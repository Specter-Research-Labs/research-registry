import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from prover.providers.shared_prefix_decode import sample_shared_prefix


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
