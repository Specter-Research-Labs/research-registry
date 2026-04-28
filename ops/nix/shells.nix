{ system ? "aarch64-darwin", pkgs ? null }:
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);

  pinnedPkgs =
    if pkgs != null then
      pkgs
    else
      import (builtins.fetchTree lock.nodes.nixpkgs.locked) { inherit system; };

  lib = pinnedPkgs.lib;

  pythonAttrByVersion = {
    "3.11" = "python311";
    "3.12" = "python312";
    "3.13" = "python313";
  };

  pythonFor = version:
    let
      attr =
        pythonAttrByVersion.${version}
          or (throw "Unsupported Python version for Specter shell: ${version}");
    in
    builtins.getAttr attr pinnedPkgs;

  appleShellHook = ''
    unset NIX_CFLAGS_COMPILE NIX_CFLAGS_LINK NIX_LDFLAGS
    unset DEVELOPER_DIR SDKROOT TOOLCHAINS
    if [ -n "$LIBRARY_PATH" ]; then
      export LIBRARY_PATH="${pinnedPkgs.libiconv}/lib:$LIBRARY_PATH"
    else
      export LIBRARY_PATH="${pinnedPkgs.libiconv}/lib"
    fi
    export ELAN_DEFAULT_TOOLCHAIN="leanprover/lean4:v4.25.0"

    if [ -z "$MLX_METAL_PATH" ]; then
      repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
      if [ -z "$repo_root" ]; then
        repo_root="$PWD"
      fi

      for p in \
        "$repo_root/dossiers/lenia-swarm/.build/arm64-apple-macosx/debug/mlx.metallib" \
        "$repo_root/dossiers/lenia-swarm/.build/mlx-metallib/mlx/backend/metal/kernels/mlx.metallib" \
        "$repo_root/dossiers/lenia-playground/.venv/lib/python3.13/site-packages/mlx/lib/mlx.metallib"; do
        if [ -f "$p" ]; then
          export MLX_METAL_PATH="$p"
          break
        fi
      done

      if [ -z "$MLX_METAL_PATH" ] && command -v python3 >/dev/null 2>&1; then
        mlx_py_path="$(python3 - <<'PY'
import importlib.util
import os

spec = importlib.util.find_spec("mlx")
if spec and spec.submodule_search_locations:
    base = spec.submodule_search_locations[0]
    path = os.path.join(base, "lib", "mlx.metallib")
    if os.path.isfile(path):
        print(path)
PY
)"
        if [ -n "$mlx_py_path" ]; then
          export MLX_METAL_PATH="$mlx_py_path"
        fi
      fi

      unset repo_root mlx_py_path
    fi

  '';

  mkBootstrapHook =
    {
      uvSync ? false,
      cargoFetch ? false,
      swiftResolve ? false,
      lakeUpdate ? false,
      extraHook ? "",
    }:
    ''
      ${lib.optionalString uvSync ''
        if [ -f pyproject.toml ] && command -v uv >/dev/null 2>&1 && command -v python >/dev/null 2>&1; then
          uv sync --python "$(command -v python)"
        fi
      ''}
      ${lib.optionalString cargoFetch ''
        if [ -f Cargo.toml ] && command -v cargo >/dev/null 2>&1; then
          cargo fetch --locked
        fi
      ''}
      ${lib.optionalString swiftResolve ''
        if [ -f Package.swift ] && command -v swift >/dev/null 2>&1; then
          swift package resolve
        fi
      ''}
      ${lib.optionalString lakeUpdate ''
        if [ -f lakefile.lean ] && command -v lake >/dev/null 2>&1; then
          lake update
        fi
      ''}
      ${extraHook}
    '';

  xcodebuildWrapper = pinnedPkgs.writeShellScriptBin "xcodebuild" ''
    set -euo pipefail
    while IFS= read -r v; do unset "$v"; done < <(env | awk -F= '/^NIX_/ {print $1}')
    unset CC CXX DEVELOPER_DIR SDKROOT TOOLCHAINS LD LD_DYLD_PATH LIBRARY_PATH
    DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer" exec /usr/bin/xcodebuild "$@"
  '';

  swiftWrapper = pinnedPkgs.writeShellScriptBin "swift" ''
    set -euo pipefail
    while IFS= read -r v; do unset "$v"; done < <(env | awk -F= '/^NIX_/ {print $1}')
    unset CC CXX DEVELOPER_DIR SDKROOT TOOLCHAINS LD LD_DYLD_PATH LIBRARY_PATH
    DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer" exec /usr/bin/xcrun swift "$@"
  '';

  commonPackages = with pinnedPkgs; [
    cmake
    elan
    uv
    ruff
    ty
    typst
    swiftWrapper
    xcodebuildWrapper
  ];
in
rec {
  pkgs = pinnedPkgs;

  rustPackages = with pinnedPkgs; [
    cargo
    rustc
    pkg-config
  ];

  wontonPackages = with pinnedPkgs; [
    duckdb
    coqPackages_8_20.coq
    coqPackages_8_20.serapi
    coqPackages_8_20.coq-lsp
    eprover
    gnutar
    gmp
    opam
    pkg-config
    pkgconf
    vampire
  ];

  mkProjectShell =
    {
      pythonVersion ? null,
      extraPackages ? [],
      bootstrap ? { },
      extraShellHook ? "",
    }:
    let
      pythonPackages =
        if pythonVersion == null then
          [ ]
        else
          [ (pythonFor pythonVersion) ];
    in
    pinnedPkgs.mkShell {
      packages = commonPackages ++ pythonPackages ++ extraPackages;
      shellHook = appleShellHook + mkBootstrapHook bootstrap + extraShellHook;
    };

  mkRootShell = mkProjectShell {
    pythonVersion = "3.12";
  };

  mkPythonProjectShell =
    {
      pythonVersion,
      extraPackages ? [],
      bootstrap ? { },
      extraShellHook ? "",
    }:
    mkProjectShell {
      inherit pythonVersion extraPackages extraShellHook;
      bootstrap = bootstrap // { uvSync = true; };
    };

  mkRustProjectShell =
    {
      extraPackages ? [ ],
      bootstrap ? { },
      extraShellHook ? "",
    }:
    mkProjectShell {
      extraPackages = rustPackages ++ extraPackages;
      inherit extraShellHook;
      bootstrap = bootstrap // { cargoFetch = true; };
    };

  mkLeanProjectShell =
    {
      extraPackages ? [ ],
      bootstrap ? { },
      extraShellHook ? "",
    }:
    mkProjectShell {
      inherit extraPackages extraShellHook;
      bootstrap = bootstrap // { lakeUpdate = true; };
    };
}
