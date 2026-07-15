# concurrent-work — RocketRide vs base LangChain on concurrent **stateful** work

**The claim, scoped tightly:** on concurrent *stateful* work, **stock RocketRide is safe by default** — its per-pipe process topology does, with zero concurrency code, what a LangChain user has to *know* to do (thread-affinity, a lock, a process pool). Stock LangChain's most natural idioms **crash, silently lose data, or lose everything to one fault.**

Every number runs **real LangChain** (`lc_version` per row), **AST-identical work** (AST parity gate), and a **native trace**, with full provenance — re-run from [`harness/`](harness/).

## Scorecard — *stock vs stock*

| Benchmark | Stock LangChain (default idiom) | **Stock RocketRide (default)** |
|---|---|---|
| [concurrent-processing](runs/concurrent-processing/REPORT.md) | `.batch` (shared conn) **CRASHES 0/64** (`sqlite3.ProgrammingError`); `.abatch`/seq serialize **7.5 s** | ✅ **safe — M=16 0.867 s (range 0.807–1.049), 0 errors** (10/10 reps clean) |
| [fault-isolation](runs/fault-isolation/REPORT.md) | in-process `.abatch` (one interpreter) **loses ALL 0/4** to one crash | ✅ **survives** — only the crashing run dies (10/10 reps) |
| [data-isolation](runs/data-isolation/REPORT.md) | one shared dict, 32 workers → **silently loses 32–244 of 256** (12–95%) | ✅ **0 lost / 0 leaked** — each pipe its own data (10/10 reps) |
| [authoring-effort](runs/authoring-effort/REPORT.md) | **14–17** imperative lines + up to **5** hidden decisions; one crashes, one silently serializes, one is slow — none deliver concurrency | ✅ **0** imperative concurrency lines (validated `.pipe`) |

*Fresh local 10× reps (crash/pick/instance; authoring is static). Runtime `3.2.1.30 hash: 114509c6` · x86_64 · langchain-core `0.3.86`. **Ratios reproduce; absolute values vary.***

## Why this is fair

- **Same work, both sides** — the per-doc work is identical (an AST parity gate aborts if the per-doc processing function ever diverges). The only difference is *how each framework is used by default* — of LangChain's three natural idioms one crashes, one silently serializes, and one is slow, while RocketRide's default is safe by construction.
- **Pool size is a disclosed run parameter** (pick M={8,16}, instance M=32) for runtime stability; the isolation claims are size-independent. See [`harness/NOTICE`](harness/NOTICE).

## Read at any depth

- **This file** — the scorecard.
- **[`runs/`](runs/)** `<bench>/REPORT.md` — Verdict · Hypothesis · Method · Results · Provenance, with committed `results.json` + native `trace/` (10 reps each for the timed/stateful benches).
- **[`harness/`](harness/)** — the runners + everything to reproduce ([`REPRODUCE.md`](harness/REPRODUCE.md)).
