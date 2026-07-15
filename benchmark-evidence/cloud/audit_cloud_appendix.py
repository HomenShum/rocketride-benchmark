#!/usr/bin/env python3
"""Independently audit a RocketRide Cloud appendix run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any


POOL_SIZE = 4
DOCUMENTS = 16
REPETITIONS = 3
OFFICIAL_STATUS = "cloud_operational_appendix_unsubmitted"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(run_root: Path) -> list[str]:
    issues: list[str] = []
    manifest_path = run_root / "artifact-manifest.json"
    if not manifest_path.is_file():
        return ["artifact-manifest.json is missing"]
    manifest = read_json(manifest_path)
    seen: set[str] = set()
    for entry in manifest.get("files", []):
        relative = entry.get("path")
        if not isinstance(relative, str) or relative in seen:
            issues.append(f"invalid or duplicate manifest path: {relative!r}")
            continue
        seen.add(relative)
        path = run_root / relative
        if not path.is_file():
            issues.append(f"manifest file is missing: {relative}")
            continue
        if path.stat().st_size != entry.get("bytes"):
            issues.append(f"manifest byte count changed: {relative}")
        if sha256(path) != entry.get("sha256"):
            issues.append(f"manifest hash changed: {relative}")
    required = {
        "receipt.json",
        "RESULTS.md",
        "run.log",
        "source-manifest.json",
        "billing-before.json",
        "billing-after.json",
        "exact-upstream-attempt.json",
        *(f"repetition-{index:02d}.json" for index in range(1, REPETITIONS + 1)),
    }
    missing = sorted(required - seen)
    if missing:
        issues.append("manifest omits required files: " + ", ".join(missing))
    return issues


def secret_scan(run_root: Path) -> list[str]:
    issues: list[str] = []
    api_key = os.environ.get("ROCKETRIDE_APIKEY", "")
    forbidden_patterns = (
        re.compile(r"ROCKETRIDE_APIKEY\s*="),
        re.compile(r"Bearer\s+[A-Za-z0-9._-]{12,}", re.IGNORECASE),
    )
    for path in sorted(item for item in run_root.rglob("*") if item.is_file()):
        if path.name == "artifact-manifest.json":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(run_root).as_posix()
        if api_key and api_key in text:
            issues.append(f"live API key appears in {relative}")
        for pattern in forbidden_patterns:
            if pattern.search(text):
                issues.append(f"credential-shaped content appears in {relative}")
    return issues


def semantic_audit(receipt: dict[str, Any], repetitions: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    protocol = receipt.get("protocol", {})
    expected_protocol = {
        "poolSize": POOL_SIZE,
        "documentsPerRepetition": DOCUMENTS,
        "repetitions": REPETITIONS,
        "measuredRetries": 0,
        "modelCalls": 0,
        "paidModelCostUsd": 0,
        "cloudCheckoutChargeUsd": 0,
    }
    for key, value in expected_protocol.items():
        if protocol.get(key) != value:
            issues.append(f"protocol {key}: expected {value}, found {protocol.get(key)}")
    if receipt.get("officialStatus") != OFFICIAL_STATUS:
        issues.append("official status overclaims the Cloud appendix")
    if receipt.get("exactUpstreamCloudStatus") not in {
        "blocked_missing_workload_service",
        "started_requires_input_environment",
    }:
        issues.append("exact upstream Cloud attempt has an unclassified result")
    if len(repetitions) != REPETITIONS:
        issues.append(f"expected {REPETITIONS} repetitions, found {len(repetitions)}")

    normal: list[dict[str, Any]] = []
    failure: list[dict[str, Any]] = []
    cleanup: list[dict[str, Any]] = []
    token_hashes: list[str] = []
    for expected_index, repetition in enumerate(repetitions, start=1):
        if repetition.get("repetition") != expected_index:
            issues.append(f"repetition ordering changed at {expected_index}")
        if repetition.get("poolSize") != POOL_SIZE:
            issues.append(f"repetition {expected_index} pool size changed")
        if repetition.get("documentCount") != DOCUMENTS:
            issues.append(f"repetition {expected_index} document count changed")
        tasks = repetition.get("tasks", [])
        if len(tasks) != POOL_SIZE:
            issues.append(f"repetition {expected_index} task count is {len(tasks)}")
        token_hashes.extend(str(task.get("taskTokenHash", "")) for task in tasks)
        normal.extend(repetition.get("normal", []))
        failure.extend(repetition.get("failure", []))
        cleanup.extend(repetition.get("cleanup", []))

    if len(set(token_hashes)) != REPETITIONS * POOL_SIZE:
        issues.append("task-token hashes are missing or not unique")
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in token_hashes):
        issues.append("one or more task-token fingerprints are malformed")
    if len(normal) != REPETITIONS * DOCUMENTS:
        issues.append(f"expected 48 normal records, found {len(normal)}")
    for record in normal:
        if not (
            record.get("ok") is True
            and record.get("markerPresent") is True
            and record.get("crossTaskLeak") is False
            and record.get("seenMarkers") == [record.get("expectedMarker")]
        ):
            issues.append(
                "normal request failed isolation: "
                f"r{record.get('repetition')} d{record.get('documentIndex')}"
            )
    targeted = [record for record in failure if record.get("taskIndex") == 0]
    unaffected = [record for record in failure if record.get("taskIndex") != 0]
    if len(targeted) != REPETITIONS or any(record.get("ok") is not False for record in targeted):
        issues.append("terminated task did not fail exactly once per repetition")
    if len(unaffected) != REPETITIONS * (POOL_SIZE - 1):
        issues.append("unaffected failure-phase request count is wrong")
    for record in unaffected:
        if not (
            record.get("ok") is True
            and record.get("markerPresent") is True
            and record.get("crossTaskLeak") is False
            and record.get("seenMarkers") == [record.get("expectedMarker")]
        ):
            issues.append(
                "unaffected task failed isolation: "
                f"r{record.get('repetition')} t{record.get('taskIndex')}"
            )
    if len(cleanup) != REPETITIONS * POOL_SIZE:
        issues.append(f"expected 12 cleanup records, found {len(cleanup)}")
    if any(record.get("terminateCallSucceeded") is not True for record in cleanup):
        issues.append("one or more task termination calls failed")

    billing = receipt.get("billingAfter", {})
    subscription = billing.get("subscription") or {}
    if billing.get("promotionCode") != "JULY2026BENCHMARK":
        issues.append("promotion code verification is missing")
    if subscription.get("status") != "active":
        issues.append("Starter subscription is not active")
    if not str(subscription.get("planNickname", "")).lower().startswith("starter"):
        issues.append("Starter subscription was not verified")
    if subscription.get("cancelAtPeriodEnd") is not True:
        issues.append("paid renewal remains enabled")
    if receipt.get("controlSummary", {}).get("billingGatePassed") is not True:
        issues.append("billing gate did not pass")
    if receipt.get("controlAdmissionStatus") != "passed":
        issues.append("Cloud control did not pass")
    return issues


def audit(run_root: Path) -> dict[str, Any]:
    integrity = verify_manifest(run_root)
    integrity.extend(secret_scan(run_root))
    receipt_path = run_root / "receipt.json"
    if not receipt_path.is_file():
        integrity.append("receipt.json is missing")
        receipt: dict[str, Any] = {}
    else:
        receipt = read_json(receipt_path)
    repetitions = []
    for index in range(1, REPETITIONS + 1):
        path = run_root / f"repetition-{index:02d}.json"
        if path.is_file():
            repetitions.append(read_json(path))
    semantic = semantic_audit(receipt, repetitions) if receipt else []
    passed = not integrity and not semantic
    return {
        "schemaVersion": 1,
        "status": "passed" if passed else "failed",
        "evidenceStatus": "complete" if passed else "invalid",
        "controlAdmissionStatus": "passed" if passed else "failed",
        "exactUpstreamCloudStatus": receipt.get("exactUpstreamCloudStatus"),
        "officialStatus": OFFICIAL_STATUS,
        "integrityIssues": integrity,
        "semanticIssues": semantic,
        "counts": receipt.get("controlSummary", {}).get("counts", {}),
        "receiptSha256": sha256(receipt_path) if receipt_path.is_file() else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    args = parser.parse_args()
    run_root = args.run_root.resolve()
    result = audit(run_root)
    output = run_root / "audit.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
