"""Compile immutable V2 application definitions from merged-source receipts."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from protocol import SCHEMA_VERSION, digest


FROZEN_PRODUCTION_COMMITS = {
    "noderoom": "2ba12a33a9f77a5152096ccf1277d355948b78f6",
    "nodebenchai": "259d78150fd6bf0d670557707af3ddfefcc4fdc5",
    "nodeslide": "81e0e512cfd4a3d80d24f371bc690810d4f65dd5",
    "nodevideo": "88fab347f853a0d5834eb7559986176ac953d9f8",
}

EXECUTION_POLICY = {
    "candidateAuthority": "candidate_only_no_backend_mutation",
    "concurrency": 4,
    "deadlineMs": 10_000,
    "delayMs": 20,
    "engineLifecycle": "run_scoped",
    "hardFailurePoolLifecycle": "request_prewarmed_then_retired",
    "normalPoolLifecycle": "fixture_variant_resident",
    "poolSize": 4,
    "repetitions": 3,
    "retries": 0,
    "threadsPerPipe": 1,
    "traceDrainMs": 1_000,
    "traceLevel": "full",
    "ttlSeconds": 120,
    "unitTimeoutMs": 2_000,
    "variants": ["normal", "hard-failure"],
}


def v2_fixture_id(value: str) -> str:
    if not value.endswith("-v1"):
        raise ValueError(f"V2 source fixture must end in -v1: {value}")
    return value[:-3] + "-v2"


def source_bindings(group: dict[str, Any], label: str) -> list[dict[str, str]]:
    files = []
    for item in group.get("files", []):
        path = item.get("path")
        sha256 = item.get("sha256")
        if item.get("missing") or not isinstance(path, str) or not isinstance(sha256, str):
            raise ValueError(f"{label} source binding is incomplete")
        files.append({"path": path, "sha256": sha256})
    if not files:
        raise ValueError(f"{label} source binding is empty")
    return sorted(files, key=lambda item: item["path"])


def compile_definitions(
    fixture_entries: list[tuple[Path, dict[str, Any]]],
    app_verification: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if app_verification.get("status") != "passed":
        raise ValueError("V2 application verification did not pass")
    if app_verification.get("protocolParity") is not True:
        raise ValueError("V2 application protocol parity did not pass")
    receipts = {item.get("app"): item for item in app_verification.get("apps", [])}
    fixtures: list[dict[str, Any]] = []
    definitions: list[dict[str, Any]] = []

    for fixture_path, source_fixture in fixture_entries:
        app = source_fixture["app"]
        expected_commit = FROZEN_PRODUCTION_COMMITS.get(app)
        receipt = receipts.get(app)
        if expected_commit is None or receipt is None:
            raise ValueError(f"missing frozen V2 application receipt for {app}")
        if receipt.get("passed") is not True or receipt.get("clean") is not True:
            raise ValueError(f"V2 application receipt is not clean and passed for {app}")
        if receipt.get("adapterCommit") != expected_commit:
            raise ValueError(
                f"{app} adapter commit {receipt.get('adapterCommit')} does not match "
                f"frozen production commit {expected_commit}"
            )

        fixture_receipt = next(
            (
                item
                for item in receipt.get("fixtures", [])
                if item.get("studyFixture") == fixture_path.name
            ),
            None,
        )
        if fixture_receipt is None or fixture_receipt.get("parity") is not True:
            raise ValueError(f"fixture parity is missing for {fixture_path.name}")

        authoring = receipt.get("authoring", {})
        definition = {
            "schemaVersion": "node.workflow-resolved-definition/v1",
            "profile": "resident-local-v2",
            "application": {
                "app": app,
                "productionCommit": expected_commit,
                "workflow": source_fixture["workflow"],
            },
            "fixture": {
                "sourceFixtureId": source_fixture["fixtureId"],
                "fixtureId": v2_fixture_id(source_fixture["fixtureId"]),
                "sourcePath": f"fixtures/{fixture_path.name}",
                "sha256": fixture_receipt["studyFixtureSha256"],
            },
            "protocol": {
                "schemaVersion": SCHEMA_VERSION,
                "path": receipt["protocol"],
                "sha256": receipt["protocolSha256"],
            },
            "sourceBindings": {
                "applicationAdapter": source_bindings(
                    authoring.get("applicationAdapter", {}), "application adapter"
                ),
                "domainTools": source_bindings(
                    authoring.get("domainTools", {}), "domain tools"
                ),
                "verification": source_bindings(
                    authoring.get("verification", {}), "verification"
                ),
            },
            "executionPolicy": copy.deepcopy(EXECUTION_POLICY),
            "costPolicy": {
                "cloudCalls": 0,
                "cloudCostUsd": 0,
                "modelCalls": 0,
                "modelCostUsd": 0,
            },
        }
        definition_digest = digest(definition)
        bound_fixture = copy.deepcopy(source_fixture)
        bound_fixture.update(
            {
                "appCommit": expected_commit,
                "definitionDigest": definition_digest,
                "fixtureId": definition["fixture"]["fixtureId"],
                "sourceFixtureId": source_fixture["fixtureId"],
                "unitTimeoutMs": EXECUTION_POLICY["unitTimeoutMs"],
            }
        )
        fixtures.append(bound_fixture)
        definitions.append(
            {"definitionDigest": definition_digest, "definition": definition}
        )

    bundle = {
        "schemaVersion": "node.workflow-resolved-definitions/v1",
        "profile": "resident-local-v2",
        "definitions": sorted(
            definitions,
            key=lambda item: item["definition"]["fixture"]["fixtureId"],
        ),
    }
    return fixtures, bundle


def request_for_v2(fixture: dict[str, Any], variant: str, repetition: int) -> dict[str, Any]:
    request_input = {
        "app": fixture["app"],
        "baseVersion": fixture.get("baseVersion"),
        "definitionDigest": fixture["definitionDigest"],
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
        "definitionDigest": fixture["definitionDigest"],
        "idempotencyKey": f"{fixture['fixtureId']}:{variant}:rep-{repetition:02d}",
        "concurrency": fixture["concurrency"],
        "deadlineMs": fixture["deadlineMs"],
        "unitTimeoutMs": fixture["unitTimeoutMs"],
    }
    if fixture.get("baseVersion") is not None:
        request["baseVersion"] = fixture["baseVersion"]
    if variant == "hard-failure":
        request["failureSeed"] = fixture["units"][0]["id"]
    return request
