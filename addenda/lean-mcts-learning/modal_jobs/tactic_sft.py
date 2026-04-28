from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import modal

APP_NAME = "wonton-tactic-sft"
MODEL_CACHE_DIR = "/model_cache"
DATA_DIR = "/data"
OUTPUT_DIR = "/outputs"

app = modal.App(APP_NAME)

train_image = (
    modal.Image.debian_slim(python_version="3.11")
    .uv_pip_install(
        "accelerate==1.9.0",
        "datasets==3.6.0",
        "huggingface_hub==0.34.2",
        "peft==0.16.0",
        "transformers==4.54.0",
        "trl==0.19.1",
        "unsloth[cu128-torch270]==2025.7.8",
        "unsloth_zoo==2025.7.10",
    )
    .env({"HF_HOME": MODEL_CACHE_DIR, "HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

with train_image.imports():
    import datasets
    from transformers import TrainingArguments
    from transformers.trainer_utils import get_last_checkpoint
    from trl import SFTTrainer
    from unsloth import FastLanguageModel

model_cache_volume = modal.Volume.from_name("wonton-learning-model-cache", create_if_missing=True)
data_volume = modal.Volume.from_name("wonton-learning-data", create_if_missing=True)
output_volume = modal.Volume.from_name("wonton-learning-outputs", create_if_missing=True)


LORA_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


@dataclass(frozen=True)
class TrainingConfig:
    model_name: str = "deepseek-ai/DeepSeek-Prover-V2-7B"
    dataset_relpath: str = "data/tactic_sft.jsonl"
    output_subdir: str = "runs/default"
    max_seq_length: int = 2048
    load_in_4bit: bool = True
    load_in_8bit: bool = False
    lora_r: int = 16
    lora_alpha: int = 16
    lora_dropout: float = 0.0
    batch_size: int = 2
    gradient_accumulation_steps: int = 8
    learning_rate: float = 2e-4
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    max_steps: int = 1000
    save_steps: int = 100
    eval_steps: int = 100
    logging_steps: int = 10
    eval_split_ratio: float = 0.1
    seed: int = 42
    skip_eval: bool = False
    resume: bool = True


def _load_jsonl_dataset(dataset_path: Path, eval_split_ratio: float, seed: int):
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found in volume: {dataset_path}")
    if not (0.0 < eval_split_ratio < 1.0):
        raise ValueError(f"eval_split_ratio must be in (0,1), got {eval_split_ratio}")

    ds = datasets.load_dataset("json", data_files=str(dataset_path), split="train")
    split = ds.train_test_split(test_size=eval_split_ratio, seed=seed)
    return split["train"], split["test"]


def _train_impl(config_dict: dict[str, Any], gpu_label: str) -> dict[str, Any]:
    config = TrainingConfig(**config_dict)
    dataset_path = (Path(DATA_DIR) / config.dataset_relpath).resolve()
    output_dir = (Path(OUTPUT_DIR) / config.output_subdir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    train_ds, eval_ds = _load_jsonl_dataset(
        dataset_path=dataset_path,
        eval_split_ratio=config.eval_split_ratio,
        seed=config.seed,
    )

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config.model_name,
        max_seq_length=config.max_seq_length,
        dtype=None,
        load_in_4bit=config.load_in_4bit,
        load_in_8bit=config.load_in_8bit,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=config.lora_r,
        target_modules=LORA_TARGET_MODULES,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=config.seed,
    )

    args = TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=config.batch_size,
        per_device_eval_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=config.warmup_ratio,
        weight_decay=config.weight_decay,
        max_steps=config.max_steps,
        save_steps=config.save_steps,
        eval_steps=config.eval_steps,
        logging_steps=config.logging_steps,
        seed=config.seed,
        bf16=True,
        fp16=False,
        report_to=["none"],
        remove_unused_columns=False,
        evaluation_strategy="no" if config.skip_eval else "steps",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=None if config.skip_eval else eval_ds,
        dataset_text_field="text",
        max_seq_length=config.max_seq_length,
        packing=False,
        args=args,
    )

    resume_from = None
    if config.resume:
        resume_from = get_last_checkpoint(str(output_dir))

    train_result = trainer.train(resume_from_checkpoint=resume_from)
    adapter_dir = output_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))

    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "gpu": gpu_label,
        "dataset_path": str(dataset_path),
        "output_dir": str(output_dir),
        "adapter_dir": str(adapter_dir),
        "resume_from_checkpoint": resume_from,
        "metrics": train_result.metrics,
        "config": asdict(config),
        "rows_train": len(train_ds),
        "rows_eval": 0 if config.skip_eval else len(eval_ds),
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(payload, indent=2))
    output_volume.commit()
    return payload


@app.function(
    image=train_image,
    gpu="L40S",
    timeout=60 * 60 * 8,
    retries=2,
    volumes={
        MODEL_CACHE_DIR: model_cache_volume,
        DATA_DIR: data_volume,
        OUTPUT_DIR: output_volume,
    },
    secrets=[modal.Secret.from_name("hf")],
)
def train_l40s(config_dict: dict[str, Any]) -> dict[str, Any]:
    return _train_impl(config_dict, gpu_label="L40S")


@app.function(
    image=train_image,
    gpu="A100-80GB",
    timeout=60 * 60 * 8,
    retries=2,
    volumes={
        MODEL_CACHE_DIR: model_cache_volume,
        DATA_DIR: data_volume,
        OUTPUT_DIR: output_volume,
    },
    secrets=[modal.Secret.from_name("hf")],
)
def train_a100(config_dict: dict[str, Any]) -> dict[str, Any]:
    return _train_impl(config_dict, gpu_label="A100-80GB")


@app.local_entrypoint()
def main(
    dataset_path: str,
    dataset_relpath: str = "data/tactic_sft.jsonl",
    output_subdir: str = "runs/default",
    gpu: str = "l40s",
    max_steps: int = 1000,
    save_steps: int = 100,
    eval_steps: int = 100,
    skip_eval: bool = False,
) -> None:
    src = Path(dataset_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"dataset_path does not exist: {src}")
    rel = Path(dataset_relpath)
    if rel.is_absolute():
        raise ValueError("dataset_relpath must be relative")

    with data_volume.batch_upload(force=True) as batch:
        batch.put_file(str(src), str(rel))
    data_volume.commit()

    config = TrainingConfig(
        dataset_relpath=str(rel),
        output_subdir=output_subdir,
        max_steps=max_steps,
        save_steps=save_steps,
        eval_steps=eval_steps,
        skip_eval=skip_eval,
    )
    config_dict = asdict(config)

    gpu_norm = gpu.strip().lower()
    if gpu_norm in {"l40s", "l40"}:
        result = train_l40s.remote(config_dict)
    elif gpu_norm in {"a100", "a100-80gb"}:
        result = train_a100.remote(config_dict)
    else:
        raise ValueError(f"Unsupported gpu value: {gpu}. Use l40s or a100.")

    print(json.dumps(result, indent=2))
