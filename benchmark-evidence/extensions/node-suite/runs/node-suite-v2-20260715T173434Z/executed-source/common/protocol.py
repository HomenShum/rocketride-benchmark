"""Versioned JSON protocol shared by the deterministic Node extension runners."""

from __future__ import annotations

import hashlib
import json
from typing import Any


SCHEMA_VERSION = "node.workflow-execution/v1"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def digest(value: Any) -> str:
    encoded = canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def deadline_overrun_count(results: list[dict], deadline_ms: int | float) -> int:
    return sum(
        float(result["metrics"]["totalMs"]) > float(deadline_ms)
        for result in results
    )


def request_for(fixture: dict, variant: str, repetition: int) -> dict:
    request_input = {
        "app": fixture["app"],
        "baseVersion": fixture.get("baseVersion"),
        "fixtureId": fixture["fixtureId"],
        "units": fixture["units"],
        "variant": variant,
        "workflow": fixture["workflow"],
    }
    request = {
        "schemaVersion": SCHEMA_VERSION,
        "app": fixture["app"],
        "workflow": fixture["workflow"],
        "fixtureId": fixture["fixtureId"],
        "traceId": f"trace:{fixture['fixtureId']}:{variant}:rep-{repetition:02d}",
        "inputDigest": digest(request_input),
        "idempotencyKey": f"{fixture['fixtureId']}:{variant}:rep-{repetition:02d}",
        "concurrency": fixture["concurrency"],
        "deadlineMs": fixture["deadlineMs"],
    }
    if fixture.get("baseVersion") is not None:
        request["baseVersion"] = fixture["baseVersion"]
    if variant == "hard-failure":
        request["failureSeed"] = fixture["units"][0]["id"]
    return request


def result_for(
    *,
    fixture: dict,
    request: dict,
    framework: str,
    repetition: int,
    execution: dict,
    runtime: str,
    runtime_version: str,
    adapter_version: str = "1.0.0",
) -> dict:
    completed = list(execution.get("completed", []))
    failed = list(execution.get("failed", []))
    expected = [unit["id"] for unit in fixture["units"]]
    duplicate_count = len(completed) - len(set(completed))
    leaked_count = len([unit for unit in completed if unit not in expected])
    events = [{"sequence": 1, "atMs": 0, "kind": "run.started"}]
    at_ms = 0
    for unit_id in completed:
        at_ms += 1
        events.append(
            {
                "sequence": len(events) + 1,
                "atMs": at_ms,
                "kind": "unit.completed",
                "unitId": unit_id,
            }
        )
    for unit_id in failed:
        at_ms += 1
        events.append(
            {
                "sequence": len(events) + 1,
                "atMs": at_ms,
                "kind": "unit.failed",
                "unitId": unit_id,
            }
        )
    total_ms = round(float(execution.get("totalMs", 0)), 3)
    execution_ms = round(float(execution.get("executionMs", total_ms)), 3)
    cold_ms = round(float(execution.get("coldStartMs", 0)), 3)
    warmup_ms = round(float(execution.get("warmupMs", 0)), 3)
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "runId": f"{request['idempotencyKey']}:{framework}",
        "traceId": request["traceId"],
        "framework": framework,
        "candidate": fixture["candidate"],
        "inputDigest": request["inputDigest"],
        "idempotencyKey": request["idempotencyKey"],
        "outputDigest": digest(fixture["candidate"]),
        "events": events,
        "metrics": {
            "coldStartMs": cold_ms,
            "warmupMs": warmup_ms,
            "executionMs": execution_ms,
            "totalMs": total_ms,
            "retryCount": int(execution.get("retryCount", 0)),
            "completedUnits": len(completed),
            "failedUnits": len(failed),
            "duplicateUnits": duplicate_count,
            "leakedUnits": leaked_count,
            "peakRssBytes": int(execution.get("peakRssBytes", 0)),
            "cpuTimeMs": round(float(execution.get("cpuTimeMs", 0)), 3),
        },
        "provenance": {
            "adapter": f"node-suite-{framework}",
            "adapterVersion": adapter_version,
            "runtime": runtime,
            "runtimeVersion": runtime_version,
            "appCommit": fixture["appCommit"],
            "deterministic": True,
            "location": "local",
        },
    }
    if "serverHealthyAfter" in execution:
        result["metrics"]["runtimeHealthyAfter"] = bool(execution["serverHealthyAfter"])
    if failed:
        result["error"] = {
            "code": "injected_hard_failure",
            "message": "A pre-registered work unit hard-failed.",
            "retryable": False,
        }
    return result
