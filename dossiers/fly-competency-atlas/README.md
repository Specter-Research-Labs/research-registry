# Fly Competency Atlas

FlyBrainLab harness for upstream inventory, runtime checks, motif selection, and first-pass
lamina experiments. The goal is to stage fly circuits as one more substrate for the lab's
competency assays: efficiency, lesion tolerance, basin preservation, structured-vs-noise
sensitivity, and whole-over-parts advantage.

## Start Here

```bash
cd dossiers/fly-competency-atlas
nix develop
uv run fly-competency-atlas doctor
uv run fly-competency-atlas backend doctor
uv run fly-competency-atlas catalog
uv run fly-competency-atlas inventory
uv run fly-competency-atlas lamina prepare
uv run fly-competency-atlas lamina local-execute
uv run fly-competency-atlas lamina execute --dry-run
```

`direnv allow` from `dossiers/fly-competency-atlas/` is equivalent to `nix develop`; the shell
runs `uv sync`.

Create the separate upstream-style FlyBrainLab client env only when you need to import
`flybrainlab` directly:

```bash
cd dossiers/fly-competency-atlas
./scripts/bootstrap_flybrainlab_user_side.sh /path/to/python3.9 .venv-flybrainlab
source .venv-flybrainlab/bin/activate
python -c "import flybrainlab, neuromynerva, jupyterlab"
```

That env stays separate because the upstream client still expects JupyterLab `>=3.0,<3.6` and
probes the `jupyter` executable on `PATH` during import.

## Harness Surfaces

- `doctor`: report FlyBrainLab-related package availability
- `backend doctor`: check whether this host can run a local execution backend
- `backend probe`: connect to an FFBO processor and report datasets plus Neurokernel availability
- `catalog`: print the tracked motif and dataset panel
- `inventory`: query upstream tutorials and dataset catalog
- `lamina prepare`: fetch lamina cartridge assets and write the sweep manifest
- `lamina local-execute`: run the lamina panel through the local CPU surrogate
- `lamina execute`: run the prepared panel through a FlyBrainLab backend

Real Neurokernel execution needs a working FFBO processor URL from a full backend install. The
packaged FlyBrainLab default endpoint is stale, and the public user-side backends do not provide
Neurokernel execution.

## Backend Setup

The full backend expects Linux, Docker, and NVIDIA CUDA.

- Use Linux x86_64 with Docker and NVIDIA GPU support for local backend work.
- Use Apple silicon for the client stack and local surrogate runs.
- Use a remote Linux x86_64 GPU host or the FFBO AMI when Apple silicon needs real execution.

Check the current host:

```bash
cd dossiers/fly-competency-atlas
uv run fly-competency-atlas backend doctor
```

On an execution-capable Linux host, launch the upstream Docker image:

```bash
cd dossiers/fly-competency-atlas
./scripts/start_flybrainlab_docker_backend.sh --database-dir /path/to/fbl-databases
```

That script exposes:

- Jupyter UI: `http://localhost:9999`
- FFBO processor: `ws://localhost:8081/ws`

Probe before running the lamina panel:

```bash
cd dossiers/fly-competency-atlas
uv run fly-competency-atlas backend probe --processor-url ws://localhost:8081/ws --dataset hemibrain
```

If the dataset name is unknown, omit `--dataset` first. The probe lists valid datasets when the
backend exposes more than one.

## Local Execution

Local execution reuses the upstream lamina cartridge assets and manifest cases, then runs them
through a small mixed-sign CPU surrogate instead of FFBO. This is the Apple silicon path for
perturbation, pattern-sensitivity, and recovery experiments; it is not Neurokernel parity.

```bash
cd dossiers/fly-competency-atlas
uv run fly-competency-atlas lamina prepare
uv run fly-competency-atlas lamina local-execute
```

Outputs:

- `results/<manifest>.local.ndjson`: completed run records
- `results/<manifest>.local/`: raw per-case outputs and downsampled traces

## First Motif Panel

- `lamina_cartridge`: executable circuit tutorial and first pattern-sensitive recovery surface
- `osn_ephys`: olfactory sensory neuron tutorial for structured-vs-noise assays
- `optic_lobe_1_0`: larger visual dataset, near-term follow-on after lamina
- `hemibrain_1_2`: broad central-brain substrate for motif extraction and lesion panels
- `flywire_783`: current large-scale atlas surface for later competency catalog expansion
