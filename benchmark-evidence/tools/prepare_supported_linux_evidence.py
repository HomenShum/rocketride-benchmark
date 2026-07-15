#!/usr/bin/env python3
"""Verify and summarize the supported Linux reproduction without grading outcomes."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import statistics


REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "benchmark-evidence"
LINUX = EVIDENCE / "baseline" / "linux"
SOURCE_SHA = "43be41acb58558dfae8e2e3deb86d8a00cb1b1c8"
EXPECTED = {
    "fault-isolation": 10,
    "concurrent-processing": 10,
    "data-isolation": 10,
    "authoring-effort": 1,
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], p: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p / 100
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return round(ordered[low] * (1 - weight) + ordered[high] * weight, 3)


def stats(values) -> dict:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    return {
        "count": len(numeric),
        "median": round(statistics.median(numeric), 3) if numeric else None,
        "p95": percentile(numeric, 95),
        "min": round(min(numeric), 3) if numeric else None,
        "max": round(max(numeric), 3) if numeric else None,
    }


def result_paths(run_root: Path, benchmark: str) -> list[Path]:
    root = run_root / "raw" / "concurrent-work-runs" / benchmark
    if benchmark == "authoring-effort":
        path = root / "results.json"
        return [path] if path.is_file() else []
    return sorted(root.glob("run-*/results.json"))


def verify_export_manifest(run_root: Path) -> list[str]:
    issues = []
    manifest_path = run_root / "manifest.json"
    if not manifest_path.is_file():
        return ["export manifest is missing"]
    for item in load_json(manifest_path).get("files", []):
        path = (run_root / item["path"]).resolve()
        if run_root.resolve() not in path.parents:
            issues.append(f"manifest path escapes run root: {item['path']}")
        elif not path.is_file():
            issues.append(f"manifest file is missing: {item['path']}")
        elif path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            issues.append(f"manifest hash mismatch: {item['path']}")
    return issues


def failure_signals() -> dict:
    ledger = EVIDENCE / "failures.jsonl"
    rows = []
    if ledger.is_file():
        rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line]
    selected = [row for row in rows if row.get("commandId") == "baseline-supported-linux-n10"]
    return {
        "count": len(selected),
        "retries": sum(row.get("event") == "runner_attempt_failed" for row in selected),
        "failures": selected,
    }


def aggregate(run_root: Path) -> dict:
    loaded = {
        benchmark: [load_json(path) for path in result_paths(run_root, benchmark)]
        for benchmark in EXPECTED
    }
    completeness = {
        benchmark: {
            "expected": expected,
            "observed": len(loaded[benchmark]),
            "complete": len(loaded[benchmark]) == expected,
        }
        for benchmark, expected in EXPECTED.items()
    }
    issues = verify_export_manifest(run_root)
    completion = load_json(run_root / "completion.json") if (run_root / "completion.json").is_file() else {}
    if completion.get("exitCode") != 0:
        issues.append(f"Linux runner exit code is {completion.get('exitCode', 'missing')}")
    if completion.get("sourceCommit") != SOURCE_SHA:
        issues.append("Linux runner source commit does not match the frozen SHA")
    for benchmark, item in completeness.items():
        if not item["complete"]:
            issues.append(
                f"{benchmark}: expected {item['expected']} results, observed {item['observed']}"
            )

    concurrent = loaded["concurrent-processing"]
    for index, result in enumerate(concurrent, 1):
        if result.get("parity_gate") != "PASS":
            issues.append(f"concurrent-processing run {index}: AST parity gate did not pass")
        if result.get("langchain_provenance", {}).get("lc_version") != "0.3.86":
            issues.append(f"concurrent-processing run {index}: unexpected LangChain version")

    rr_by_pool = {}
    for pool in (8, 16):
        cells = [
            cell
            for result in concurrent
            for cell in result.get("rocketride", [])
            if cell.get("M") == pool
        ]
        rr_by_pool[str(pool)] = {
            "wallSeconds": stats(cell.get("wall_s") for cell in cells),
            "warmupSeconds": stats(cell.get("warm_s") for cell in cells),
            "p50Milliseconds": stats(cell.get("p50_ms") for cell in cells),
            "p99Milliseconds": stats(cell.get("p99_ms") for cell in cells),
            "cleanRuns": sum(cell.get("status") == "ok" for cell in cells),
            "nodeErrors": sum(int(cell.get("node_errors", 0)) for cell in cells),
        }

    langchain = {}
    for mode in ("batch_shared", "abatch_blocking", "seq"):
        cells = [result.get("langchain", {}).get(mode, {}) for result in concurrent]
        langchain[mode] = {
            "wallSeconds": stats(cell.get("wall_s") for cell in cells),
            "statuses": sorted({str(cell.get("status", "missing")) for cell in cells}),
            "okUnits": stats(cell.get("n_ok") for cell in cells),
            "errorUnits": stats(cell.get("n_err") for cell in cells),
        }

    fault = loaded["fault-isolation"]
    isolation = loaded["data-isolation"]
    return {
        "schemaVersion": "node.rocketride.supported-linux-summary/v1",
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "runId": completion.get("runId", run_root.name),
        "status": "evidence_complete" if not issues else "evidence_incomplete",
        "officialStatus": "independent_unsubmitted_reproduction",
        "sourceCommit": SOURCE_SHA,
        "environment": load_json(run_root / "environment.json"),
        "completeness": completeness,
        "gateIssues": issues,
        "failureLedger": failure_signals(),
        "faultIsolation": {
            "rocketRideIsolationHeld": sum(
                result.get("verdict_metrics", {}).get("rr_isolation_holds") is True
                for result in fault
            ),
            "langChainLostAll": sum(
                result.get("verdict_metrics", {}).get("inproc_lost_all") is True
                for result in fault
            ),
            "repetitions": len(fault),
        },
        "concurrentProcessing": {
            "rocketRideByPool": rr_by_pool,
            "langChain": langchain,
            "appendixNodeErrors": stats(
                result.get("rr_appendix_threads4", {}).get("node_errors")
                for result in concurrent
            ),
        },
        "dataIsolation": {
            "cleanRuns": sum(
                result.get("verdict_metrics", {}).get("rr_clean") is True for result in isolation
            ),
            "lostDocs": stats(
                result.get("verdict_metrics", {}).get("rr_docs_lost") for result in isolation
            ),
            "duplicatedOrLeakedDocs": stats(
                result.get("verdict_metrics", {}).get("rr_docs_duplicated_or_leaked")
                for result in isolation
            ),
            "wallSeconds": stats(
                result.get("rocketride", {}).get("wall_s") for result in isolation
            ),
            "warmupSeconds": stats(
                result.get("rocketride", {}).get("warm_s") for result in isolation
            ),
        },
        "authoringEffort": loaded["authoring-effort"][0].get("verdict_metrics", {})
        if loaded["authoring-effort"]
        else {},
    }


def markdown(summary: dict) -> str:
    lines = [
        "# Supported Linux Reproduction",
        "",
        f"Evidence status: **{summary['status']}**. External status: **{summary['officialStatus']}**.",
        "This is an unchanged benchmark-source reproduction on WSL2 Ubuntu, not a RocketRide-accepted official result.",
        "",
        "| Benchmark | Expected | Observed | Complete |",
        "|---|---:|---:|---|",
    ]
    for benchmark, item in summary["completeness"].items():
        lines.append(
            f"| {benchmark} | {item['expected']} | {item['observed']} | {str(item['complete']).lower()} |"
        )
    lines.extend(["", "## Dimensional Results", ""])
    fault = summary["faultIsolation"]
    lines.append(
        f"- Fault isolation: RocketRide held in {fault['rocketRideIsolationHeld']}/{fault['repetitions']} runs; LangChain lost all work in {fault['langChainLostAll']}/{fault['repetitions']}."
    )
    for pool, item in summary["concurrentProcessing"]["rocketRideByPool"].items():
        lines.append(
            f"- RocketRide M={pool}: wall median {item['wallSeconds']['median']} s, p95 {item['wallSeconds']['p95']} s; warm-up median {item['warmupSeconds']['median']} s; clean {item['cleanRuns']}/{item['wallSeconds']['count']}."
        )
    for mode, item in summary["concurrentProcessing"]["langChain"].items():
        lines.append(
            f"- LangChain {mode}: statuses {', '.join(item['statuses'])}; wall median {item['wallSeconds']['median']} s, p95 {item['wallSeconds']['p95']} s."
        )
    isolation = summary["dataIsolation"]
    lines.append(
        f"- Data isolation: RocketRide clean {isolation['cleanRuns']}/{summary['completeness']['data-isolation']['observed']}; lost median {isolation['lostDocs']['median']}; duplicated/leaked median {isolation['duplicatedOrLeakedDocs']['median']}."
    )
    lines.append(
        f"- Preserved Linux failure signals: {summary['failureLedger']['count']} total, {summary['failureLedger']['retries']} retries."
    )
    if summary["gateIssues"]:
        lines.extend(["", "## Evidence Gaps", ""])
        lines.extend(f"- {issue}" for issue in summary["gateIssues"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    candidates = sorted(path for path in LINUX.glob("linux-*") if path.is_dir())
    run_root = LINUX / args.run if args.run else (candidates[-1] if candidates else None)
    if run_root is None or not run_root.is_dir():
        raise SystemExit("no supported Linux export found")
    summary = aggregate(run_root)
    aggregate_root = run_root / "aggregate"
    aggregate_root.mkdir(parents=True, exist_ok=True)
    (aggregate_root / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (aggregate_root / "SUMMARY.md").write_text(markdown(summary), encoding="utf-8")
    (LINUX / "latest.json").write_text(
        json.dumps(
            {
                "schemaVersion": "node.rocketride.supported-linux-pointer/v1",
                "runId": run_root.name,
                "summary": (aggregate_root / "summary.json").relative_to(REPO).as_posix(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"runId": run_root.name, "status": summary["status"]}))
    return 1 if args.require_complete and summary["status"] != "evidence_complete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
