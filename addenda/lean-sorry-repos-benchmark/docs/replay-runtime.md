# Replay Runtime Image

This benchmark has two container targets:
- `Dockerfile`: lightweight benchmark harness validation.
- `Dockerfile.replay`: pinned runtime for `repo_replay` execution.

## Pinned Inputs
- Base image: `python:3.12.8-slim`
- `uv`: `0.9.26`
- `elan`: `4.1.2`
- Lean toolchain: `leanprover/lean4:v4.28.0`

## Build + Emit Runtime Manifest
```bash
cd addenda/lean-sorry-repos-benchmark
./scripts/build_replay_runtime.sh \
  lean-sorry-repos-benchmark-replay:local \
  artifacts/replay-runtime
```

This writes:
- `artifacts/replay-runtime/runtime_manifest.json`

Manifest fields include:
- image tag and image id
- exact runtime command versions (`python`, `uv`, `git`, `lean`, `lake`, `elan`)
- generation timestamp

Use this manifest as the release-time runtime pin for replay runs.
