#!/usr/bin/env bash
# Provision a reproducible environment: locate-or-download the PINNED RocketRide runtime and
# build the harness venv. No credentials needed — the engine is a public MIT release.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RR_ENGINE_VERSION="${RR_ENGINE_VERSION:-3.2.1}"
ENGINE_DIR="${ENGINE_DIR:-$REPO_DIR/engine}"

# Engine binary name differs on Windows (git-bash/MSYS): engine.exe vs engine.
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) ENGINE_BIN=engine.exe ;; *) ENGINE_BIN=engine ;; esac

# 1) Engine: use an existing one, else download the prebuilt for this OS/arch.
if [ -x "$ENGINE_DIR/$ENGINE_BIN" ]; then
  echo "engine present: $ENGINE_DIR/$ENGINE_BIN"
else
  os="$(uname -s)"; arch="$(uname -m)"
  ext=tar.gz
  case "$os/$arch" in
    Darwin/arm64) plat=darwin-arm64 ;;
    Darwin/x86_64) plat=darwin-x64 ;;
    Linux/*)      plat=linux-x64 ;;
    # Windows via git-bash/MSYS/Cygwin: the release ships a .zip (not .tar.gz) that extracts
    # engine.exe at the archive root (no leading component to strip).
    MINGW*/*|MSYS*/*|CYGWIN*/*) plat=win64; ext=zip ;;
    *) echo "unsupported $os/$arch; use Docker (ghcr.io/rocketride-org/rocketride-engine)"; exit 1 ;;
  esac
  asset="rocketride-server-v${RR_ENGINE_VERSION}-${plat}.${ext}"
  url="https://github.com/rocketride-org/rocketride-server/releases/download/server-v${RR_ENGINE_VERSION}/${asset}"
  echo "downloading $url"
  mkdir -p "$ENGINE_DIR"
  tmp_asset="${TMPDIR:-/tmp}/$asset"
  curl -fL "$url" -o "$tmp_asset"
  if [ "$ext" = "zip" ]; then
    unzip -oq "$tmp_asset" -d "$ENGINE_DIR"        # win64.zip: engine.exe at the root
  else
    # Release tarballs are FLAT — the engine binary + ai/ + lib/ ... sit at the archive root (same
    # as the win64 zip), so do NOT --strip-components: it silently drops the top-level `engine` file
    # (a single-component path), leaving a runtime with no launcher. Extract as-is; if a future
    # release wraps everything in one top dir, flatten that so $ENGINE_DIR/engine still resolves.
    tar -xzf "$tmp_asset" -C "$ENGINE_DIR"
    if [ ! -e "$ENGINE_DIR/$ENGINE_BIN" ]; then
      inner="$(find "$ENGINE_DIR" -mindepth 2 -maxdepth 2 -name "$ENGINE_BIN" 2>/dev/null | head -1)"
      [ -n "$inner" ] && { d="$(dirname "$inner")"; ( cd "$d" && tar -cf - . ) | ( cd "$ENGINE_DIR" && tar -xf - ); rm -rf "$d"; }
    fi
  fi
  echo "extracted engine -> $ENGINE_DIR"
fi
( cd "$ENGINE_DIR" && "./$ENGINE_BIN" --version 2>&1 | head -1 ) || true

# NOTE: native prebuilts exist for darwin-arm64/darwin-x64/linux-x64/win64. On Apple Silicon the
# Docker image (linux-x64) runs under emulation — for fair Mac numbers use the darwin-arm64
# prebuilt; for fair Docker numbers run on a linux-x64 host and containerize the competitors too.

# 2) Harness venv. venv lays python under Scripts/ on Windows, bin/ elsewhere.
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) VENV_PY="$REPO_DIR/.venv/Scripts/python.exe" ;;
                     *) VENV_PY="$REPO_DIR/.venv/bin/python" ;; esac
if [ ! -x "$VENV_PY" ]; then
  # The rocketride SDK needs Python >=3.11 (it imports typing.NotRequired). Ubuntu 22.04's default
  # python3 is 3.10 and fails at import — prefer python3.11 when present; honor an explicit $PYTHON.
  PYBIN="${PYTHON:-}"
  [ -n "$PYBIN" ] || { command -v python3.11 >/dev/null 2>&1 && PYBIN=python3.11 || PYBIN=python3; }
  echo "creating venv with $PYBIN ($("$PYBIN" --version 2>&1))"
  "$PYBIN" -m venv "$REPO_DIR/.venv"
fi
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r "$REPO_DIR/requirements.txt"
echo "venv ready: $REPO_DIR/.venv  ($("$VENV_PY" -c 'import rocketride; print("rocketride", rocketride.__version__)'))"

# 3) Optional: the REAL LangChain competitor baseline for the Tier-1 head-to-heads (no infra, no
#    creds — the model is a fixed-latency mock). `make provision-competitors` does the same thing.
if [ "${1:-}" = "--competitors" ]; then
  echo "installing competitor baselines (real LangChain)"
  "$VENV_PY" -m pip install --quiet -r "$REPO_DIR/requirements-competitors.txt"
  echo "competitors ready: $("$VENV_PY" -c 'import langchain_core; print("langchain-core", langchain_core.__version__)')"
fi

echo
echo "provisioned. next:  make start  &&  make smoke"
echo "competitor head-to-heads (optional):  make provision-competitors  &&  make run-competitive"
