SHELL := /bin/bash

PYTHON_TYPECHECK_PATHS := \
	lenia_swarm_analysis/_cli.py \
	lenia_swarm_analysis/_commands.py \
	lenia_swarm_analysis/_dispatch.py \
	lenia_swarm_analysis/paths.py \
	lenia_swarm_analysis/morphospace_cli.py \
	lenia_swarm_analysis/morphospace/schema.py \
	lenia_swarm_analysis/morphospace/warehouse.py \
	lenia_swarm_analysis/morphospace/ingest_compendium.py \
	lenia_swarm_analysis/morphospace/migrate_v9.py \
	lenia_swarm_analysis/morphospace/regenerate_v9.py \
	lenia_swarm_analysis/morphospace/derive_anatomy.py \
	lenia_swarm_analysis/morphospace/derive_axes.py \
	lenia_swarm_analysis/morphospace/derive_creature_signals.py \
	lenia_swarm_analysis/morphospace/derive_lenia_features.py \
	lenia_swarm_analysis/morphospace/common_morphology.py \
	lenia_swarm_analysis/topology

.PHONY: check check-swift check-python lint typecheck test-python smoke-deterministic smoke-cluster install-app

check: check-python check-swift

check-swift:
	swift test

check-python: lint test-python

lint:
	uv run ruff check lenia_swarm_analysis Tests

typecheck:
	uv run ty check $(PYTHON_TYPECHECK_PATHS)

test-python:
	uv run pytest

smoke-deterministic:
	./ops/deterministic-smoke.sh

smoke-cluster:
	./ops/smoke-cluster.sh

install-app:
	./ops/install-lenia-studio-app.sh
