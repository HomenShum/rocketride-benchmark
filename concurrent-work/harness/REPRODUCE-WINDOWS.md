# Reproducing the concurrency benchmarks on Windows

The suite was authored on macOS/Linux (see [`REPRODUCE.md`](REPRODUCE.md)). This note covers the
Windows-specific setup. Everything below uses the pinned engine (`server-v3.2.1`) and pinned LangChain
(`langchain-core 0.3.86`), exactly like the macOS/Linux runs.

## Setup (git-bash / MSYS)

```bash
cd rocketride-bench
bash scripts/provision.sh --competitors   # Windows: pulls the win64 .zip engine + builds .venv
                                           # (Scripts/ layout) + real LangChain
ROCKETRIDE_PORT=5565 bash scripts/start_engine.sh    # engine.exe ai/eaas.py --port=5565
```

Notes specific to Windows:
- The pinned release ships a **`win64.zip`** engine; `provision.sh` unzips it to `./engine` (the binary
  is `engine.exe`). macOS/Linux still download the `.tar.gz`.
- If the **RocketRide VS Code extension** is installed, its own engine may already hold `:5565`. Start the
  benchmark engine on a **free port** and point the harness at it:
  ```bash
  ROCKETRIDE_PORT=5566 bash scripts/start_engine.sh
  export ROCKETRIDE_URI="ws://localhost:5566"
  ```
- The runners force UTF-8 stdout (`harness/__init__.py`), so unicode output no longer crashes the
  legacy-codepage (cp1252) Windows console.
- Temp paths default to the OS temp dir (`%LOCALAPPDATA%\Temp`) instead of `/tmp`. Override the shared
  params/db locations with `$ROCKETRIDE_BENCH_PARAMS` / `$BENCH_DB_DIR` if the engine and harness resolve
  different temp dirs (e.g. run under different accounts).

## Run

```bash
# from concurrent-work/harness/ :
python run_isolated_windows.py
```

## Note on the workload SQLite connection

The `concurrent-processing` workload node uses a **per-thread cached SQLite connection**
(`conn="thread_local"` in `nodes/workload/IInstance.py`). SQLite connections are thread-affine, and an
engine may dispatch a pipe's *sequential* documents across more than one OS worker thread on some
platforms (observed on the `win64` `server-v3.2.1` build even at `threads=1`; macOS/Linux use one thread
per pipe). A per-thread connection is safe under either topology, so the headline RocketRide cell runs
clean regardless of OS. The `rr_appendix_threads4` honesty cell deliberately keeps the naive single
shared connection (`conn="module"`) — it reproduces the `sqlite3.ProgrammingError` trap on purpose, to
show what a naive shared handle does when a pipe genuinely uses multiple threads.
