# Wonton Soup Poster
Deterministic SVG/PNG poster renders anchored to the `hf00795` block-exact MCTS logs.
Run commands from this directory; Berkeley Mono is preferred, with monospace fallback.
Final hybrid: `python scripts/render_design_takes.py --pair-dir data/hf00795-block-exact --intervention block_exact --take blueprint-ledger --out out/wonton-real-log-block-exact-take-05-blueprint-ledger.svg --manifest out/wonton-real-log-block-exact-take-05-blueprint-ledger.manifest.json`
Rasterize: `magick -density 180 out/wonton-real-log-block-exact-take-05-blueprint-ledger.svg out/wonton-real-log-block-exact-take-05-blueprint-ledger.png`
Other takes: `noir`, `blueprint`, `coral`, `ledger`.
Contact sheets live in `out/*contact-sheet.png`.
Manifests record the theorem, winning tactics, blocked exact attempts, and source files.
