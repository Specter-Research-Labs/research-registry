#!/usr/bin/env bash
set -euo pipefail

IMAGE="${FLYBRAINLAB_DOCKER_IMAGE:-fruitflybrain/fbl:latest}"
NAME="${FLYBRAINLAB_DOCKER_NAME:-flybrainlab-backend}"
UI_PORT="${FLYBRAINLAB_UI_PORT:-9999}"
PROCESSOR_PORT="${FLYBRAINLAB_PROCESSOR_PORT:-8081}"
DATABASE_DIR="${FLYBRAINLAB_DATABASE_DIR:-}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--name NAME] [--ui-port PORT] [--processor-port PORT] [--database-dir PATH]

Launch the upstream FlyBrainLab full Docker image with the processor port exposed for the
external harness. This script is intended for Linux x86_64 hosts with NVIDIA GPU support.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)
      NAME="$2"
      shift 2
      ;;
    --ui-port)
      UI_PORT="$2"
      shift 2
      ;;
    --processor-port)
      PROCESSOR_PORT="$2"
      shift 2
      ;;
    --database-dir)
      DATABASE_DIR="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

SYSTEM="$(uname -s)"
MACHINE="$(uname -m)"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

if [[ "$SYSTEM" == "Darwin" && "$MACHINE" == "arm64" ]]; then
  echo "local Neurokernel execution is not credible on Apple silicon." >&2
  echo "FlyBrainLab full execution depends on NVIDIA CUDA; use a Linux x86_64 GPU host or the FFBO AMI." >&2
  exit 1
fi

if [[ "$SYSTEM" != "Linux" ]]; then
  echo "the upstream full backend expects Linux with NVIDIA CUDA support." >&2
  exit 1
fi

if [[ "$MACHINE" != "x86_64" && "$MACHINE" != "amd64" ]]; then
  echo "the upstream full backend is built around x86_64 CUDA tooling." >&2
  exit 1
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi is missing; this host does not look execution-capable for Neurokernel." >&2
  exit 1
fi

DOCKER_ARGS=(
  run
  --name "$NAME"
  --gpus all
  -p "${UI_PORT}:8888"
  -p "${PROCESSOR_PORT}:8081"
)

if [[ -n "$DATABASE_DIR" ]]; then
  mkdir -p "$DATABASE_DIR"
  DOCKER_ARGS+=(-v "$(cd "$DATABASE_DIR" && pwd):/home/ffbo/orientdb/databases")
fi

DOCKER_ARGS+=(-it "$IMAGE")

echo "Launching ${IMAGE}"
echo "Jupyter UI: http://localhost:${UI_PORT}"
echo "Processor URL: ws://localhost:${PROCESSOR_PORT}/ws"
echo ""
echo "docker ${DOCKER_ARGS[*]}"
exec docker "${DOCKER_ARGS[@]}"
