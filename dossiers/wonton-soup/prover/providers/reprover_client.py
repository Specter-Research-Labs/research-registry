from __future__ import annotations

import torch
from transformers import AutoModel, AutoModelForSeq2SeqLM, AutoTokenizer

REPROVER_MODEL_ID = "kaiyuy/leandojo-lean4-tacgen-byt5-small"
REPROVER_MAX_INPUT_LENGTH = 2300
REPROVER_DEFAULT_MAX_LENGTH = 256
REPROVER_BEAM_LIMIT = 4


def get_default_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class ReProverModel:
    MODEL_ID = REPROVER_MODEL_ID
    DEFAULT_MAX_INPUT_LENGTH = REPROVER_MAX_INPUT_LENGTH
    DEFAULT_MAX_LENGTH = REPROVER_DEFAULT_MAX_LENGTH
    DEFAULT_BEAM_LIMIT = REPROVER_BEAM_LIMIT

    def __init__(
        self,
        device: str | None = None,
        use_sampling: bool = False,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ):
        self.device = device if device is not None else get_default_device()
        self.tokenizer = None
        self.model = None
        self.use_sampling = use_sampling
        self.temperature = temperature
        self.top_p = top_p

    def load(self):
        self.tokenizer = AutoTokenizer.from_pretrained(self.MODEL_ID)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            self.MODEL_ID
        ).to(self.device)
        self.model.eval()

    def set_seed(self, seed: int) -> None:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

    def generate_tactics(
        self, state: str, num_return: int = 10, max_length: int = DEFAULT_MAX_LENGTH
    ) -> list[tuple[str, float]]:
        if self.tokenizer is None or self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        inputs = self.tokenizer(
            state,
            return_tensors="pt",
            max_length=self.DEFAULT_MAX_INPUT_LENGTH,
            truncation=True,
        ).to(self.device)

        with torch.no_grad():
            if self.use_sampling:
                outputs = self.model.generate(
                    **inputs,
                    max_length=max_length,
                    do_sample=True,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    num_return_sequences=num_return,
                    return_dict_in_generate=True,
                    output_scores=True,
                )
            else:
                num_beams = min(num_return, self.DEFAULT_BEAM_LIMIT)
                outputs = self.model.generate(
                    **inputs,
                    max_length=max_length,
                    num_beams=num_beams,
                    num_return_sequences=num_beams,
                    length_penalty=0.0,
                    early_stopping=False,
                    return_dict_in_generate=True,
                    output_scores=True,
                )

        tactics = []
        for i, seq in enumerate(outputs.sequences):
            tactic = self.tokenizer.decode(seq, skip_special_tokens=True)
            has_scores = hasattr(outputs, "sequences_scores")
            score = outputs.sequences_scores[i].item() if has_scores else 0.0
            prob = torch.sigmoid(torch.tensor(score)).item()
            tactics.append((tactic.strip(), prob))

        return sorted(tactics, key=lambda x: x[1], reverse=True)

    def generate_tactics_multi_run(
        self,
        state: str,
        num_return: int = 10,
        num_runs: int = 3,
        max_length: int = DEFAULT_MAX_LENGTH,
    ) -> list[tuple[str, float]]:
        if not self.use_sampling:
            return self.generate_tactics(state, num_return, max_length)

        seen: dict[str, float] = {}
        for _ in range(num_runs):
            tactics = self.generate_tactics(state, num_return, max_length)
            for tactic, prob in tactics:
                if tactic not in seen or prob > seen[tactic]:
                    seen[tactic] = prob

        results = [(t, p) for t, p in seen.items()]
        return sorted(results, key=lambda x: x[1], reverse=True)[:num_return]

    def generate_tactics_with_premises(
        self, state: str, premises: list[str], num_return: int = 10
    ) -> list[tuple[str, float]]:
        input_text = "\n\n".join(premises + [state])
        return self.generate_tactics(input_text, num_return)

    def generate_tactics_batch(
        self, states: list[str], num_return: int = 10, max_length: int = DEFAULT_MAX_LENGTH
    ) -> list[list[tuple[str, float]]]:
        if self.tokenizer is None or self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        inputs = self.tokenizer(
            states,
            return_tensors="pt",
            padding=True,
            max_length=self.DEFAULT_MAX_INPUT_LENGTH,
            truncation=True,
        ).to(self.device)

        num_beams = min(num_return, self.DEFAULT_BEAM_LIMIT)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_length=max_length,
                num_beams=num_beams,
                num_return_sequences=num_beams,
                length_penalty=0.0,
                early_stopping=False,
                return_dict_in_generate=True,
                output_scores=True,
            )

        batch_size = len(states)
        all_tactics = []
        for i in range(batch_size):
            tactics = []
            for j in range(num_beams):
                idx = i * num_beams + j
                tactic = self.tokenizer.decode(outputs.sequences[idx], skip_special_tokens=True)
                has_scores = hasattr(outputs, "sequences_scores")
                score = outputs.sequences_scores[idx].item() if has_scores else 0.0
                prob = torch.sigmoid(torch.tensor(score)).item()
                tactics.append((tactic.strip(), prob))
            all_tactics.append(sorted(tactics, key=lambda x: x[1], reverse=True))

        return all_tactics


class PremiseRetriever:
    def __init__(self, device: str | None = None):
        self.device = device if device is not None else get_default_device()
        self.encoder = None
        self.tokenizer = None
        self.premise_embeddings: torch.Tensor | None = None
        self.premise_names: list[str] = []

    def load(self):
        self.tokenizer = AutoTokenizer.from_pretrained("kaiyuy/leandojo-lean4-retriever-byt5-small")
        self.encoder = AutoModel.from_pretrained("kaiyuy/leandojo-lean4-retriever-byt5-small").to(
            self.device
        )
        self.encoder.eval()

    def load_premises(self, premises: list[tuple[str, str]]):
        self.premise_names = [name for name, _ in premises]
        statements = [stmt for _, stmt in premises]
        self.premise_embeddings = self._encode_batch(statements)

    def _encode_batch(self, texts: list[str]) -> torch.Tensor:
        if self.tokenizer is None or self.encoder is None:
            raise RuntimeError("Retriever not loaded. Call load() first.")

        inputs = self.tokenizer(
            texts, return_tensors="pt", padding=True, truncation=True, max_length=512
        ).to(self.device)
        with torch.no_grad():
            outputs = self.encoder(**inputs)
            embeddings = outputs.last_hidden_state.mean(dim=1)
        return embeddings

    def retrieve(self, state: str, k: int = 100) -> list[str]:
        if self.premise_embeddings is None:
            raise RuntimeError("No premises loaded. Call load_premises() first.")

        state_emb = self._encode_batch([state])
        scores = torch.cosine_similarity(state_emb, self.premise_embeddings)
        top_k = torch.topk(scores, min(k, len(self.premise_names)))
        return [self.premise_names[i] for i in top_k.indices.tolist()]
