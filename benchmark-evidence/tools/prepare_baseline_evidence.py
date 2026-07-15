#!/usr/bin/env python3
"""Copy Windows raw runs into evidence and derive an outcome-neutral aggregate."""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics


REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "concurrent-work" / "runs-windows"
EVIDENCE = REPO / "benchmark-evidence"
TARGET = EVIDENCE / "baseline" / "concurrent-work"
RAW = TARGET / "raw-runs"
AGGREGATE = TARGET / "aggregate"
EXPECTED = {
    "fault-isolation": 10,
    "concurrent-processing": 10,
    "data-isolation": 10,
    "authoring-effort": 1,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def result_paths(benchmark: str) -> list[Path]:
    if benchmark == "authoring-effort":
        path = SOURCE / benchmark / "results.json"
        return [path] if path.exists() else []
    return sorted((SOURCE / benchmark).glob("run-*/results.json"))


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * percentile_value / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


def stats(values: list[float]) -> dict:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    return {
        "count": len(numeric),
        "min": round(min(numeric), 3) if numeric else None,
        "median": round(statistics.median(numeric), 3) if numeric else None,
        "p95": percentile(numeric, 95),
        "max": round(max(numeric), 3) if numeric else None,
    }


def copy_raw() -> list[dict]:
    manifest: list[dict] = []
    for benchmark in EXPECTED:
        source_root = SOURCE / benchmark
        if not source_root.exists():
            continue
        for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
            relative = source.relative_to(SOURCE)
            if "trace" in relative.parts:
                destination = RAW / Path(str(relative) + ".gz")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.open("rb") as source_handle, gzip.open(
                    destination, "wb", compresslevel=9
                ) as target_handle:
                    shutil.copyfileobj(source_handle, target_handle)
            else:
                destination = RAW / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            manifest.append(
                {
                    "path": destination.relative_to(REPO).as_posix(),
                    "bytes": destination.stat().st_size,
                    "sha256": sha256(destination),
                }
            )
    return manifest


def failure_counts() -> dict:
    path = EVIDENCE / "failures.jsonl"
    rows = []
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                rows.append(json.loads(raw))
    baseline = [row for row in rows if row.get("commandId") == "baseline-isolated-windows-n10"]
    retries: dict[str, int] = {}
    for row in baseline:
        if row.get("event") != "runner_attempt_failed":
            continue
        benchmark = str(row.get("benchmark", "unknown"))
        retries[benchmark] = retries.get(benchmark, 0) + 1
    return {"signals": len(baseline), "retriesByBenchmark": retries}


def aggregate_results() -> dict:
    loaded = {name: [load_json(path) for path in result_paths(name)] for name in EXPECTED}
    counts = {name: len(rows) for name, rows in loaded.items()}
    completeness = {
        name: {"expected": expected, "observed": counts[name], "complete": counts[name] == expected}
        for name, expected in EXPECTED.items()
    }

    fault = loaded["fault-isolation"]
    concurrent = loaded["concurrent-processing"]
    isolation = loaded["data-isolation"]
    authoring = loaded["authoring-effort"][0] if loaded["authoring-effort"] else {}

    rr_by_pool: dict[str, dict] = {}
    for pool_size in (8, 16):
        cells = [
            cell
            for run in concurrent
            for cell in run.get("rocketride", [])
            if cell.get("M") == pool_size
        ]
        rr_by_pool[str(pool_size)] = {
            "wallSeconds": stats([cell.get("wall_s") for cell in cells]),
            "warmupSeconds": stats([cell.get("warm_s") for cell in cells]),
            "p50Milliseconds": stats([cell.get("p50_ms") for cell in cells]),
            "p99Milliseconds": stats([cell.get("p99_ms") for cell in cells]),
            "cleanRuns": sum(
                1
                for cell in cells
                if cell.get("status") == "ok" and int(cell.get("node_errors", 0)) == 0
            ),
            "nodeErrors": sum(int(cell.get("node_errors", 0)) for cell in cells),
        }

    lc_modes = ("batch_shared", "abatch_blocking", "seq")
    langchain = {
        mode: {
            "wallSeconds": stats(
                [run.get("langchain", {}).get(mode, {}).get("wall_s") for run in concurrent]
            ),
            "statuses": sorted(
                {
                    str(run.get("langchain", {}).get(mode, {}).get("status", "missing"))
                    for run in concurrent
                }
            ),
            "okUnits": stats(
                [run.get("langchain", {}).get(mode, {}).get("n_ok") for run in concurrent]
            ),
            "errorUnits": stats(
                [run.get("langchain", {}).get(mode, {}).get("n_err") for run in concurrent]
            ),
        }
        for mode in lc_modes
    }

    data_wall = [run.get("rocketride", {}).get("wall_s") for run in isolation]
    data_warm = [run.get("rocketride", {}).get("warm_s") for run in isolation]
    loss_by_gap: dict[str, list[int]] = {}
    for run in isolation:
        for gap, lost in run.get("verdict_metrics", {}).get("lc_lost_by_gap", {}).items():
            loss_by_gap.setdefault(str(gap), []).append(int(lost))

    gate_issues = [
        f"{name}: expected {item['expected']} results, observed {item['observed']}"
        for name, item in completeness.items()
        if not item["complete"]
    ]
    for index, run in enumerate(concurrent, 1):
        if run.get("parity_gate") != "PASS":
            gate_issues.append(f"concurrent-processing run {index}: AST parity gate did not pass")
        if run.get("langchain_provenance", {}).get("lc_version") != "0.3.86":
            gate_issues.append(f"concurrent-processing run {index}: unexpected langchain-core version")

    return {
        "schemaVersion": "node.rocketride.baseline-aggregate/v1",
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "evidence_complete" if not gate_issues else "evidence_incomplete",
        "officialStatus": "independent_unsubmitted_reproduction",
        "sourceCommit": "43be41acb58558dfae8e2e3deb86d8a00cb1b1c8",
        "completeness": completeness,
        "gateIssues": gate_issues,
        "failureLedger": failure_counts(),
        "faultIsolation": {
            "rocketRideIsolationHeld": sum(
                run.get("verdict_metrics", {}).get("rr_isolation_holds") is True for run in fault
            ),
            "langChainLostAll": sum(
                run.get("verdict_metrics", {}).get("inproc_lost_all") is True for run in fault
            ),
            "repetitions": len(fault),
        },
        "concurrentProcessing": {
            "rocketRideByPool": rr_by_pool,
            "langChain": langchain,
            "appendixNodeErrors": stats(
                [run.get("rr_appendix_threads4", {}).get("node_errors") for run in concurrent]
            ),
        },
        "dataIsolation": {
            "rocketRideWallSeconds": stats(data_wall),
            "rocketRideWarmupSeconds": stats(data_warm),
            "rocketRideCleanRuns": sum(
                run.get("verdict_metrics", {}).get("rr_clean") is True for run in isolation
            ),
            "rocketRideDocsLost": stats(
                [run.get("verdict_metrics", {}).get("rr_docs_lost") for run in isolation]
            ),
            "rocketRideDocsDuplicatedOrLeaked": stats(
                [
                    run.get("verdict_metrics", {}).get("rr_docs_duplicated_or_leaked")
                    for run in isolation
                ]
            ),
            "langChainLostUpdatesByGap": {
                gap: stats(values) for gap, values in sorted(loss_by_gap.items())
            },
        },
        "authoringEffort": authoring.get("verdict_metrics", {}),
    }


def markdown(summary: dict) -> str:
    fault = summary["faultIsolation"]
    concurrent = summary["concurrentProcessing"]
    isolation = summary["dataIsolation"]
    retries = summary["failureLedger"]["retriesByBenchmark"]
    lines = [
        "# Independent Windows Baseline",
        "",
        f"Evidence status: **{summary['status']}**. External status: **{summary['officialStatus']}**.",
        "This is an unchanged local reproduction, not a RocketRide-accepted official result.",
        "",
        "## Completeness",
        "",
        "| Benchmark | Expected | Observed | Complete |",
        "|---|---:|---:|---|",
    ]
    for name, item in summary["completeness"].items():
        lines.append(
            f"| {name} | {item['expected']} | {item['observed']} | {str(item['complete']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Dimensional Results",
            "",
            f"- Fault isolation: RocketRide held in {fault['rocketRideIsolationHeld']}/{fault['repetitions']} runs; the in-process LangChain probe lost all work in {fault['langChainLostAll']}/{fault['repetitions']} runs.",
        ]
    )
    for pool, values in concurrent["rocketRideByPool"].items():
        wall = values["wallSeconds"]
        warm = values["warmupSeconds"]
        lines.append(
            f"- RocketRide pool M={pool}: warm execution median {wall['median']} s, p95 {wall['p95']} s; warm-up median {warm['median']} s; clean {values['cleanRuns']}/{wall['count']}."
        )
    for mode, values in concurrent["langChain"].items():
        wall = values["wallSeconds"]
        lines.append(
            f"- LangChain {mode}: statuses {', '.join(values['statuses'])}; wall median {wall['median']} s, p95 {wall['p95']} s."
        )
    lines.extend(
        [
            f"- Data isolation: RocketRide clean {isolation['rocketRideCleanRuns']}/{summary['completeness']['data-isolation']['observed']}; lost-doc median {isolation['rocketRideDocsLost']['median']}; duplicated/leaked median {isolation['rocketRideDocsDuplicatedOrLeaked']['median']}.",
            f"- Preserved retry signals: {json.dumps(retries, sort_keys=True)}.",
            "",
            "Cold start, warm-up, and warm execution remain separate. Resource fields are reported only where the upstream result emits them.",
        ]
    )
    if summary["gateIssues"]:
        lines.extend(["", "## Evidence Gaps", ""])
        lines.extend(f"- {issue}" for issue in summary["gateIssues"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    if not SOURCE.exists():
        raise SystemExit(f"missing Windows run directory: {SOURCE}")
    manifest = copy_raw()
    AGGREGATE.mkdir(parents=True, exist_ok=True)
    (TARGET / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": "node.rocketride.evidence-manifest/v1",
                "files": manifest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    summary = aggregate_results()
    (AGGREGATE / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (AGGREGATE / "SUMMARY.md").write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"status": summary["status"], "files": len(manifest)}))
    if args.require_complete and summary["status"] != "evidence_complete":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
