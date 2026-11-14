from pathlib import Path

DOSSIER_ROOT = Path(__file__).resolve().parents[1]
# SwiftPM keeps .build/release pointing at the active build system's products, so this path
# holds for both the native and the xcbuild layout.
LENIA_CLI = DOSSIER_ROOT / ".build" / "release" / "LeniaCLI"
