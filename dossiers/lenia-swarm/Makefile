SHELL := /bin/bash

.PHONY: check check-swift check-python lint typecheck test-python smoke-deterministic smoke-cluster install-app

check: check-python check-swift

check-swift:
	swift test

check-python: lint test-python

lint:
	uv run ruff check lenia_swarm_analysis Tests

typecheck:
	uv run ty check

test-python:
	uv run pytest

smoke-deterministic:
	./ops/deterministic-smoke.sh

smoke-cluster:
	./ops/smoke-cluster.sh

install-app:
	./ops/install-lenia-studio-app.sh
