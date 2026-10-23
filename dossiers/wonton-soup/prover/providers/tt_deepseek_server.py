"""Serve DeepSeek tactic samples from one Tenstorrent N300 through tt-transformers.

The server holds the model on one card and answers JSON-line requests on a Unix socket:
{"ids": [...], "n": 40, "seed": 7, "max_new_tokens": 64, "temperature": 0.6, "top_p": 0.9}
-> {"tokens": [[...], ...]}. One request runs at a time.

All samples of a request share the prompt's key-value blocks. The block-aligned prefix of
the prompt is prefilled once into shared pages; every sample slot then decodes the remaining
prompt tokens as forced inputs into its own pages before sampling, so a request costs one
prefill and at most 32 forced steps on top of its generated tokens.

Weights stay in bfloat16: with bfloat8_b weights the root proposals picked up junk tokens
the CPU path never produces.

Run with the tt-metal Python environment, MESH_DEVICE=N300 and HF_MODEL set to the model directory:
python tt_deepseek_server.py --socket /path/card0.sock
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

import torch

BLOCK = 32
BATCH = 32
MAX_PROMPT = 2048
PREFIX_BLOCKS = MAX_PROMPT // BLOCK
PRIVATE_BLOCKS = 3
STOP_STRINGS = ("[/TAC", "</s>", "<｜end▁of▁sentence｜>", "<|EOT|>", "\n\n\n", "---")
TOP_K = 64


def nucleus_sample(
    logits: torch.Tensor, temperature: float, top_p: float, generator: torch.Generator
) -> torch.Tensor:
    probs = torch.softmax(logits.float() / temperature, dim=-1)
    top_probs, top_idx = torch.topk(probs, TOP_K, dim=-1)
    covered = top_probs.sum(-1) >= top_p
    if not bool(covered.all()):
        top_probs, top_idx = torch.sort(probs, descending=True, dim=-1)
    keep = top_probs.cumsum(-1) - top_probs < top_p
    kept = top_probs * keep
    choice = torch.multinomial(kept / kept.sum(-1, keepdim=True), 1, generator=generator)
    return top_idx.gather(-1, choice).squeeze(-1)


class Sampler:
    def __init__(self) -> None:
        import ttnn
        from models.tt_transformers.tt.common import PagedAttentionConfig, create_tt_model
        from models.tt_transformers.tt.generator import Generator
        from models.tt_transformers.tt.model_config import DecodersPrecision

        self.ttnn = ttnn
        ttnn.set_fabric_config(ttnn.FabricConfig.FABRIC_1D)
        self.mesh = ttnn.open_mesh_device(
            ttnn.MeshShape(1, 2),
            trace_region_size=50_000_000,
            num_command_queues=1,
            dispatch_core_config=ttnn.DispatchCoreConfig(),
        )
        # Block 0 absorbs the padded positions that prefill writes past the prompt.
        self.prefix_pages = torch.arange(1, 1 + PREFIX_BLOCKS)
        first_private = 1 + PREFIX_BLOCKS
        self.private_pages = torch.arange(
            first_private, first_private + BATCH * PRIVATE_BLOCKS
        ).reshape(BATCH, PRIVATE_BLOCKS)
        paged = PagedAttentionConfig(
            block_size=BLOCK, max_num_blocks=first_private + BATCH * PRIVATE_BLOCKS
        )
        self.args, self.model, self.kv, _ = create_tt_model(
            self.mesh,
            instruct=False,
            max_batch_size=BATCH,
            optimizations=lambda a: DecodersPrecision.accuracy(a.n_layers, a.model_name),
            max_seq_len=4096,
            paged_attention_config=paged,
            dtype=ttnn.bfloat16,
        )
        self.generator = Generator(
            [self.model], [self.args], self.mesh, processor=None, tokenizer=self.args.tokenizer
        )
        self.tokenizer = self.args.tokenizer
        self.eos = self.tokenizer.eos_token_id
        self.vocab = self.args.vocab_size

    def _page_table(self, prefix_blocks: int) -> torch.Tensor:
        width = PREFIX_BLOCKS + PRIVATE_BLOCKS
        table = torch.zeros(BATCH, width, dtype=torch.int32)
        table[:, :prefix_blocks] = self.prefix_pages[:prefix_blocks]
        table[:, prefix_blocks : prefix_blocks + PRIVATE_BLOCKS] = self.private_pages
        return table

    def _prefill_prefix(self, prefix: list[int]) -> None:
        table = torch.zeros(1, PREFIX_BLOCKS + PRIVATE_BLOCKS, dtype=torch.int32)
        table[0, : len(prefix) // BLOCK] = self.prefix_pages[: len(prefix) // BLOCK]
        self.generator.prefill_forward_text(
            torch.tensor([prefix]),
            page_table=table,
            kv_cache=[self.kv],
            prompt_lens=[len(prefix)],
            empty_slots=[0],
            enable_trace=False,
            warmup_prefill=False,
        )

    def _round(
        self,
        tail: list[int],
        start: int,
        table: torch.Tensor,
        keep: int,
        request: dict,
        generator: torch.Generator,
    ) -> list[list[int]]:
        out: list[list[int]] = [[] for _ in range(keep)]
        done = [False] * keep
        pos = torch.full((BATCH,), start)
        tok = torch.full((BATCH,), tail[0])
        steps = len(tail) - 1 + request["max_new_tokens"]
        for step in range(steps):
            logits, _ = self.generator.decode_forward(
                tok.reshape(BATCH, 1),
                pos,
                page_table=table,
                kv_cache=[self.kv],
                enable_trace=True,
                reset_batch=step == 0,
            )
            pos += 1
            if step + 1 < len(tail):
                tok = torch.full((BATCH,), tail[step + 1])
                continue
            tok = nucleus_sample(
                logits.reshape(BATCH, -1)[:, : self.vocab],
                request["temperature"],
                request["top_p"],
                generator,
            )
            for b in range(keep):
                if done[b]:
                    continue
                out[b].append(int(tok[b]))
                if int(tok[b]) == self.eos or any(
                    s in self.tokenizer.decode(out[b]) for s in STOP_STRINGS
                ):
                    done[b] = True
            if all(done):
                break
        return out

    def sample(self, request: dict) -> list[list[int]]:
        ids = request["ids"]
        if not 2 <= len(ids) <= MAX_PROMPT:
            raise ValueError(f"prompt length {len(ids)} outside [2, {MAX_PROMPT}]")
        prefix_len = ((len(ids) - 1) // BLOCK) * BLOCK
        if prefix_len:
            self._prefill_prefix(ids[:prefix_len])
        table = self._page_table(prefix_len // BLOCK)
        generator = torch.Generator().manual_seed(int(request["seed"]))
        rounds = -(-request["n"] // BATCH)
        sizes = [request["n"] // rounds + (i < request["n"] % rounds) for i in range(rounds)]
        tokens: list[list[int]] = []
        for keep in sizes:
            tokens.extend(
                self._round(ids[prefix_len:], prefix_len, table, keep, request, generator)
            )
        return tokens


def serve(socket_path: Path) -> None:
    sampler = Sampler()
    lock = threading.Lock()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            for line in self.rfile:
                request = json.loads(line)
                started = time.monotonic()
                with lock:
                    tokens = sampler.sample(request)
                reply = {"tokens": tokens, "seconds": round(time.monotonic() - started, 3)}
                self.wfile.write((json.dumps(reply) + "\n").encode())
                self.wfile.flush()

    if socket_path.exists():
        socket_path.unlink()
    # Closing the mesh on SIGTERM leaves the card's dispatch cores idle for the next server.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        with socketserver.ThreadingUnixStreamServer(str(socket_path), Handler) as server:
            print(f"READY {socket_path} pid={os.getpid()}", flush=True)
            server.serve_forever()
    finally:
        with lock:
            sampler.ttnn.close_mesh_device(sampler.mesh)


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
        reply = sock.makefile("rb").readline()
    return json.loads(reply)["tokens"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True, type=Path)
    serve(parser.parse_args().socket)
