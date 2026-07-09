#!/usr/bin/env bash
# One-time host prerequisites for running these benchmarks on a fresh Ubuntu/Debian box.
# The harness venv needs Python >=3.11 (the rocketride SDK imports typing.NotRequired), but Ubuntu
# 22.04 ships 3.10 — so this installs 3.11 (via the deadsnakes PPA when it isn't already present)
# plus the base build tools a clean cloud image lacks. The engine bundles its own runtime; this
# Python is only for the harness venv.
#
#   bash scripts/setup-ubuntu.sh
set -euo pipefail

if ! command -v apt-get >/dev/null 2>&1; then
  echo "setup-ubuntu.sh targets Debian/Ubuntu (apt-get not found) — nothing to do here." >&2
  exit 0
fi

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 && SUDO=sudo || { echo "need root or sudo to apt-get install" >&2; exit 1; }
fi

$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends \
  make curl tar ca-certificates software-properties-common

# Python 3.11 for the harness venv. Skip the PPA if a 3.11 is already present (e.g. Debian 12).
if ! command -v python3.11 >/dev/null 2>&1; then
  $SUDO add-apt-repository -y ppa:deadsnakes/ppa
  $SUDO apt-get update
fi
$SUDO apt-get install -y --no-install-recommends python3.11 python3.11-venv

echo
echo "prereqs installed ($(python3.11 --version 2>&1)). next, from this rocketride-bench/ dir:"
echo "  make provision && make provision-competitors && make start && make smoke"
