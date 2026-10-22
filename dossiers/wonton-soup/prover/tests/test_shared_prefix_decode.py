import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from prover.providers import shared_prefix_decode
from prover.providers.shared_prefix_decode import sample_shared_encoder, sample_shared_prefix


def _tiny_llama():
    torch.manual_seed(0)
    config = transformers.LlamaConfig(
        vocab_size=97, hidden_size=64, intermediate_size=128, num_hidden_layers=2,
        num_attention_heads=4, num_key_value_heads=4, max_position_embeddings=256,
        rope_scaling={"rope_type": "linear", "factor": 4.0}, rope_theta=100000.0,
    )
    return transformers.LlamaForCausalLM(config).eval()


def test_nucleus_of_one_token_matches_greedy_generate():
    model = _tiny_llama()
    ids = torch.randint(0, 97, (1, 40))
    with torch.no_grad():
        ref = model.generate(input_ids=ids, attention_mask=torch.ones_like(ids), do_sample=False,
                             max_new_tokens=12, pad_token_id=96, eos_token_id=96)[0, 40:]
    out = sample_shared_prefix(model, ids, num_samples=3, max_new_tokens=12, temperature=1.0, top_p=1e-9, eos_token_id=96)
    for row in out:
        assert torch.equal(row[: len(ref)], ref)


def test_samples_differ_and_stop_at_eos():
    model = _tiny_llama()
    torch.manual_seed(1)
    out = sample_shared_prefix(model, torch.randint(0, 97, (1, 30)), num_samples=16, max_new_tokens=20,
                               temperature=1.0, top_p=0.9, eos_token_id=5)
    assert len({tuple(r) for r in out.tolist()}) > 1
    for row in out.tolist():
        if 5 in row:
            assert set(row[row.index(5):]) == {5}


def _tiny_t5():
    torch.manual_seed(0)
    config = transformers.T5Config(
        vocab_size=50, d_model=32, d_kv=8, d_ff=64, num_layers=2, num_decoder_layers=2, num_heads=4,
        feed_forward_proj="gated-gelu", tie_word_embeddings=False, decoder_start_token_id=0, eos_token_id=1, pad_token_id=0,
    )
    return transformers.T5ForConditionalGeneration(config).eval()


def test_t5_nucleus_of_one_token_matches_greedy_generate():
    model = _tiny_t5()
    ids = torch.randint(2, 50, (1, 25))
    with torch.no_grad():
        ref = model.generate(input_ids=ids, do_sample=False, max_length=16)[0, 1:]
    out = sample_shared_encoder(model, ids, num_samples=3, max_new_tokens=15, temperature=1.0, top_p=1e-9)
    for row in out:
        assert torch.equal(row[: len(ref)], ref)


def _record_logits(monkeypatch):
    seen = []

    def pick(logits, temperature, top_p):
        seen.append(logits.float())
        return logits.argmax(-1)

    monkeypatch.setattr(shared_prefix_decode, "_nucleus_sample", pick)
    return seen


@pytest.mark.parametrize("tied", [False, True])
def test_t5_step_logits_match_full_forward(monkeypatch, tied):
    torch.manual_seed(0)
    config = transformers.T5Config(
        vocab_size=50, d_model=32, d_kv=8, d_ff=64, num_layers=2, num_decoder_layers=2, num_heads=4,
        feed_forward_proj="gated-gelu", tie_word_embeddings=tied, decoder_start_token_id=0, eos_token_id=1, pad_token_id=0,
    )
    model = transformers.T5ForConditionalGeneration(config).eval()
    ids = torch.randint(2, 50, (1, 25))
    seen = _record_logits(monkeypatch)
    out = sample_shared_encoder(model, ids, num_samples=2, max_new_tokens=6, temperature=1.0, top_p=1.0)
    decoder_ids = torch.cat([torch.zeros(1, 1, dtype=torch.long), out[:1, :-1]], 1)
    with torch.no_grad():
        full = model(input_ids=ids, decoder_input_ids=decoder_ids).logits[0]
    for step, logits in enumerate(seen):
        assert torch.allclose(logits[0], full[step], atol=1e-4)


def test_llama_step_logits_match_full_forward(monkeypatch):
    model = _tiny_llama()
    ids = torch.randint(0, 97, (1, 40))
    seen = _record_logits(monkeypatch)
    out = sample_shared_prefix(model, ids, num_samples=2, max_new_tokens=6, temperature=1.0, top_p=1.0, eos_token_id=96)
    with torch.no_grad():
        full = model(input_ids=torch.cat([ids, out[:1, :-1]], 1)).logits[0, 39:]
    for step, logits in enumerate(seen):
        assert torch.allclose(logits[0], full[step], atol=1e-4)


def test_byt5_decode_matches_tokenizer():
    from prover.providers.reprover_client import decode_byt5

    tokenizer = transformers.ByT5Tokenizer()
    torch.manual_seed(0)
    for _ in range(50):
        ids = torch.randint(0, 384, (int(torch.randint(1, 80, ()).item()),)).tolist()
        assert decode_byt5(ids) == tokenizer.decode(ids, skip_special_tokens=True)
    text = "simp [Nat.add_zero] ⊢ ∀ ε > 0, ‖x‖ ≤ ε"
    assert decode_byt5(tokenizer(text)["input_ids"]) == text
