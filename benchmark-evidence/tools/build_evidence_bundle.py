#!/usr/bin/env python3
"""Build the NodeBenchAI ingestion bundle from immutable baseline evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "benchmark-evidence"
OUTPUT = EVIDENCE / "evidence-bundle.json"
SOURCE_SHA = "43be41acb58558dfae8e2e3deb86d8a00cb1b1c8"


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_kind(path: Path) -> str:
    value = path.as_posix().lower()
    if "trace" in value and path.suffix in {".gz", ".jsonl"}:
        return "trace"
    if "failure" in value:
        return "failure_ledger"
    if "deviation" in value:
        return "deviation"
    if "manifest" in value or "requirements" in value or "sha" in path.name.lower():
        return "manifest"
    if "environment" in value or "platform" in value or "version" in value:
        return "environment"
    if path.suffix == ".log":
        return "log"
    if "summary" in value or "scorecard" in value or "aggregate" in value:
        return "scorecard"
    return "result"


def collect_artifacts() -> list[dict]:
    paths = [
        path
        for path in (EVIDENCE / "baseline").rglob("*")
        if path.is_file() and path.resolve() != OUTPUT.resolve()
    ]
    paths.extend(
        path for path in (EVIDENCE / "failures.jsonl", EVIDENCE / "deviations.json") if path.is_file()
    )
    artifacts = []
    for path in sorted(set(paths)):
        relative = path.relative_to(EVIDENCE)
        artifacts.append(
            {
                "path": relative.as_posix(),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "kind": artifact_kind(relative),
            }
        )
    return artifacts


def add_runtime_findings(label: str, summary: dict, findings: list[str]) -> None:
    concurrent = summary.get("concurrentProcessing", {})
    rocketride = concurrent.get("rocketRideByPool", {})
    langchain = concurrent.get("langChain", {})
    lc_median = langchain.get("abatch_blocking", {}).get("wallSeconds", {}).get("median")
    for pool, values in rocketride.items():
        wall = values.get("wallSeconds", {})
        count = int(wall.get("count") or 0)
        clean = int(values.get("cleanRuns") or 0)
        if clean < count:
            findings.append(f"{label}: RocketRide M={pool} was clean in {clean}/{count} repetitions.")
        rr_median = wall.get("median")
        if isinstance(rr_median, (int, float)) and isinstance(lc_median, (int, float)) and rr_median > lc_median:
            findings.append(
                f"{label}: RocketRide M={pool} wall median {rr_median}s exceeded LangChain abatch {lc_median}s."
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    windows = load(EVIDENCE / "baseline" / "concurrent-work" / "aggregate" / "summary.json")
    linux_pointer = load(EVIDENCE / "baseline" / "linux" / "latest.json")
    linux = load(REPO / linux_pointer["summary"]) if linux_pointer else None
    gaps = ["RocketRide has not externally accepted or published this independent reproduction."]
    findings: list[str] = []
    if windows:
        add_runtime_findings("Windows", windows, findings)
        if windows.get("status") != "evidence_complete":
            gaps.append("The exploratory Windows evidence bundle is incomplete.")
    else:
        gaps.append("The exploratory Windows summary is missing.")
    if linux:
        add_runtime_findings("Supported Linux", linux, findings)
        if linux.get("status") != "evidence_complete":
            gaps.append("The supported Linux reproduction is incomplete.")
    else:
        gaps.append("The supported Linux reproduction is missing.")

    failure_rows = []
    failure_path = EVIDENCE / "failures.jsonl"
    if failure_path.is_file():
        failure_rows = [
            json.loads(line)
            for line in failure_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    bundle = {
        "schemaVersion": "node.rocketride.evidence-bundle/v1",
        "studyId": "rocketride-node-study-20260715",
        "sourceCommit": SOURCE_SHA,
        "publicationStatus": "independent_unsubmitted",
        "evidenceStatus": "complete"
        if linux and linux.get("status") == "evidence_complete"
        else "incomplete",
        "failureSignals": sum(row.get("failure") is True for row in failure_rows),
        "modelCostUsd": 0,
        "cloudCostUsd": 0,
        "negativeFindings": sorted(set(findings)),
        "evidenceGaps": sorted(set(gaps)),
        "artifacts": collect_artifacts(),
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "path": output.relative_to(REPO).as_posix(),
                "status": bundle["evidenceStatus"],
                "artifacts": len(bundle["artifacts"]),
                "negativeFindings": len(bundle["negativeFindings"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
