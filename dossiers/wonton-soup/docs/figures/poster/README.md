---
summary: "How the Wonton Soup poster is rendered deterministically from block-exact MCTS logs."
---

# Wonton Soup poster
Deterministic SVG/PNG poster renders anchored to the `hf00795` block-exact MCTS logs.
Run commands from this directory; Berkeley Mono is preferred, with monospace fallback.
Render: `python scripts/render_poster.py --pair-dir data/hf00795-block-exact --intervention block_exact --out out/wonton-real-log-block-exact-take-05-blueprint-ledger.svg --manifest out/wonton-real-log-block-exact-take-05-blueprint-ledger.manifest.json`
Rasterize: `magick -density 180 out/wonton-real-log-block-exact-take-05-blueprint-ledger.svg out/wonton-real-log-block-exact-take-05-blueprint-ledger.png`
Manifests record the theorem, winning tactics, blocked exact attempts, and source files.
