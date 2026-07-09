#!/usr/bin/env python3
"""Windows-native 10x runner for the concurrency benchmarks — the counterpart to run_isolated.sh.

run_isolated.sh can't drive a Windows run: it writes into ../runs/ (the committed macOS tree),
hardcodes port 5565 (often held by the VS Code extension's engine), and uses lsof / .venv/bin/python
/ --host=0.0.0.0. This driver mirrors its logic on Windows:

  - engine lifecycle on a FREE port (default 5566) via psutil (find listener -> terminate tree ->
    relaunch engine.exe ai/eaas.py --host=127.0.0.1 --port=PORT -> poll /ping -> record pid),
  - .venv/Scripts/python.exe for the benches, ROCKETRIDE_URI pointed at the chosen port,
  - fault-isolation xREPS back-to-back (no restart), authoring-effort x1 (static),
    concurrent-processing xREPS @ M={8,16} and data-isolation xREPS @ M=32, each warm-pool rep on a
    freshly-restarted+primed engine (retry up to MAX_ATTEMPTS),
  - outputs into ../runs-windows/<bench>/run-NN/ (results.json + captured run.log); trace/ kept for
    run-01 only (gzip it afterwards to match the committed convention).

Env: REPS (default 10), MAX_ATTEMPTS (5), ROCKETRIDE_PORT (5566), RESTART=1 (set 0 to reuse a single
warm engine — the disclosed fallback; correctness outcomes are restart-independent, only warm-pool
timing hygiene differs).

Run:  ./.venv/Scripts/python.exe ../run_isolated_windows.py
      (from rocketride-bench/, with the engine provisioned + competitors installed)
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

import psutil

HERE = os.path.dirname(os.path.abspath(__file__))          # concurrent-work/harness
BR = os.path.join(HERE, "rocketride-bench")
RUNS_WIN = os.path.join(HERE, "..", "runs-windows")
ENGINE_DIR = os.environ.get("ENGINE_DIR") or os.path.join(BR, "engine")
ENGINE_EXE = os.path.join(ENGINE_DIR, "engine.exe")
PY = os.environ.get("BENCH_PY") or os.path.join(BR, ".venv", "Scripts", "python.exe")
PORT = int(os.environ.get("ROCKETRIDE_PORT", "5566"))
URI = "ws://localhost:%d" % PORT
REPS = int(os.environ.get("REPS", "10"))
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "5"))
DO_RESTART = os.environ.get("RESTART", "1") != "0"
PARAMS = os.path.join(BR, "results", "bench_params.json")   # explicit shared path (engine + harness)
ENGINE_LOG = os.path.join(BR, "results", "engine_win.log")

CRASH = "groups/robustness-and-isolation/fault-isolation"
PICK = "groups/scale-and-concurrency/concurrent-processing"
INST = "groups/scale-and-concurrency/data-isolation"
AUTH = "groups/scale-and-concurrency/authoring-effort"

# One environment shared by the engine (so task subprocesses inherit the params path + URI) and the
# bench runners (so config.URI / the node's params path agree).
BASE_ENV = dict(os.environ)
BASE_ENV["ROCKETRIDE_URI"] = URI
BASE_ENV["ROCKETRIDE_PORT"] = str(PORT)
BASE_ENV["ROCKETRIDE_BENCH_PARAMS"] = PARAMS
BASE_ENV["ENGINE_DIR"] = ENGINE_DIR
BASE_ENV["PYTHONIOENCODING"] = "utf-8"

_engine_proc = None


def _listener_pid(port):
    for c in psutil.net_connections(kind="inet"):
        if c.laddr and c.laddr.port == port and c.status == "LISTEN":
            return c.pid
    return None


def stop_engine():
    global _engine_proc
    pid = _listener_pid(PORT)
    if pid:
        try:
            p = psutil.Process(pid)
            for k in p.children(recursive=True):
                try:
                    k.terminate()
                except psutil.Error:
                    pass
            p.terminate()
            psutil.wait_procs([p], timeout=8)
        except psutil.Error:
            pass
    _engine_proc = None


def _healthy():
    try:
        urllib.request.urlopen("http://localhost:%d/ping" % PORT, timeout=2)
        return True
    except urllib.error.HTTPError:   # 401 etc. == a live server
        return True
    except Exception:                # connection refused == not up yet
        return False


def start_engine(timeout_s=90):
    global _engine_proc
    os.makedirs(os.path.dirname(ENGINE_LOG), exist_ok=True)
    logf = open(ENGINE_LOG, "ab")
    _engine_proc = subprocess.Popen(
        [ENGINE_EXE, "ai/eaas.py", "--host=127.0.0.1", "--port=%d" % PORT],
        cwd=ENGINE_DIR, stdout=logf, stderr=logf, env=BASE_ENV)
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if _healthy():
            pid = _listener_pid(PORT)
            if pid:
                with open(os.path.join(BR, "results", "engine.pid"), "w") as f:
                    f.write(str(pid))
            return True
        time.sleep(1.0)
    return False


def restart():
    stop_engine()
    time.sleep(2)
    if not start_engine():
        print("    [engine did not come healthy after restart]", flush=True)
    time.sleep(3)


def prime():
    """Wake the engine's pipe machinery with one quick single-pipe run."""
    try:
        subprocess.run([PY, os.path.join(BR, CRASH, "run.py")],
                       cwd=BR, env=BASE_ENV, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=90)
    except subprocess.SubprocessError:
        pass


def copy_out(rel, out_dir, keep_trace):
    src = os.path.join(BR, rel, "results.json")
    if not os.path.isfile(src):
        return False
    shutil.copy(src, out_dir)
    tr = os.path.join(BR, rel, "trace")
    if keep_trace and os.path.isdir(tr):
        shutil.copytree(tr, os.path.join(out_dir, "trace"), dirs_exist_ok=True)
    return True


def run_bench(rel, key, run_name, env_extra, restart_first, keep_trace, flat=False):
    out = os.path.join(RUNS_WIN, key) if flat else os.path.join(RUNS_WIN, key, run_name)
    os.makedirs(out, exist_ok=True)
    env = dict(BASE_ENV)
    env.update(env_extra or {})
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if restart_first and DO_RESTART:
            restart()
            prime()
        with open(os.path.join(out, "run.log"), "w", encoding="utf-8") as log:
            try:
                rc = subprocess.run([PY, os.path.join(BR, rel, "run.py")], cwd=BR, env=env,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=360).returncode
            except subprocess.TimeoutExpired:
                rc = -1
                log.write("\n[TIMEOUT after 360s]\n")
        if rc == 0 and copy_out(rel, out, keep_trace):
            print("  OK   %s %s (attempt %d)" % (key, run_name, attempt), flush=True)
            return True
        print("  ...retry %s %s (attempt %d, rc=%s)" % (key, run_name, attempt, rc), flush=True)
    print("  FAIL %s %s after %d attempts" % (key, run_name, MAX_ATTEMPTS), flush=True)
    return False


def main():
    for tool in (ENGINE_EXE, PY):
        if not os.path.exists(tool):
            sys.exit("missing %s — provision the engine + venv first" % tool)
    os.makedirs(RUNS_WIN, exist_ok=True)

    print("=== starting engine on :%d ===" % PORT, flush=True)
    stop_engine()                              # clear any stale listener on our port first
    time.sleep(1)
    if not start_engine():
        sys.exit("engine did not become healthy on :%d" % PORT)

    print("=== fault-isolation x%d (back-to-back, no restart) ===" % REPS, flush=True)
    for r in range(1, REPS + 1):
        run_bench(CRASH, "fault-isolation", "run-%02d" % r, {}, False, False)

    print("=== authoring-effort x1 (static) ===", flush=True)
    run_bench(AUTH, "authoring-effort", "", {}, False, False, flat=True)

    print("=== concurrent-processing x%d @ M={8,16} (restart+prime+retry) ===" % REPS, flush=True)
    for r in range(1, REPS + 1):
        keep = (r == 1)                       # trace kept for run-01 only (convention)
        run_bench(PICK, "concurrent-processing", "run-%02d" % r, {"BENCH_MS": "8,16"}, True, keep)

    print("=== data-isolation x%d @ M=32 (restart+prime+retry) ===" % REPS, flush=True)
    for r in range(1, REPS + 1):
        keep = (r == 1)
        run_bench(INST, "data-isolation", "run-%02d" % r, {"BENCH_M": "32"}, True, keep)

    stop_engine()
    print("=== 10x RUN DONE -> %s ===" % os.path.abspath(RUNS_WIN), flush=True)


if __name__ == "__main__":
    main()
