#!/usr/bin/env bash
set -euo pipefail

SOURCE_SHA="43be41acb58558dfae8e2e3deb86d8a00cb1b1c8"
SOURCE_URL="https://github.com/rocketride-org/rocketride-benchmark.git"
PYTHON_HOST="${PYTHON_HOST:-python3.11}"
RUN_ID="${LINUX_RUN_ID:-linux-$(date -u +%Y%m%dT%H%M%SZ)}"
WORK_ROOT="${HOME}/.cache/rocketride-node-study/${RUN_ID}"
REPO="${WORK_ROOT}/rocketride-benchmark"
EXPORT_PARENT="${LINUX_EXPORT_ROOT:?LINUX_EXPORT_ROOT must be an absolute WSL path}"
EXPORT_ROOT="${EXPORT_PARENT}/${RUN_ID}"
BENCH="${REPO}/concurrent-work/harness/rocketride-bench"
RUNS="${REPO}/concurrent-work/runs"

mkdir -p "${WORK_ROOT}" "${EXPORT_ROOT}"

wait_http() {
  local port="$1" deadline=$((SECONDS + 180)) code
  while [ "${SECONDS}" -lt "${deadline}" ]; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${port}/ping" 2>/dev/null || true)"
    if [ -n "${code}" ] && [ "${code}" != "000" ]; then
      echo "external readiness confirmed on :${port} (HTTP ${code})"
      return 0
    fi
    sleep 1
  done
  echo "engine did not become externally ready on :${port}" >&2
  return 1
}

export_partial() {
  local status=$?
  set +e
  if [ -d "${BENCH}" ]; then
    (cd "${BENCH}" && bash scripts/stop_engine.sh >/dev/null 2>&1) || true
  fi
  mkdir -p "${EXPORT_ROOT}/raw" "${EXPORT_ROOT}/logs"
  [ -d "${RUNS}" ] && cp -a "${RUNS}" "${EXPORT_ROOT}/raw/concurrent-work-runs"
  [ -d "${REPO}/lines-of-code" ] && cp -a "${REPO}/lines-of-code" "${EXPORT_ROOT}/raw/lines-of-code"
  find "${EXPORT_ROOT}/raw" -type f -path '*/trace/*' ! -name '*.gz' -exec gzip -9 {} \;
  [ -f "${WORK_ROOT}/full-run.log" ] && cp "${WORK_ROOT}/full-run.log" "${EXPORT_ROOT}/logs/full-run.log"
  [ -f "${WORK_ROOT}/smoke.log" ] && cp "${WORK_ROOT}/smoke.log" "${EXPORT_ROOT}/logs/smoke.log"
  [ -f "${WORK_ROOT}/lines-of-code.log" ] && cp "${WORK_ROOT}/lines-of-code.log" "${EXPORT_ROOT}/logs/lines-of-code.log"
  [ -f "${WORK_ROOT}/aggregate.log" ] && cp "${WORK_ROOT}/aggregate.log" "${EXPORT_ROOT}/logs/aggregate.log"
  [ -f "${REPO}/concurrent-work/README.md" ] && cp "${REPO}/concurrent-work/README.md" "${EXPORT_ROOT}/upstream-aggregate.md"
  if [ -d "${REPO}/.git" ]; then
    git -C "${REPO}" status --porcelain=v1 > "${EXPORT_ROOT}/post-run-status.txt"
    git -C "${REPO}" diff --name-only > "${EXPORT_ROOT}/tracked-files-changed.txt"
  fi
  printf '{"schemaVersion":"node.rocketride.linux-run/v1","runId":"%s","sourceCommit":"%s","exitCode":%d}\n' \
    "${RUN_ID}" "${SOURCE_SHA}" "${status}" > "${EXPORT_ROOT}/completion.json"
  "${PYTHON_HOST}" - "${EXPORT_ROOT}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
files = []
for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "manifest.json"):
    files.append(
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
(root / "manifest.json").write_text(
    json.dumps({"schemaVersion": "node.rocketride.linux-manifest/v1", "files": files}, indent=2)
    + "\n",
    encoding="utf-8",
)
PY
  return "${status}"
}
trap export_partial EXIT

for command in git curl tar make timeout gzip; do
  command -v "${command}" >/dev/null || {
    echo "missing required command: ${command}" >&2
    exit 2
  }
done
command -v "${PYTHON_HOST}" >/dev/null || {
  echo "missing required Python interpreter: ${PYTHON_HOST}" >&2
  exit 2
}

"${PYTHON_HOST}" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required; run scripts/setup-ubuntu.sh first")
PY

git clone --no-checkout "${SOURCE_URL}" "${REPO}"
git -C "${REPO}" checkout --detach "${SOURCE_SHA}"
test "$(git -C "${REPO}" rev-parse HEAD)" = "${SOURCE_SHA}"

git -C "${REPO}" rev-parse HEAD > "${EXPORT_ROOT}/upstream-sha.txt"
git -C "${REPO}" status --porcelain=v1 > "${EXPORT_ROOT}/pre-run-status.txt"
"${PYTHON_HOST}" - "${REPO}" "${EXPORT_ROOT}" <<'PY'
import json
import os
import platform
from pathlib import Path
import subprocess
import sys

repo = Path(sys.argv[1])
output = Path(sys.argv[2]) / "environment.json"
value = {
    "schemaVersion": "node.rocketride.linux-environment/v1",
    "sourceCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
    "platform": platform.platform(),
    "machine": platform.machine(),
    "python": platform.python_version(),
    "kernel": platform.release(),
    "processor": platform.processor(),
    "cpuCount": os.cpu_count(),
    "wslDistro": os.environ.get("WSL_DISTRO_NAME"),
    "benchmarkEnvironment": {
        "REPS": "10",
        "MAX_ATTEMPTS": "5",
        "BENCH_MS": "8,16",
        "BENCH_M": "32",
        "ROCKETRIDE_PORT": "5565",
    },
}
meminfo = Path("/proc/meminfo")
if meminfo.exists():
    value["meminfo"] = meminfo.read_text(encoding="utf-8").splitlines()[:4]
output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
PY

(cd "${REPO}/lines-of-code" && "${PYTHON_HOST}" measure.py) 2>&1 | tee "${WORK_ROOT}/lines-of-code.log"

cd "${BENCH}"
bash scripts/provision.sh
"${BENCH}/.venv/bin/python" -m pip install -r requirements-competitors.txt
"${BENCH}/.venv/bin/python" -m pip freeze --all > "${EXPORT_ROOT}/requirements-resolved.txt"
sha256sum "${BENCH}/engine/engine" > "${EXPORT_ROOT}/engine-sha256.txt"
"${BENCH}/engine/engine" --version > "${EXPORT_ROOT}/engine-version.txt" 2>&1 || true

ENGINE_DIR="${BENCH}/engine" bash scripts/start_engine.sh
wait_http 5565
"${BENCH}/.venv/bin/python" groups/robustness-and-isolation/fault-isolation/run.py \
  2>&1 | tee "${WORK_ROOT}/smoke.log"

mv "${RUNS}" "${WORK_ROOT}/upstream-reference-runs"
mkdir -p "${RUNS}"

cd "${REPO}/concurrent-work/harness"
BENCH_PY="${BENCH}/.venv/bin/python" REPS=10 MAX_ATTEMPTS=5 bash run_isolated.sh \
  2>&1 | tee "${WORK_ROOT}/full-run.log"
"${PYTHON_HOST}" aggregate.py 2>&1 | tee "${WORK_ROOT}/aggregate.log"

"${PYTHON_HOST}" - "${RUNS}" <<'PY'
from pathlib import Path
import sys

runs = Path(sys.argv[1])
expected = {"fault-isolation": 10, "concurrent-processing": 10, "data-isolation": 10}
issues = []
for benchmark, count in expected.items():
    observed = len(list((runs / benchmark).glob("run-*/results.json")))
    print(f"{benchmark}: {observed}/{count}")
    if observed != count:
        issues.append(f"{benchmark}: expected {count}, observed {observed}")
authoring = runs / "authoring-effort" / "results.json"
print(f"authoring-effort: {'1/1' if authoring.is_file() else '0/1'}")
if not authoring.is_file():
    issues.append("authoring-effort: expected 1, observed 0")
if issues:
    raise SystemExit("incomplete supported-Linux run: " + "; ".join(issues))
PY

echo "supported Linux reproduction complete: ${RUN_ID}"
