#!/usr/bin/env bash
# One-time host prerequisites for running these benchmarks on a fresh Ubuntu/Debian box.
# A clean cloud image is typically missing python3-venv / pip / make, which `make provision`
# needs. Ubuntu 22.04's system Python 3.10 is sufficient: the pinned harness deps require
# >=3.10 (rocketride 1.2.0) / >=3.9 (langchain-core 0.3.86), and the engine bundles its own
# runtime — so no PPA / newer Python is needed.
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
  python3 python3-venv python3-pip make curl tar ca-certificates

echo
echo "prereqs installed ($(python3 --version 2>&1)). next, from this rocketride-bench/ dir:"
echo "  make provision && make provision-competitors && make start && make smoke"
