"""Serve ReProver tactic samples to many concurrent searches from one copy of the model on a CPU.

Requests are JSON lines on a Unix socket: {"ids": [...], "n": 10, "seed": 7, "max_new_tokens": 255,
"temperature": 0.7, "top_p": 0.9} -> {"tokens": [[...], ...]}, each sample ending with the
end-of-sequence token unless it hit the length limit.

Decoding one step reads every decoder weight, and on a CPU that read costs about as much at ten rows
as at a hundred. One search's ten samples therefore leave most of each step unused, and separate
search processes contend for the same memory bandwidth instead of sharing it. Here every step
decodes the live samples of all pending requests together. A request joins at the next step after
its encoder pass and leaves as soon as its last sample ends, and a sample that has ended stops
taking rows. Attention stays per request: each keeps its encoder keys and values at batch size one
and its own self-attention cache, as in `sample_shared_encoder`.

Each request samples from its own generator seeded by the client, so its draws do not depend on
which other requests share its steps.

python reprover_sample_server.py --socket /path/reprover0.sock --dtype float32 --threads 4
"""

from __future__ import annotations

import argparse
import json
import queue
import socket
import socketserver
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch

from prover.providers.reprover_client import REPROVER_MODEL_ID


def nucleus_sample(
    logits: torch.Tensor, temperature: float, top_p: float, generator: torch.Generator
) -> torch.Tensor:
    sorted_logits, sorted_ids = (logits.float() / temperature).sort(descending=True)
    remove = sorted_logits.softmax(-1).cumsum(-1) > top_p
    remove[:, 1:] = remove[:, :-1].clone()
    remove[:, 0] = False
    sorted_logits[remove] = float("-inf")
    choice = torch.multinomial(sorted_logits.softmax(-1), 1, generator=generator)
    return sorted_ids.gather(1, choice).squeeze(1)


@dataclass
class Request:
    ids: list[int]
    n: int
    seed: int
    max_new_tokens: int
    temperature: float
    top_p: float
    done: threading.Event = field(default_factory=threading.Event)
    result: list[list[int]] | None = None
    error: str | None = None


class _Live:
    """A request inside the decode loop; its rows are the samples that have not ended, in order."""

    def __init__(
        self,
        request: Request,
        cross: list[tuple[torch.Tensor, torch.Tensor]],
        blocks: int,
        heads: int,
        head_dim: int,
        dtype: torch.dtype,
        start_token: int,
    ) -> None:
        self.request = request
        self.cross = cross
        n, steps = request.n, request.max_new_tokens
        self.self_kv = [
            (
                torch.empty(n, heads, steps, head_dim, dtype=dtype),
                torch.empty(n, heads, steps, head_dim, dtype=dtype),
            )
            for _ in range(blocks)
        ]
        self.rows = torch.arange(n)
        self.tokens = torch.full((n,), start_token, dtype=torch.long)
        self.step = 0
        self.generator = torch.Generator().manual_seed(request.seed)
        self.out: list[list[int]] = [[] for _ in range(n)]


class BatchedSampler:
    def __init__(self, model: Any) -> None:
        config = model.config
        self.model = model
        self.decoder = model.decoder
        self.blocks = self.decoder.block
        self.heads, self.head_dim = config.num_heads, config.d_kv
        self.eos = config.eos_token_id
        self.start = config.decoder_start_token_id
        self.scale = config.d_model**-0.5 if config.scale_decoder_outputs else None
        self.dtype = model.dtype
        self.bias = self.blocks[0].layer[0].SelfAttention
        self.position_bias = torch.empty(0)
        self.pending: queue.Queue[Request] = queue.Queue()

    def _bias_rows(self, steps: int) -> torch.Tensor:
        if self.position_bias.shape[-1] < steps:
            self.position_bias = self.bias.compute_bias(steps, steps)
        return self.position_bias

    def _admit(self, request: Request) -> _Live:
        ids = torch.tensor([request.ids], dtype=torch.long)
        encoded = self.model.encoder(input_ids=ids).last_hidden_state
        cross = [
            (
                block.layer[1]
                .EncDecAttention.k(encoded)
                .view(1, -1, self.heads, self.head_dim)
                .transpose(1, 2),
                block.layer[1]
                .EncDecAttention.v(encoded)
                .view(1, -1, self.heads, self.head_dim)
                .transpose(1, 2),
            )
            for block in self.blocks
        ]
        return _Live(
            request, cross, len(self.blocks), self.heads, self.head_dim, self.dtype, self.start
        )

    def _step(self, live: list[_Live]) -> None:
        heads, head_dim = self.heads, self.head_dim
        sizes = [len(r.rows) for r in live]
        bias = self._bias_rows(max(r.request.max_new_tokens for r in live))
        x = self.decoder.embed_tokens(torch.cat([r.tokens for r in live])[:, None])
        for b, block in enumerate(self.blocks):
            attn = block.layer[0].SelfAttention
            h = block.layer[0].layer_norm(x)
            q_all = attn.q(h).view(-1, 1, heads, head_dim).transpose(1, 2).split(sizes)
            k_all = attn.k(h).view(-1, 1, heads, head_dim).transpose(1, 2).split(sizes)
            v_all = attn.v(h).view(-1, 1, heads, head_dim).transpose(1, 2).split(sizes)
            outs = []
            for r, q, k, v in zip(live, q_all, k_all, v_all):
                ks, vs = r.self_kv[b]
                step, seen = r.step, r.step + 1
                ks[:, :, step : step + 1] = k
                vs[:, :, step : step + 1] = v
                scores = (
                    torch.matmul(q, ks[:, :, :seen].transpose(-1, -2))
                    + bias[:, :, step : step + 1, :seen]
                )
                outs.append(
                    torch.matmul(scores.float().softmax(-1).to(self.dtype), vs[:, :, :seen])
                )
            out = torch.cat(outs).transpose(1, 2).reshape(-1, 1, heads * head_dim)
            x = x + attn.o(out)

            cross_attn = block.layer[1].EncDecAttention
            h = block.layer[1].layer_norm(x)
            q_all = cross_attn.q(h).view(-1, heads, head_dim).split(sizes)
            outs = []
            for r, q in zip(live, q_all):
                kc, vc = r.cross[b]
                # (1, heads, rows, head_dim): samples are query rows on the one encoder output.
                q_rows = q.transpose(0, 1).unsqueeze(0)
                weights = (
                    torch.matmul(q_rows, kc.transpose(-1, -2)).float().softmax(-1).to(self.dtype)
                )
                outs.append(torch.matmul(weights, vc).squeeze(0).transpose(0, 1))
            x = x + cross_attn.o(torch.cat(outs).reshape(-1, 1, heads * head_dim))

            x = x + block.layer[2].DenseReluDense(block.layer[2].layer_norm(x))
        x = self.decoder.final_layer_norm(x)
        if self.scale is not None:
            x = x * self.scale
        logits = self.model.lm_head(x)[:, -1].split(sizes)
        for r, row_logits in zip(live, logits):
            req = r.request
            nxt = nucleus_sample(row_logits, req.temperature, req.top_p, r.generator)
            for row, token in zip(r.rows.tolist(), nxt.tolist()):
                r.out[row].append(token)
            r.step += 1
            keep = nxt != self.eos
            if r.step == req.max_new_tokens:
                keep[:] = False
            if not bool(keep.all()):
                r.rows = r.rows[keep]
                r.self_kv = [(ks[keep], vs[keep]) for ks, vs in r.self_kv]
            r.tokens = nxt[keep]

    def run(self) -> None:
        live: list[_Live] = []
        while True:
            waiting: list[Request] = []
            try:
                waiting.append(self.pending.get(block=not live))
                while True:
                    waiting.append(self.pending.get_nowait())
            except queue.Empty:
                pass
            with torch.no_grad():
                for request in waiting:
                    try:
                        live.append(self._admit(request))
                    except Exception as exc:
                        request.error = repr(exc)
                        request.done.set()
                try:
                    self._step(live)
                except Exception as exc:
                    for r in live:
                        r.request.error = repr(exc)
                        r.request.done.set()
                    live = []
                    continue
            for r in live:
                if len(r.rows) == 0:
                    r.request.result = r.out
                    r.request.done.set()
            live = [r for r in live if len(r.rows) > 0]


def serve(socket_path: Path, dtype: torch.dtype, threads: int) -> None:
    from transformers import AutoModelForSeq2SeqLM

    torch.set_num_threads(threads)
    model = AutoModelForSeq2SeqLM.from_pretrained(REPROVER_MODEL_ID, dtype=dtype).eval()
    sampler = BatchedSampler(model)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            for line in self.rfile:
                request = Request(**json.loads(line))
                sampler.pending.put(request)
                request.done.wait()
                reply = (
                    {"error": request.error}
                    if request.error is not None
                    else {"tokens": request.result}
                )
                self.wfile.write((json.dumps(reply) + "\n").encode())
                self.wfile.flush()

    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True

    socket_path.unlink(missing_ok=True)
    threading.Thread(target=sampler.run, daemon=True).start()
    with Server(str(socket_path), Handler) as server:
        print(
            f"serving {REPROVER_MODEL_ID} ({dtype}, {threads} threads) on {socket_path}", flush=True
        )
        server.serve_forever()


def request_samples(
    socket_path: str,
    ids: list[int],
    n: int,
    seed: int,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
) -> list[list[int]]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(socket_path)
        payload = dict(
            ids=ids,
            n=n,
            seed=seed,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        sock.sendall((json.dumps(payload) + "\n").encode())
        reply = json.loads(sock.makefile("rb").readline())
    if "error" in reply:
        raise RuntimeError(f"reprover sample server: {reply['error']}")
    return reply["tokens"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--dtype", required=True, choices=("float32", "bfloat16"))
    parser.add_argument("--threads", required=True, type=int)
    args = parser.parse_args()
    serve(args.socket, getattr(torch, args.dtype), args.threads)
