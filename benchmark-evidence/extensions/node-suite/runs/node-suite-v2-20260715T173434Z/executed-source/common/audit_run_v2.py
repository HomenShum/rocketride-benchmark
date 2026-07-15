#!/usr/bin/env python3
"""Independently audit a resident-runtime V2 Node extension run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from typing import Any

import audit_run as v1_audit
from protocol import digest
from resolved_definition import EXECUTION_POLICY, FROZEN_PRODUCTION_COMMITS


HERE = Path(__file__).resolve().parent
SUITE = HERE.parent
REPO = SUITE.parent.parent.parent
FRAMEWORKS = ("native", "rocketride", "langchain")
VARIANTS = ("normal", "hard-failure")
REPETITIONS = EXECUTION_POLICY["repetitions"]
EXPECTED_FIXTURES = {
    "nodebenchai-frozen-sources-v2",
    "noderoom-conflict-proposal-v2",
    "noderoom-independent-writes-v2",
    "nodeslide-independent-elements-v2",
    "nodevideo-resume-shots-v2",
}
SOURCE_PATHS = [
    "PRE_REGISTRATION.md",
    "PRE_REGISTRATION_V2.md",
    "README.md",
    "common/async_utils.py",
    "common/audit_run.py",
    "common/audit_run_v2.py",
    "common/langchain_executor.py",
    "common/native_executor.mjs",
    "common/protocol.py",
    "common/resolved_definition.py",
    "common/run_app_verifiers.py",
    "common/run_suite.py",
    "common/run_suite_v2.py",
    "common/test_resident_v2.py",
    "common/rocketride-node/nodeworkflow/IGlobal.py",
    "common/rocketride-node/nodeworkflow/IInstance.py",
    "common/rocketride-node/nodeworkflow/__init__.py",
    "common/rocketride-node/nodeworkflow/services.json",
    *[
        f"fixtures/{path.name}" for path in sorted((SUITE / "fixtures").glob("*.json"))
    ],
]
EXECUTED_SOURCE_PATHS = list(SOURCE_PATHS)


def definition_map(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in bundle.get("definitions", []):
        definition = item.get("definition")
        definition_digest = item.get("definitionDigest")
        if not isinstance(definition, dict) or not isinstance(definition_digest, str):
            continue
        fixture_id = definition.get("fixture", {}).get("fixtureId")
        if isinstance(fixture_id, str):
            result[fixture_id] = item
    return result


def result_issues_v2(
    path: Path,
    request: dict[str, Any],
    definition_item: dict[str, Any],
    display_path: str,
) -> list[dict[str, str]]:
    issues = v1_audit.result_issues(path, request, display_path)
    result = v1_audit.read_json(path)

    def issue(code: str, message: str) -> None:
        issues.append({"path": display_path, "code": code, "message": message})

    expected_digest = definition_item["definitionDigest"]
    if request.get("definitionDigest") != expected_digest:
        issue("definition_binding", "request definition digest does not match fixture")
    if result.get("definitionDigest") != expected_digest:
        issue("definition_binding", "result definition digest does not match request")
    provenance = result.get("provenance", {})
    if provenance.get("definitionDigest") != expected_digest:
        issue("definition_binding", "provenance definition digest does not match request")
    expected_commit = definition_item["definition"]["application"]["productionCommit"]
    if provenance.get("appCommit") != expected_commit:
        issue("production_binding", "result does not bind the frozen production commit")
    if result.get("outputDigest") != digest(result.get("candidate")):
        issue("candidate_digest", "candidate output digest does not verify")
    lifecycle = result.get("runtimeLifecycle", {})
    expected_exclusion = result.get("framework") == "rocketride"
    if lifecycle.get("profile") != "resident-local-v2":
        issue("runtime_lifecycle", "serving profile is not resident-local-v2")
    if lifecycle.get("startupExcludedFromTotalMs") is not expected_exclusion:
        issue("runtime_lifecycle", "startup clock boundary is inconsistent")
    if lifecycle.get("unitTimeoutMs") != EXECUTION_POLICY["unitTimeoutMs"]:
        issue("runtime_lifecycle", "unit timeout does not match the V2 definition")
    return issues


def expected_input_digest(
    source_fixture: dict[str, Any], request: dict[str, Any], variant: str
) -> str:
    request_input = {
        "app": source_fixture["app"],
        "baseVersion": source_fixture.get("baseVersion"),
        "definitionDigest": request["definitionDigest"],
        "fixtureId": request["fixtureId"],
        "units": source_fixture["units"],
        "variant": variant,
        "workflow": source_fixture["workflow"],
    }
    return digest(request_input)


def semantic_audit(run_root: Path) -> dict[str, Any]:
    scorecard = v1_audit.read_json(run_root / "scorecard.json")
    bundle = v1_audit.read_json(run_root / "resolved-definitions.json")
    definitions = definition_map(bundle)
    integrity: list[str] = []
    protocol: list[dict[str, str]] = []
    result_count = 0
    trace_count = 0
    request_count = 0
    seen_cells: set[tuple[str, str, int]] = set()
    result_frameworks = {framework: 0 for framework in FRAMEWORKS}

    if set(definitions) != EXPECTED_FIXTURES:
        integrity.append("resolved definition fixture catalog is incomplete")
    for fixture_id, item in definitions.items():
        if digest(item.get("definition")) != item.get("definitionDigest"):
            integrity.append(f"resolved definition digest is invalid: {fixture_id}")
        definition = item.get("definition", {})
        app = definition.get("application", {}).get("app")
        if definition.get("application", {}).get("productionCommit") != FROZEN_PRODUCTION_COMMITS.get(app):
            integrity.append(f"production commit binding is invalid: {fixture_id}")
        if definition.get("executionPolicy") != EXECUTION_POLICY:
            integrity.append(f"execution policy changed: {fixture_id}")

    for fixture_id in sorted(EXPECTED_FIXTURES):
        item = definitions.get(fixture_id)
        if item is None:
            continue
        source_path = item["definition"]["fixture"]["sourcePath"]
        source_fixture = v1_audit.read_json(SUITE / source_path)
        for variant in VARIANTS:
            candidate_digests: set[str] = set()
            for repetition in range(1, REPETITIONS + 1):
                directory = run_root / fixture_id / variant / f"rep-{repetition:02d}"
                if not directory.is_dir():
                    integrity.append(
                        f"missing repetition directory: {directory.relative_to(run_root)}"
                    )
                    continue
                seen_cells.add((fixture_id, variant, repetition))
                request_path = directory / "request.json"
                if not request_path.is_file():
                    integrity.append(f"missing request: {request_path.relative_to(run_root)}")
                    continue
                request_count += 1
                request = v1_audit.read_json(request_path)
                if request.get("deadlineMs") != EXECUTION_POLICY["deadlineMs"]:
                    integrity.append(f"deadline changed: {request_path.relative_to(run_root)}")
                if request.get("unitTimeoutMs") != EXECUTION_POLICY["unitTimeoutMs"]:
                    integrity.append(f"unit timeout changed: {request_path.relative_to(run_root)}")
                if request.get("definitionDigest") != item["definitionDigest"]:
                    integrity.append(
                        f"request definition changed: {request_path.relative_to(run_root)}"
                    )
                if request.get("inputDigest") != expected_input_digest(
                    source_fixture, request, variant
                ):
                    integrity.append(
                        f"request input digest is invalid: {request_path.relative_to(run_root)}"
                    )
                for framework in FRAMEWORKS:
                    result_path = directory / f"{framework}-result.json"
                    if not result_path.is_file():
                        integrity.append(
                            f"missing result: {result_path.relative_to(run_root)}"
                        )
                        continue
                    result_count += 1
                    result_frameworks[framework] += 1
                    result = v1_audit.read_json(result_path)
                    candidate_digests.add(str(result.get("outputDigest")))
                    metrics = result.get("metrics", {})
                    if variant == "normal":
                        if metrics.get("completedUnits") != 4 or metrics.get("failedUnits") != 0:
                            integrity.append(
                                f"normal completion failed: {result_path.relative_to(run_root)}"
                            )
                    elif framework in ("native", "rocketride"):
                        if metrics.get("completedUnits") != 3 or metrics.get("failedUnits") != 1:
                            integrity.append(
                                f"hard-failure isolation failed: {result_path.relative_to(run_root)}"
                            )
                        if framework == "rocketride" and metrics.get("runtimeHealthyAfter") is not True:
                            integrity.append(
                                f"engine unhealthy after fault: {result_path.relative_to(run_root)}"
                            )
                    protocol.extend(
                        result_issues_v2(
                            result_path,
                            request,
                            item,
                            result_path.relative_to(run_root).as_posix(),
                        )
                    )
                trace_path = directory / "rocketride-trace.jsonl.gz"
                if not trace_path.is_file() or trace_path.stat().st_size == 0:
                    integrity.append(
                        f"missing RocketRide trace: {trace_path.relative_to(run_root)}"
                    )
                else:
                    trace_count += 1
            if len(candidate_digests) != 1:
                integrity.append(f"candidate digest parity failed: {fixture_id} {variant}")

    expected_cells = len(EXPECTED_FIXTURES) * len(VARIANTS) * REPETITIONS
    if len(seen_cells) != expected_cells:
        integrity.append(f"expected {expected_cells} repetition cells, found {len(seen_cells)}")
    if request_count != expected_cells:
        integrity.append(f"expected 30 requests, found {request_count}")
    if result_count != expected_cells * len(FRAMEWORKS):
        integrity.append(f"expected 90 results, found {result_count}")
    if trace_count != expected_cells:
        integrity.append(f"expected 30 traces, found {trace_count}")
    if len(scorecard.get("rows", [])) != 30:
        integrity.append("scorecard must contain 30 aggregate rows")
    if scorecard.get("status") != "passed":
        integrity.append("orchestration scorecard did not pass")
    if scorecard.get("appVerification", {}).get("status") != "passed":
        integrity.append("app verification did not pass")
    if scorecard.get("appVerification", {}).get("protocolParity") is not True:
        integrity.append("app protocol parity did not pass")
    for receipt in scorecard.get("appVerification", {}).get("apps", []):
        app = receipt.get("app")
        if receipt.get("adapterCommit") != FROZEN_PRODUCTION_COMMITS.get(app):
            integrity.append(f"app verifier is not on frozen production commit: {app}")
        if receipt.get("branch") != "main":
            integrity.append(f"app verifier was not executed on main: {app}")
    conditions = scorecard.get("conditions", {})
    if conditions.get("paidModelCalls") != 0 or conditions.get("cloudRuns") != 0:
        integrity.append("scored run used a paid model or cloud runtime")
    if conditions.get("finalWritesAttempted") != 0:
        integrity.append("scored run attempted an application write")
    if scorecard.get("v1Result", {}).get("superseded") is not False:
        integrity.append("V1 failure preservation marker is missing")

    lifecycle = v1_audit.read_json(run_root / "runtime-lifecycle.json")
    pools = lifecycle.get("rocketridePools", [])
    normal_pools = [item for item in pools if item.get("variant") == "normal"]
    fault_pools = [item for item in pools if item.get("variant") == "hard-failure"]
    if len(pools) != 20 or len(normal_pools) != 5 or len(fault_pools) != 15:
        integrity.append("RocketRide pool lifecycle does not match pre-registration")
    if len({item.get("poolId") for item in pools}) != len(pools):
        integrity.append("RocketRide pool IDs are not unique")

    rows = scorecard.get("rows", [])
    rr_normal = [
        row["totalMs"]["median"]
        for row in rows
        if row["framework"] == "rocketride" and row["variant"] == "normal"
    ]
    rr_failure = [
        row["totalMs"]["median"]
        for row in rows
        if row["framework"] == "rocketride" and row["variant"] == "hard-failure"
    ]
    warmups = [float(item["warmupMs"]) for item in pools]
    engine_log = (run_root / "engine.log").read_text(encoding="utf-8", errors="replace")
    return {
        "integrityIssues": integrity,
        "protocolIssues": protocol,
        "counts": {
            "fixtures": len(EXPECTED_FIXTURES),
            "repetitionCells": len(seen_cells),
            "requests": request_count,
            "results": result_count,
            "resultsByFramework": result_frameworks,
            "rocketrideTraces": trace_count,
            "aggregateRows": len(rows),
            "rocketridePools": len(pools),
        },
        "observations": {
            "rocketrideNormalMedianTotalMsRange": [min(rr_normal), max(rr_normal)],
            "rocketrideHardFailureMedianTotalMsRange": [min(rr_failure), max(rr_failure)],
            "rocketridePoolWarmupMsRange": [min(warmups), max(warmups)],
            "engineWebsocket403Count": engine_log.count('"WebSocket /task/service" 403'),
            "v1DeadlineIssueCount": 30,
        },
    }


def capture_executed_sources(run_root: Path) -> None:
    destination = run_root / "executed-source"
    for relative in EXECUTED_SOURCE_PATHS:
        target = destination / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SUITE / relative, target)


def source_manifest(run_root: Path) -> dict[str, Any]:
    current_files = v1_audit.file_metrics(SUITE, SOURCE_PATHS)
    executed_files = v1_audit.file_metrics(
        run_root / "executed-source", EXECUTED_SOURCE_PATHS
    )
    scorecard = v1_audit.read_json(run_root / "scorecard.json")
    recorded = {
        item["path"]: item["sha256"]
        for group in scorecard.get("authoring", {}).values()
        if isinstance(group, dict)
        for item in group.get("files", [])
    }
    executed = {item["path"]: item["sha256"] for item in executed_files}
    mismatches = [
        path for path, source_hash in recorded.items() if executed.get(path) != source_hash
    ]
    return {
        "schemaVersion": "node.workflow-source-manifest/v2",
        "generatedAt": v1_audit.utc_now(),
        "runId": run_root.name,
        "scorecardGeneratedAt": scorecard.get("generatedAt"),
        "scorecardRecordedSourceHashesMatch": not mismatches,
        "scorecardRecordedSourceHashMismatches": mismatches,
        "executedFiles": executed_files,
        "currentFiles": current_files,
    }


def write_audit(run_root: Path) -> dict[str, Any]:
    pre_manifest = run_root / "manifest.json"
    pre_manifest_sha256 = v1_audit.sha256(pre_manifest)
    pre_manifest_issues = v1_audit.manifest_issues(run_root)
    capture_executed_sources(run_root)
    sources = source_manifest(run_root)
    v1_audit.write_json(run_root / "source-manifest.json", sources)
    semantic = semantic_audit(run_root)
    integrity = [*pre_manifest_issues, *semantic["integrityIssues"]]
    protocol_issues = semantic["protocolIssues"]
    evidence_complete = not integrity and sources["scorecardRecordedSourceHashesMatch"]
    protocol_passed = not protocol_issues
    observations = semantic["observations"]
    audit = {
        "schemaVersion": "node.workflow-post-run-audit/v2",
        "generatedAt": v1_audit.utc_now(),
        "runId": run_root.name,
        "profile": "resident-local-v2",
        "evidenceStatus": "complete" if evidence_complete else "incomplete",
        "orchestrationGateStatus": v1_audit.read_json(
            run_root / "scorecard.json"
        ).get("status"),
        "protocolAdmissionStatus": "passed" if protocol_passed else "failed",
        "promotionStatus": (
            "eligible_for_external_submission"
            if evidence_complete and protocol_passed
            else "blocked"
        ),
        "officialStatus": "separate_application_study_unsubmitted",
        "preAuditManifestSha256": pre_manifest_sha256,
        "sourceManifestSha256": v1_audit.sha256(run_root / "source-manifest.json"),
        "integrityIssues": integrity,
        "protocolIssues": protocol_issues,
        "counts": semantic["counts"],
        "observations": observations,
        "negativeFindings": [
            "V1 remains protocol-blocked by 30 RocketRide request deadline overruns.",
            (
                "V2 RocketRide pool warmup ranged from "
                f"{observations['rocketridePoolWarmupMsRange'][0]:.3f} to "
                f"{observations['rocketridePoolWarmupMsRange'][1]:.3f} ms and is a real "
                "standing or recovery cost."
            ),
            "Native and LangChain V2 totals conservatively retain subprocess startup time.",
            "V2 local eligibility is not an official or accepted RocketRide result.",
        ],
        "costs": {"modelUsd": 0, "cloudUsd": 0},
    }
    v1_audit.write_json(run_root / "audit.json", audit)
    v1_audit.rebuild_manifest(run_root)
    v1_audit.update_latest_pointer(run_root, audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--write-receipt", action="store_true")
    parser.add_argument("--require-promotion-ready", action="store_true")
    args = parser.parse_args()
    run_root = args.run_root.resolve()
    audit = (
        write_audit(run_root)
        if args.write_receipt
        else v1_audit.read_json(run_root / "audit.json")
    )
    integrity = v1_audit.manifest_issues(run_root)
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
    if (
        args.require_promotion_ready
        and audit.get("promotionStatus") != "eligible_for_external_submission"
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
