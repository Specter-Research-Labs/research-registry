import tempfile
import threading
import time
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from prover.providers import reprover_sample_server
from prover.providers.reprover_sample_server import BatchedSampler, Request, request_samples


def _tiny_t5():
    torch.manual_seed(0)
    config = transformers.T5Config(
        vocab_size=50,
        d_model=32,
        d_kv=8,
        d_ff=64,
        num_layers=2,
        num_decoder_layers=2,
        num_heads=4,
        feed_forward_proj="gated-gelu",
        tie_word_embeddings=False,
        decoder_start_token_id=0,
        eos_token_id=1,
        pad_token_id=0,
    )
    return transformers.T5ForConditionalGeneration(config).eval()


def _request(ids, n, seed=0, top_p=1.0, temperature=3.0, max_new_tokens=15):
    return Request(
        ids=ids, n=n, seed=seed, max_new_tokens=max_new_tokens, temperature=temperature, top_p=top_p
    )


def _drive(sampler, arrivals):
    """Step the sampler by hand, admitting each request at its step, so that join order is fixed."""
    live, step = [], 0
    with torch.no_grad():
        while arrivals or live:
            live += [sampler._admit(r) for at, r in arrivals if at == step]
            arrivals = [(at, r) for at, r in arrivals if at != step]
            if live:
                sampler._step(live)
                live = [r for r in live if len(r.rows) > 0]
            step += 1


def _sample(sampler, requests_at):
    lives = {}
    original = sampler._admit

    def admit(request):
        lives[id(request)] = original(request)
        return lives[id(request)]

    sampler._admit = admit
    _drive(sampler, requests_at)
    return [lives[id(r)].out for _, r in requests_at]


def test_staggered_requests_each_match_greedy_generate():
    model = _tiny_t5()
    sampler = BatchedSampler(model)
    prompts = [torch.randint(2, 50, (1, length)) for length in (25, 9, 40)]
    requests = [
        (at, _request(p[0].tolist(), n, top_p=1e-9))
        for at, p, n in zip((0, 3, 7), prompts, (3, 1, 5))
    ]
    outs = _sample(sampler, requests)
    for prompt, out in zip(prompts, outs):
        with torch.no_grad():
            ref = model.generate(input_ids=prompt, do_sample=False, max_length=16)[0, 1:].tolist()
        for row in out:
            assert row == ref[: len(row)]
            assert row[-1] == 1 or len(row) == 15


def test_request_draws_do_not_depend_on_batch_neighbours():
    model = _tiny_t5()
    ids = torch.randint(2, 50, (25,)).tolist()
    alone = _sample(BatchedSampler(model), [(0, _request(ids, 16, seed=7))])[0]
    other = torch.randint(2, 50, (30,)).tolist()
    shared = _sample(
        BatchedSampler(model), [(0, _request(other, 8, seed=3)), (2, _request(ids, 16, seed=7))]
    )[1]
    assert shared == alone
    assert len({tuple(r) for r in alone}) > 1


def test_socket_round_trip(monkeypatch):
    model = _tiny_t5()
    monkeypatch.setattr(
        transformers.AutoModelForSeq2SeqLM, "from_pretrained", lambda *a, **k: model
    )
    # Unix socket paths are limited to about 100 bytes, which pytest's tmp_path on macOS exceeds.
    path = Path(tempfile.mkdtemp(dir="/tmp")) / "s.sock"
    threading.Thread(
        target=reprover_sample_server.serve, args=(path, torch.float32, 1), daemon=True
    ).start()
    deadline = time.monotonic() + 30
    while not path.exists():
        assert time.monotonic() < deadline, "sample server did not start"
        time.sleep(0.01)
    ids = torch.randint(2, 50, (20,)).tolist()
    got = request_samples(
        str(path), ids, n=4, seed=11, max_new_tokens=15, temperature=3.0, top_p=1.0
    )
    assert got == _sample(BatchedSampler(model), [(0, _request(ids, 4, seed=11))])[0]


def test_run_admits_each_request_once():
    model = _tiny_t5()
    sampler = BatchedSampler(model)
    admitted = []
    original = sampler._admit

    def admit(request):
        admitted.append(request)
        return original(request)

    sampler._admit = admit
    threading.Thread(target=sampler.run, daemon=True).start()
    requests = [_request(torch.randint(2, 50, (20,)).tolist(), 4, seed=i) for i in range(3)]
    for r in requests:
        sampler.pending.put(r)
    for r in requests:
        assert r.done.wait(30)
    assert len(admitted) == len(requests)
