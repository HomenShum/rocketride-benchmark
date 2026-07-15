#!/usr/bin/env python3
"""Audit a completed Node extension run without rewriting its scorecard."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import shutil
from typing import Any


HERE = Path(__file__).resolve().parent
SUITE = HERE.parent
REPO = SUITE.parent.parent.parent
EXPECTED_FIXTURES = {
    "nodebenchai-frozen-sources-v1",
    "noderoom-conflict-proposal-v1",
    "noderoom-independent-writes-v1",
    "nodeslide-independent-elements-v1",
    "nodevideo-resume-shots-v1",
}
FRAMEWORKS = ("native", "rocketride", "langchain")
VARIANTS = ("normal", "hard-failure")
REPETITIONS = 3
SOURCE_PATHS = [
    "PRE_REGISTRATION.md",
    "README.md",
    "common/async_utils.py",
    "common/langchain_executor.py",
    "common/native_executor.mjs",
    "common/protocol.py",
    "common/run_app_verifiers.py",
    "common/run_suite.py",
    "common/test_protocol.py",
    "common/rocketride-node/nodeworkflow/IGlobal.py",
    "common/rocketride-node/nodeworkflow/IInstance.py",
    "common/rocketride-node/nodeworkflow/__init__.py",
    "common/rocketride-node/nodeworkflow/services.json",
    *[
        f"fixtures/{path.name}"
        for path in sorted((SUITE / "fixtures").glob("*.json"))
    ],
]
EXECUTED_SOURCE_PATHS = [
    "PRE_REGISTRATION.md",
    "common/async_utils.py",
    "common/langchain_executor.py",
    "common/native_executor.mjs",
    "common/protocol.py",
    "common/run_suite.py",
    "common/rocketride-node/nodeworkflow/IGlobal.py",
    "common/rocketride-node/nodeworkflow/IInstance.py",
    "common/rocketride-node/nodeworkflow/__init__.py",
    "common/rocketride-node/nodeworkflow/services.json",
    *[
        f"fixtures/{path.name}"
        for path in sorted((SUITE / "fixtures").glob("*.json"))
    ],
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_relative(value: str) -> bool:
    path = Path(value)
    return (
        bool(value)
        and not path.is_absolute()
        and not any(part in ("", ".", "..") for part in path.parts)
    )


def manifest_issues(run_root: Path) -> list[str]:
    path = run_root / "manifest.json"
    if not path.is_file():
        return ["manifest.json is missing"]
    try:
        manifest = read_json(path)
    except Exception as error:
        return [f"manifest.json is invalid: {error}"]
    issues: list[str] = []
    if manifest.get("schemaVersion") != "node.workflow-extension-manifest/v1":
        issues.append("manifest schema is unsupported")
    declared: dict[str, dict] = {}
    for item in manifest.get("files", []):
        relative = item.get("path")
        if not isinstance(relative, str) or not safe_relative(relative):
            issues.append(f"unsafe manifest path: {relative}")
            continue
        if relative in declared:
            issues.append(f"duplicate manifest path: {relative}")
        declared[relative] = item
    actual = {
        item.relative_to(run_root).as_posix()
        for item in run_root.rglob("*")
        if item.is_file() and item != path
    }
    missing = sorted(set(declared) - actual)
    extra = sorted(actual - set(declared))
    if missing:
        issues.append("manifest files missing: " + ", ".join(missing))
    if extra:
        issues.append("unmanifested files: " + ", ".join(extra))
    for relative in sorted(set(declared) & actual):
        artifact = run_root / relative
        item = declared[relative]
        if item.get("bytes") != artifact.stat().st_size:
            issues.append(f"byte count mismatch: {relative}")
        if item.get("sha256") != sha256(artifact):
            issues.append(f"sha256 mismatch: {relative}")
    return issues


def result_issues(
    path: Path,
    request: dict,
    display_path: str | None = None,
) -> list[dict[str, str]]:
    relative = display_path or path.as_posix()
    try:
        result = read_json(path)
    except Exception as error:
        return [{"path": relative, "code": "invalid_json", "message": str(error)}]
    issues: list[dict[str, str]] = []

    def issue(code: str, message: str) -> None:
        issues.append({"path": relative, "code": code, "message": message})

    if result.get("schemaVersion") != "node.workflow-execution/v1":
        issue("schema", "unsupported result schema")
    for key in ("traceId", "inputDigest", "idempotencyKey"):
        if result.get(key) != request.get(key):
            issue("request_binding", f"{key} does not match request")
    framework = result.get("framework")
    if framework not in FRAMEWORKS:
        issue("framework", "framework is invalid")
    metrics = result.get("metrics")
    if not isinstance(metrics, dict):
        issue("metrics", "metrics are missing")
        return issues
    total_ms = metrics.get("totalMs")
    if not isinstance(total_ms, (int, float)) or not math.isfinite(total_ms):
        issue("metrics", "totalMs is not finite")
    elif total_ms > request.get("deadlineMs", -1):
        issue(
            "deadline_exceeded",
            f"totalMs {total_ms:.3f} exceeds deadlineMs {request.get('deadlineMs')}",
        )
    for key in ("duplicateUnits", "leakedUnits"):
        if metrics.get(key) != 0:
            issue("integrity", f"{key} must be zero")
    provenance = result.get("provenance")
    if not isinstance(provenance, dict):
        issue("provenance", "runtime provenance is missing")
    else:
        if provenance.get("deterministic") is not True:
            issue("provenance", "runtime provenance is not deterministic")
        if provenance.get("location") != "local":
            issue("provenance", "scored runtime is not local")
    events = result.get("events")
    if not isinstance(events, list) or not events:
        issue("events", "execution events are missing")
    elif any(event.get("sequence") != index for index, event in enumerate(events, 1)):
        issue("events", "event sequences are not contiguous")
    return issues


def semantic_audit(run_root: Path) -> dict[str, Any]:
    scorecard_path = run_root / "scorecard.json"
    scorecard = read_json(scorecard_path)
    integrity: list[str] = []
    protocol: list[dict[str, str]] = []
    result_count = 0
    trace_count = 0
    request_count = 0
    seen_cells: set[tuple[str, str, int]] = set()
    result_frameworks = {framework: 0 for framework in FRAMEWORKS}

    for fixture in sorted(EXPECTED_FIXTURES):
        for variant in VARIANTS:
            for repetition in range(1, REPETITIONS + 1):
                directory = run_root / fixture / variant / f"rep-{repetition:02d}"
                if not directory.is_dir():
                    integrity.append(f"missing repetition directory: {directory.relative_to(run_root)}")
                    continue
                seen_cells.add((fixture, variant, repetition))
                request_path = directory / "request.json"
                if not request_path.is_file():
                    integrity.append(f"missing request: {request_path.relative_to(run_root)}")
                    continue
                request_count += 1
                request = read_json(request_path)
                if request.get("deadlineMs") != 10_000:
                    integrity.append(f"deadline changed: {request_path.relative_to(run_root)}")
                for framework in FRAMEWORKS:
                    result_path = directory / f"{framework}-result.json"
                    if not result_path.is_file():
                        integrity.append(f"missing result: {result_path.relative_to(run_root)}")
                        continue
                    result_count += 1
                    result_frameworks[framework] += 1
                    protocol.extend(
                        result_issues(
                            result_path,
                            request,
                            result_path.relative_to(run_root).as_posix(),
                        )
                    )
                trace_path = directory / "rocketride-trace.jsonl.gz"
                if not trace_path.is_file() or trace_path.stat().st_size == 0:
                    integrity.append(f"missing RocketRide trace: {trace_path.relative_to(run_root)}")
                else:
                    trace_count += 1

    expected_cells = len(EXPECTED_FIXTURES) * len(VARIANTS) * REPETITIONS
    if len(seen_cells) != expected_cells:
        integrity.append(f"expected {expected_cells} repetition cells, found {len(seen_cells)}")
    if result_count != expected_cells * len(FRAMEWORKS):
        integrity.append(f"expected 90 results, found {result_count}")
    if trace_count != expected_cells:
        integrity.append(f"expected 30 traces, found {trace_count}")
    if request_count != expected_cells:
        integrity.append(f"expected 30 requests, found {request_count}")
    if len(scorecard.get("rows", [])) != 30:
        integrity.append("scorecard must contain 30 aggregate rows")
    if scorecard.get("appVerification", {}).get("status") != "passed":
        integrity.append("app verification is not passed")
    if scorecard.get("appVerification", {}).get("protocolParity") is not True:
        integrity.append("app protocol parity is not passed")
    conditions = scorecard.get("conditions", {})
    if conditions.get("paidModelCalls") != 0 or conditions.get("cloudRuns") != 0:
        integrity.append("scored run used a paid model or cloud runtime")
    if conditions.get("finalWritesAttempted") != 0:
        integrity.append("scored run attempted an application write")

    deadline_issues = [item for item in protocol if item["code"] == "deadline_exceeded"]
    other_protocol_issues = [item for item in protocol if item["code"] != "deadline_exceeded"]
    engine_log = (run_root / "engine.log").read_text(encoding="utf-8", errors="replace")
    rows = scorecard.get("rows", [])
    rr_normal = [row["totalMs"]["median"] for row in rows if row["framework"] == "rocketride" and row["variant"] == "normal"]
    rr_failure = [row["totalMs"]["median"] for row in rows if row["framework"] == "rocketride" and row["variant"] == "hard-failure"]
    return {
        "integrityIssues": integrity,
        "protocolIssues": protocol,
        "deadlineIssueCount": len(deadline_issues),
        "otherProtocolIssueCount": len(other_protocol_issues),
        "counts": {
            "fixtures": len(EXPECTED_FIXTURES),
            "repetitionCells": len(seen_cells),
            "requests": request_count,
            "results": result_count,
            "resultsByFramework": result_frameworks,
            "rocketrideTraces": trace_count,
            "aggregateRows": len(rows),
        },
        "observations": {
            "rocketrideNormalMedianTotalMsRange": [min(rr_normal), max(rr_normal)],
            "rocketrideHardFailureMedianTotalMsRange": [min(rr_failure), max(rr_failure)],
            "engineWebsocket403Count": engine_log.count('"WebSocket /task/service" 403'),
        },
    }


def file_metrics(root: Path, paths: list[str]) -> list[dict[str, Any]]:
    files = []
    for relative in paths:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "physicalLines": len(text.splitlines()),
                "nonBlankLines": sum(bool(line.strip()) for line in text.splitlines()),
                "sha256": sha256(path),
            }
        )
    return files


def capture_executed_sources(run_root: Path) -> None:
    destination = run_root / "executed-source"
    for relative in EXECUTED_SOURCE_PATHS:
        target = destination / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SUITE / relative, target)


def source_manifest(run_root: Path) -> dict[str, Any]:
    current_files = file_metrics(SUITE, SOURCE_PATHS)
    executed_files = file_metrics(
        run_root / "executed-source", EXECUTED_SOURCE_PATHS
    )
    scorecard = read_json(run_root / "scorecard.json")
    recorded = {
        item["path"]: item["sha256"]
        for group in scorecard.get("authoring", {}).values()
        if isinstance(group, dict)
        for item in group.get("files", [])
    }
    executed = {item["path"]: item["sha256"] for item in executed_files}
    mismatches = [
        path for path, digest in recorded.items() if executed.get(path) != digest
    ]
    return {
        "schemaVersion": "node.workflow-source-manifest/v1",
        "generatedAt": utc_now(),
        "runId": run_root.name,
        "scorecardGeneratedAt": scorecard.get("generatedAt"),
        "scorecardRecordedSourceHashesMatch": not mismatches,
        "scorecardRecordedSourceHashMismatches": mismatches,
        "executedFiles": executed_files,
        "currentFiles": current_files,
    }


def rebuild_manifest(run_root: Path) -> None:
    manifest_path = run_root / "manifest.json"
    files = []
    for path in sorted(item for item in run_root.rglob("*") if item.is_file()):
        if path == manifest_path:
            continue
        files.append(
            {
                "path": path.relative_to(run_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    write_json(
        manifest_path,
        {"schemaVersion": "node.workflow-extension-manifest/v1", "files": files},
    )


def update_latest_pointer(run_root: Path, audit: dict[str, Any]) -> None:
    path = SUITE / "latest-run.json"
    if not path.is_file():
        return
    pointer = read_json(path)
    if pointer.get("runId") != run_root.name:
        return
    pointer.update(
        {
            "orchestrationStatus": audit["orchestrationGateStatus"],
            "protocolAdmissionStatus": audit["protocolAdmissionStatus"],
            "promotionStatus": audit["promotionStatus"],
            "auditPath": (run_root / "audit.json").relative_to(REPO).as_posix(),
        }
    )
    write_json(path, pointer)


def write_audit(run_root: Path) -> dict[str, Any]:
    pre_manifest = run_root / "manifest.json"
    pre_manifest_sha256 = sha256(pre_manifest)
    pre_manifest_issues = manifest_issues(run_root)
    capture_executed_sources(run_root)
    sources = source_manifest(run_root)
    write_json(run_root / "source-manifest.json", sources)
    semantic = semantic_audit(run_root)
    integrity = [*pre_manifest_issues, *semantic["integrityIssues"]]
    protocol_issues = semantic["protocolIssues"]
    evidence_complete = not integrity and sources["scorecardRecordedSourceHashesMatch"]
    protocol_passed = not protocol_issues
    negative_findings = [
        (
            f"{semantic['deadlineIssueCount']} result envelopes exceeded the fixed "
            "10000 ms request deadline and would be rejected by the shared app protocol."
        ),
        (
            "RocketRide normal median total time ranged from "
            f"{semantic['observations']['rocketrideNormalMedianTotalMsRange'][0]:.3f} to "
            f"{semantic['observations']['rocketrideNormalMedianTotalMsRange'][1]:.3f} ms."
        ),
        (
            "RocketRide hard-failure median total time ranged from "
            f"{semantic['observations']['rocketrideHardFailureMedianTotalMsRange'][0]:.3f} to "
            f"{semantic['observations']['rocketrideHardFailureMedianTotalMsRange'][1]:.3f} ms."
        ),
    ]
    if semantic["observations"]["engineWebsocket403Count"]:
        negative_findings.append(
            "The engine log recorded "
            f"{semantic['observations']['engineWebsocket403Count']} transient WebSocket 403 response(s)."
        )
    audit = {
        "schemaVersion": "node.workflow-post-run-audit/v1",
        "generatedAt": utc_now(),
        "runId": run_root.name,
        "evidenceStatus": "complete" if evidence_complete else "incomplete",
        "orchestrationGateStatus": read_json(run_root / "scorecard.json").get("status"),
        "protocolAdmissionStatus": "passed" if protocol_passed else "failed",
        "promotionStatus": (
            "eligible_for_external_submission"
            if evidence_complete and protocol_passed
            else "blocked"
        ),
        "officialStatus": "separate_application_study_unsubmitted",
        "preAuditManifestSha256": pre_manifest_sha256,
        "sourceManifestSha256": sha256(run_root / "source-manifest.json"),
        "integrityIssues": integrity,
        "protocolIssues": protocol_issues,
        "counts": semantic["counts"],
        "observations": semantic["observations"],
        "negativeFindings": negative_findings,
        "costs": {"modelUsd": 0, "cloudUsd": 0},
    }
    write_json(run_root / "audit.json", audit)
    rebuild_manifest(run_root)
    update_latest_pointer(run_root, audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--write-receipt", action="store_true")
    parser.add_argument("--require-promotion-ready", action="store_true")
    args = parser.parse_args()
    run_root = args.run_root.resolve()
    if args.write_receipt:
        audit = write_audit(run_root)
    else:
        audit = read_json(run_root / "audit.json")
    integrity = manifest_issues(run_root)
    if audit.get("evidenceStatus") != "complete":
        integrity.append("audit evidence status is not complete")
    result = {
        "runId": run_root.name,
        "manifestStatus": "passed" if not integrity else "failed",
        "manifestIssues": integrity,
        "evidenceStatus": audit.get("evidenceStatus"),
        "protocolAdmissionStatus": audit.get("protocolAdmissionStatus"),
        "promotionStatus": audit.get("promotionStatus"),
        "counts": audit.get("counts"),
    }
    print(json.dumps(result, indent=2))
    if integrity:
        return 1
    if args.require_promotion_ready and audit.get("promotionStatus") != "eligible_for_external_submission":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
