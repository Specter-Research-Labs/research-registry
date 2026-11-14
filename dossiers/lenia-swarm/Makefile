SHELL := /bin/bash

.PHONY: build build-debug check check-swift check-python lint typecheck test-python smoke-deterministic smoke-cluster install-app

build:
	swift build -c release --product LeniaCLI
	./ops/write-buildinfo.sh "$$(swift build -c release --show-bin-path)/LeniaCLI"

build-debug:
	swift build --product LeniaCLI
	./ops/write-buildinfo.sh "$$(swift build --show-bin-path)/LeniaCLI"

check: check-python check-swift

# CLI tests run the debug LeniaCLI, which refuses research runs without matching build info,
# so the tests are built first, the binary stamped, and then run without a rebuild.
check-swift:
	swift build --build-tests
	./ops/write-buildinfo.sh "$$(swift build --show-bin-path)/LeniaCLI"
	swift test --skip-build

check-python: lint typecheck test-python

lint:
	uv run ruff check lenia_swarm_analysis Tests

typecheck:
	uv run ty check lenia_swarm_analysis Tests

test-python:
	uv run pytest
	cd tt_backend && uv run pytest

smoke-deterministic:
	./ops/deterministic-smoke.sh

smoke-cluster:
	./ops/smoke-cluster.sh

install-app:
	./ops/install-lenia-studio-app.sh
