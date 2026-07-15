#!/usr/bin/env python3
"""Run the pre-registered RocketRide Cloud operational appendix."""

from __future__ import annotations

import argparse
import asyncio
import copy
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import time
from typing import Any
import uuid


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
RUNS = HERE / "runs"
CONTROL_PIPE = HERE / "cloud-control.pipe"
EXACT_PIPE = (
    REPO
    / "concurrent-work"
    / "harness"
    / "rocketride-bench"
    / "groups"
    / "robustness-and-isolation"
    / "fault-isolation"
    / "pipeline.pipe"
)
UPSTREAM_COMMIT = "43be41acb58558dfae8e2e3deb86d8a00cb1b1c8"
PREREG_COMMIT = "572f651"
URI = "https://api.rocketride.ai"
PROMO_CODE = "JULY2026BENCHMARK"
POOL_SIZE = 4
DOCUMENTS = 16
REPETITIONS = 3
SEND_TIMEOUT_SECONDS = 120
USE_TIMEOUT_SECONDS = 180
SOURCE_FILES = (
    "PRE_REGISTRATION.md",
    "SETUP_ATTEMPTS.md",
    "RUN_HISTORY.md",
    "README.md",
    "cloud-control.pipe",
    "run_cloud_appendix.py",
    "audit_cloud_appendix.py",
    "test_cloud_appendix.py",
)
SENSITIVE_KEY_PARTS = (
    "token",
    "auth",
    "apikey",
    "api_key",
    "secret",
    "credential",
    "email",
    "phone",
    "userid",
    "user_id",
    "orgid",
    "org_id",
    "organization",
    "teamid",
    "team_id",
    "subscriptionid",
    "subscription_id",
    "promotioncodeid",
    "customer",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_ready(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if hasattr(value, "_asdict"):
        return json_ready(value._asdict())
    if hasattr(value, "__dict__"):
        return json_ready(vars(value))
    return value


def sanitize(value: Any, forbidden_values: tuple[str, ...] = ()) -> Any:
    """Redact identifiers and credentials while preserving evidence shape."""
    value = json_ready(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized != "tokens" and any(
                part in normalized for part in SENSITIVE_KEY_PARTS
            ):
                if item in (None, "", [], {}):
                    result[key] = item
                else:
                    result[key] = "sha256:" + sha256_text(canonical_json(item))
            else:
                result[key] = sanitize(item, forbidden_values)
        return result
    if isinstance(value, list):
        return [sanitize(item, forbidden_values) for item in value]
    if isinstance(value, str):
        result = value
        for forbidden in forbidden_values:
            if forbidden:
                result = result.replace(forbidden, "<redacted>")
        result = result.replace(str(REPO), "<repo>")
        return result
    return value


def safe_error(exc: BaseException, secret: str) -> str:
    return str(sanitize(str(exc), (secret,)))[:2000]


def load_external_env(path: Path) -> dict[str, str]:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(REPO.resolve())
    except ValueError:
        pass
    else:
        raise RuntimeError("credential environment file must be outside the repository")
    if not resolved.is_file():
        raise RuntimeError(f"credential environment file not found: {resolved}")
    values: dict[str, str] = {}
    for raw_line in resolved.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_pipe(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError(f"pipeline is not an object: {path}")
    nested = parsed.get("pipeline")
    return nested if isinstance(nested, dict) else parsed


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=REPO, text=True, encoding="utf-8"
    ).strip()


def make_client(uri: str, key: str) -> Any:
    from rocketride import RocketRideClient

    return RocketRideClient(
        uri=uri,
        auth=key,
        env={},
        module="proofloop-cloud-appendix",
        request_timeout=120000,
        max_retry_time=30000,
    )


async def connect_client(uri: str, key: str) -> tuple[Any, dict[str, Any]]:
    client = make_client(uri, key)
    result = await asyncio.wait_for(client.connect(timeout=30000), timeout=45)
    return client, json_ready(result)


async def disconnect_quietly(client: Any) -> None:
    try:
        await client.disconnect()
    except Exception:
        pass


def terminal_status(status: Any) -> bool:
    status = json_ready(status)
    if not isinstance(status, dict):
        return False
    if status.get("completed") is True:
        return True
    state = status.get("state")
    if isinstance(state, (int, float)) and state >= 5:
        return True
    return str(state).lower() in {
        "completed",
        "failed",
        "stopped",
        "terminated",
        "canceled",
        "cancelled",
    }


def marker_evidence(response: Any, expected: str, all_markers: list[str]) -> dict[str, Any]:
    serialized = canonical_json(json_ready(response))
    seen = sorted(marker for marker in all_markers if marker in serialized)
    sanitized_response = sanitize(response)
    sanitized_serialized = canonical_json(sanitized_response)
    return {
        "markerPresent": expected in serialized,
        "crossTaskLeak": any(marker != expected for marker in seen),
        "seenMarkers": seen,
        "responseBytes": len(serialized.encode("utf-8")),
        "responseSha256": sha256_text(serialized),
        "sanitizedResponse": sanitized_response,
        "sanitizedResponseSha256": sha256_text(sanitized_serialized),
    }


async def send_record(
    *,
    client: Any,
    token: str,
    marker: str,
    all_markers: list[str],
    phase: str,
    repetition: int,
    task_index: int,
    document_index: int | None,
    secret: str,
) -> dict[str, Any]:
    payload = f"proofloop-marker={marker}\nsynthetic hosted isolation document"
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            client.send(
                token,
                payload,
                objinfo={"name": f"{marker}.txt"},
                mimetype="text/plain",
            ),
            timeout=SEND_TIMEOUT_SECONDS,
        )
        evidence = marker_evidence(response, marker, all_markers)
        return {
            "phase": phase,
            "repetition": repetition,
            "taskIndex": task_index,
            "documentIndex": document_index,
            "expectedMarker": marker,
            "ok": True,
            "latencyMs": (time.perf_counter() - started) * 1000.0,
            **evidence,
        }
    except Exception as exc:
        return {
            "phase": phase,
            "repetition": repetition,
            "taskIndex": task_index,
            "documentIndex": document_index,
            "expectedMarker": marker,
            "ok": False,
            "latencyMs": (time.perf_counter() - started) * 1000.0,
            "markerPresent": False,
            "crossTaskLeak": False,
            "seenMarkers": [],
            "error": safe_error(exc, secret),
            "errorType": type(exc).__name__,
        }


async def terminate_and_observe(slot: dict[str, Any], secret: str) -> dict[str, Any]:
    record = {
        "taskIndex": slot["taskIndex"],
        "taskTokenHash": sha256_text(slot["token"]),
        "terminateCallSucceeded": False,
        "terminalStateObserved": False,
    }
    try:
        await asyncio.wait_for(slot["client"].terminate(slot["token"]), timeout=30)
        record["terminateCallSucceeded"] = True
    except Exception as exc:
        record["terminateError"] = safe_error(exc, secret)
    deadline = time.perf_counter() + 15
    while time.perf_counter() < deadline:
        await asyncio.sleep(0.25)
        try:
            status = await asyncio.wait_for(
                slot["client"].get_task_status(slot["token"]), timeout=10
            )
            record["lastStatus"] = sanitize(status)
            if terminal_status(status):
                record["terminalStateObserved"] = True
                break
        except Exception as exc:
            text = safe_error(exc, secret)
            record["statusError"] = text
            if any(term in text.lower() for term in ("not found", "terminated", "closed")):
                record["terminalStateObserved"] = True
            break
    return record


async def exact_upstream_attempt(uri: str, key: str) -> dict[str, Any]:
    started_at = utc_now()
    started = time.perf_counter()
    client = None
    task_token = None
    try:
        client, _ = await connect_client(uri, key)
        result = await asyncio.wait_for(
            client.use(
                pipeline=load_pipe(EXACT_PIPE),
                threads=1,
                ttl=120,
                use_existing=False,
                pipelineTraceLevel="full",
                name="proofloop-exact-upstream-cloud-attempt",
            ),
            timeout=USE_TIMEOUT_SECONDS,
        )
        task_token = str(result["token"])
        return {
            "startedAt": started_at,
            "durationMs": (time.perf_counter() - started) * 1000.0,
            "pipelinePath": EXACT_PIPE.relative_to(REPO).as_posix(),
            "pipelineSha256": sha256_bytes(EXACT_PIPE.read_bytes()),
            "status": "started",
            "exactUpstreamCloudStatus": "started_requires_input_environment",
            "taskTokenHash": sha256_text(task_token),
            "sanitizedStartResponse": sanitize(result),
        }
    except Exception as exc:
        error = safe_error(exc, key)
        missing_workload = "workload" in error.lower() and "not found" in error.lower()
        return {
            "startedAt": started_at,
            "durationMs": (time.perf_counter() - started) * 1000.0,
            "pipelinePath": EXACT_PIPE.relative_to(REPO).as_posix(),
            "pipelineSha256": sha256_bytes(EXACT_PIPE.read_bytes()),
            "status": "blocked" if missing_workload else "failed",
            "exactUpstreamCloudStatus": (
                "blocked_missing_workload_service" if missing_workload else "failed_other"
            ),
            "errorType": type(exc).__name__,
            "error": error,
            "errorSha256": sha256_text(error),
        }
    finally:
        if client is not None and task_token:
            try:
                await client.terminate(task_token)
            except Exception:
                pass
        if client is not None:
            await disconnect_quietly(client)


async def run_repetition(
    *, uri: str, key: str, run_id: str, repetition: int
) -> dict[str, Any]:
    control = load_pipe(CONTROL_PIPE)
    slots: list[dict[str, Any]] = []
    cleanup: list[dict[str, Any]] = []
    started = time.perf_counter()

    async def bring_up(task_index: int) -> dict[str, Any]:
        client, _ = await connect_client(uri, key)
        config = copy.deepcopy(control)
        config["project_id"] = str(uuid.uuid4())
        try:
            use_started = time.perf_counter()
            result = await asyncio.wait_for(
                client.use(
                    pipeline=config,
                    threads=1,
                    ttl=300,
                    use_existing=True,
                    pipelineTraceLevel="full",
                    name=f"proofloop-cloud-r{repetition}-t{task_index}",
                ),
                timeout=USE_TIMEOUT_SECONDS,
            )
            token = str(result["token"])
            return {
                "client": client,
                "token": token,
                "taskIndex": task_index,
                "taskTokenHash": sha256_text(token),
                "startMs": (time.perf_counter() - use_started) * 1000.0,
                "sanitizedStartResponse": sanitize(result),
            }
        except BaseException:
            await disconnect_quietly(client)
            raise

    brought_up = await asyncio.gather(
        *(bring_up(index) for index in range(POOL_SIZE)), return_exceptions=True
    )
    failures = [item for item in brought_up if isinstance(item, BaseException)]
    slots = [item for item in brought_up if isinstance(item, dict)]
    if failures:
        for slot in slots:
            cleanup.append(await terminate_and_observe(slot, key))
            await disconnect_quietly(slot["client"])
        raise RuntimeError(
            "resident pool bring-up failed: "
            + "; ".join(safe_error(item, key) for item in failures)
        )
    slots.sort(key=lambda item: item["taskIndex"])

    warmups: list[dict[str, Any]] = []
    normal_records: list[dict[str, Any]] = []
    failure_records: list[dict[str, Any]] = []
    targeted_termination: dict[str, Any] = {}
    try:
        warm_markers = [
            f"RR_CLOUD_{run_id}_R{repetition:02d}_T{index:02d}_WARM"
            for index in range(POOL_SIZE)
        ]
        warmups = await asyncio.gather(
            *(
                send_record(
                    client=slot["client"],
                    token=slot["token"],
                    marker=warm_markers[index],
                    all_markers=warm_markers,
                    phase="warmup",
                    repetition=repetition,
                    task_index=index,
                    document_index=None,
                    secret=key,
                )
                for index, slot in enumerate(slots)
            )
        )
        if not all(item["ok"] and item["markerPresent"] for item in warmups):
            raise RuntimeError("one or more resident task warm-ups failed")

        normal_markers = [
            f"RR_CLOUD_{run_id}_R{repetition:02d}_D{index:03d}"
            for index in range(DOCUMENTS)
        ]
        failure_markers = [
            f"RR_CLOUD_{run_id}_R{repetition:02d}_FAIL_T{index:02d}"
            for index in range(POOL_SIZE)
        ]
        all_markers = normal_markers + failure_markers
        assignments = [list(range(index, DOCUMENTS, POOL_SIZE)) for index in range(POOL_SIZE)]

        async def normal_worker(task_index: int) -> list[dict[str, Any]]:
            slot = slots[task_index]
            records = []
            for document_index in assignments[task_index]:
                records.append(
                    await send_record(
                        client=slot["client"],
                        token=slot["token"],
                        marker=normal_markers[document_index],
                        all_markers=all_markers,
                        phase="normal",
                        repetition=repetition,
                        task_index=task_index,
                        document_index=document_index,
                        secret=key,
                    )
                )
            return records

        worker_results = await asyncio.gather(
            *(normal_worker(index) for index in range(POOL_SIZE))
        )
        normal_records = sorted(
            [record for records in worker_results for record in records],
            key=lambda item: item["documentIndex"],
        )

        targeted_termination = await terminate_and_observe(slots[0], key)
        cleanup.append(targeted_termination)
        failure_records = await asyncio.gather(
            *(
                send_record(
                    client=slot["client"],
                    token=slot["token"],
                    marker=failure_markers[index],
                    all_markers=all_markers,
                    phase="failure",
                    repetition=repetition,
                    task_index=index,
                    document_index=None,
                    secret=key,
                )
                for index, slot in enumerate(slots)
            )
        )
    finally:
        terminated_indexes = {item["taskIndex"] for item in cleanup}
        for slot in slots:
            if slot["taskIndex"] not in terminated_indexes:
                cleanup.append(await terminate_and_observe(slot, key))
        for slot in slots:
            await disconnect_quietly(slot["client"])

    return {
        "repetition": repetition,
        "poolSize": POOL_SIZE,
        "documentCount": DOCUMENTS,
        "poolBringUpMs": (time.perf_counter() - started) * 1000.0,
        "tasks": [
            {
                "taskIndex": slot["taskIndex"],
                "taskTokenHash": slot["taskTokenHash"],
                "startMs": slot["startMs"],
                "sanitizedStartResponse": slot["sanitizedStartResponse"],
            }
            for slot in slots
        ],
        "warmups": warmups,
        "normal": normal_records,
        "failure": failure_records,
        "targetedTermination": targeted_termination,
        "cleanup": sorted(cleanup, key=lambda item: item["taskIndex"]),
    }


def first_matching(mapping: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(mapping, dict):
        lowered = {str(key).lower(): value for key, value in mapping.items()}
        for key in keys:
            if key.lower() in lowered:
                return lowered[key.lower()]
        for value in mapping.values():
            found = first_matching(value, keys)
            if found is not None:
                return found
    elif isinstance(mapping, list):
        for value in mapping:
            found = first_matching(value, keys)
            if found is not None:
                return found
    return None


def account_organizations(account: Any) -> list[dict[str, Any]]:
    """Accept both the documented plural and current Cloud singular shape."""
    if not isinstance(account, dict):
        return []
    plural = account.get("organizations")
    if isinstance(plural, list):
        return [item for item in plural if isinstance(item, dict)]
    singular = account.get("organization")
    if isinstance(singular, dict):
        return [singular]
    return []


def starter_monthly_price(plans: Any) -> dict[str, Any] | None:
    if not isinstance(plans, list):
        return None
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        label = plan.get("label", plan.get("nickname"))
        if str(label).lower() != "starter":
            continue
        if str(plan.get("interval", "")).lower() != "month":
            continue
        price_id = plan.get("priceId", plan.get("stripePriceId"))
        cents = plan.get("cents", plan.get("amountCents"))
        if not price_id or not isinstance(cents, int):
            continue
        return {
            "label": label,
            "amount": plan.get("amount", f"${cents / 100:g}"),
            "cents": cents,
            "currency": plan.get("currency"),
            "interval": plan.get("interval"),
            "priceId": price_id,
        }
    return None


async def billing_snapshot(uri: str, key: str, label: str) -> dict[str, Any]:
    client = None
    try:
        client, account = await connect_client(uri, key)
        organizations = account_organizations(account)
        if not organizations:
            raise RuntimeError("connected account did not expose an organization")
        organization = organizations[0]
        org_id = str(organization["id"])
        apps = account.get("apps", []) if isinstance(account, dict) else []
        app = next(
            (
                item
                for item in apps
                if item.get("id") == "rocketride.pipeBuilder"
                or str(item.get("name", "")).lower() == "pipeline builder"
            ),
            {"id": "rocketride.pipeBuilder", "name": "Pipeline Builder"},
        )
        app_id = str(app["id"])
        subscriptions = json_ready(await client.billing.get_details(org_id))
        prices = json_ready(await client.billing.get_product_prices(app_id))
        starter = starter_monthly_price(prices)
        if not isinstance(starter, dict):
            raise RuntimeError("Starter monthly price was not returned")
        promo_arguments = {
            "orgId": org_id,
            "appId": app_id,
            "priceId": starter["priceId"],
            "code": PROMO_CODE,
        }
        promo = await client.call(
            "rrext_account_billing", subcommand="promo_validate", **promo_arguments
        )
        credits = await client.billing.get_credit_balance(org_id)
        subscription = next(
            (
                item
                for item in subscriptions
                if item.get("appId") == app_id
                or str(item.get("planNickname", "")).lower().startswith("starter")
            ),
            None,
        )
        return {
            "capturedAt": utc_now(),
            "label": label,
            "organizationIdHash": sha256_text(org_id),
            "appId": app_id,
            "promotionCode": PROMO_CODE,
            "starterPrice": {
                "label": starter.get("label"),
                "amount": starter.get("amount"),
                "cents": starter.get("cents"),
                "currency": starter.get("currency"),
                "interval": starter.get("interval"),
                "priceIdHash": sha256_text(str(starter.get("priceId"))),
            },
            "promoValidation": sanitize(promo, (key, org_id)),
            "subscription": sanitize(subscription, (key, org_id)),
            "creditBalance": sanitize(credits, (key, org_id)),
        }
    except Exception as exc:
        return {
            "capturedAt": utc_now(),
            "label": label,
            "errorType": type(exc).__name__,
            "error": safe_error(exc, key),
        }
    finally:
        if client is not None:
            await disconnect_quietly(client)


def all_numbers(value: Any, key_names: tuple[str, ...]) -> list[float]:
    values: list[float] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {name.lower() for name in key_names} and isinstance(
                item, (int, float)
            ):
                values.append(float(item))
            values.extend(all_numbers(item, key_names))
    elif isinstance(value, list):
        for item in value:
            values.extend(all_numbers(item, key_names))
    return values


def billing_gate(snapshot: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if snapshot.get("error"):
        return False, [f"billing snapshot failed: {snapshot['error']}"]
    promo = snapshot.get("promoValidation", {})
    valid = first_matching(promo, ("valid", "isValid"))
    percent = all_numbers(promo, ("percentOff", "percent_off", "discountPercent"))
    due = all_numbers(
        promo,
        (
            "discountedAmount",
            "discounted_amount",
            "discountedAmountCents",
            "amountDue",
            "amount_due",
            "finalAmount",
        ),
    )
    if valid is not True:
        issues.append("promotion validation did not report valid=true")
    if not percent or max(percent) < 100:
        issues.append("promotion validation did not report 100 percent off")
    if not due or min(due) != 0:
        issues.append("promotion validation did not report zero due")
    subscription = snapshot.get("subscription")
    if not isinstance(subscription, dict):
        issues.append("Starter subscription was not returned")
    else:
        if not str(subscription.get("planNickname", "")).lower().startswith("starter"):
            issues.append("active plan is not Starter")
        if subscription.get("status") != "active":
            issues.append("Starter subscription is not active")
        if subscription.get("cancelAtPeriodEnd") is not True:
            issues.append("paid renewal is not disabled")
    return not issues, issues


def summarize(repetitions: list[dict[str, Any]], billing: dict[str, Any]) -> dict[str, Any]:
    normal = [record for rep in repetitions for record in rep.get("normal", [])]
    failure = [record for rep in repetitions for record in rep.get("failure", [])]
    targeted = [record for record in failure if record.get("taskIndex") == 0]
    unaffected = [record for record in failure if record.get("taskIndex") != 0]
    cleanup = [record for rep in repetitions for record in rep.get("cleanup", [])]
    normal_lats = [float(record["latencyMs"]) for record in normal if record.get("ok")]
    unaffected_lats = [
        float(record["latencyMs"]) for record in unaffected if record.get("ok")
    ]
    billing_ok, billing_issues = billing_gate(billing)
    counts = {
        "repetitions": len(repetitions),
        "residentTasksCreated": sum(len(rep.get("tasks", [])) for rep in repetitions),
        "normalRequests": len(normal),
        "normalSucceededCorrectly": sum(
            record.get("ok") is True
            and record.get("markerPresent") is True
            and record.get("crossTaskLeak") is False
            for record in normal
        ),
        "unaffectedFailureRequests": len(unaffected),
        "unaffectedFailureSucceededCorrectly": sum(
            record.get("ok") is True
            and record.get("markerPresent") is True
            and record.get("crossTaskLeak") is False
            for record in unaffected
        ),
        "targetedTerminatedRequests": len(targeted),
        "targetedTerminatedRequestsFailed": sum(record.get("ok") is False for record in targeted),
        "crossTaskLeaks": sum(record.get("crossTaskLeak") is True for record in normal + failure),
        "cleanupRecords": len(cleanup),
        "terminateCallsSucceeded": sum(
            record.get("terminateCallSucceeded") is True for record in cleanup
        ),
    }
    issues = []
    expected = {
        "repetitions": REPETITIONS,
        "residentTasksCreated": REPETITIONS * POOL_SIZE,
        "normalRequests": REPETITIONS * DOCUMENTS,
        "normalSucceededCorrectly": REPETITIONS * DOCUMENTS,
        "unaffectedFailureRequests": REPETITIONS * (POOL_SIZE - 1),
        "unaffectedFailureSucceededCorrectly": REPETITIONS * (POOL_SIZE - 1),
        "targetedTerminatedRequests": REPETITIONS,
        "targetedTerminatedRequestsFailed": REPETITIONS,
        "crossTaskLeaks": 0,
        "cleanupRecords": REPETITIONS * POOL_SIZE,
        "terminateCallsSucceeded": REPETITIONS * POOL_SIZE,
    }
    for key, value in expected.items():
        if counts[key] != value:
            issues.append(f"{key}: expected {value}, found {counts[key]}")
    issues.extend(billing_issues)

    def metrics(values: list[float]) -> dict[str, float] | None:
        if not values:
            return None
        ordered = sorted(values)
        p95_index = min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))
        return {
            "min": min(values),
            "median": statistics.median(values),
            "p95": ordered[p95_index],
            "max": max(values),
        }

    return {
        "passed": not issues and billing_ok,
        "issues": issues,
        "counts": counts,
        "latencyMs": {
            "normal": metrics(normal_lats),
            "unaffectedFailurePhase": metrics(unaffected_lats),
        },
        "billingGatePassed": billing_ok,
    }


def capture_sources(run_root: Path) -> dict[str, Any]:
    destination = run_root / "executed-source"
    entries = []
    for relative in SOURCE_FILES:
        source = HERE / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        entries.append(
            {
                "path": relative,
                "bytes": source.stat().st_size,
                "sha256": sha256_bytes(source.read_bytes()),
            }
        )
    upstream_target = destination / "upstream-fault-isolation.pipe"
    shutil.copy2(EXACT_PIPE, upstream_target)
    entries.append(
        {
            "path": "upstream-fault-isolation.pipe",
            "bytes": EXACT_PIPE.stat().st_size,
            "sha256": sha256_bytes(EXACT_PIPE.read_bytes()),
        }
    )
    manifest = {"capturedAt": utc_now(), "files": entries}
    write_json(run_root / "source-manifest.json", manifest)
    return manifest


def artifact_manifest(run_root: Path) -> dict[str, Any]:
    excluded = {"artifact-manifest.json", "audit.json"}
    files = []
    for path in sorted(item for item in run_root.rglob("*") if item.is_file()):
        relative = path.relative_to(run_root).as_posix()
        if relative in excluded:
            continue
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256_bytes(path.read_bytes()),
            }
        )
    return {"schemaVersion": 1, "files": files}


def results_markdown(receipt: dict[str, Any]) -> str:
    summary = receipt["controlSummary"]
    counts = summary["counts"]
    exact = receipt["exactUpstreamAttempt"]
    billing = receipt["billingAfter"]
    status = "PASS" if summary["passed"] else "FAIL"
    return f"""# RocketRide Cloud Appendix Results

## Status

- Evidence status: `{receipt['evidenceStatus']}`
- Cloud control admission: `{receipt['controlAdmissionStatus']}`
- Exact upstream Cloud status: `{exact['exactUpstreamCloudStatus']}`
- Official status: `{receipt['officialStatus']}`
- Control gate: **{status}**

The unchanged upstream pipeline did not receive an official Cloud score. Its
hosted attempt returned `{exact.get('error', exact['status'])}`. The separate
built-in-service control used no model provider and made no paid model calls.

## Control Counts

| Check | Result |
|---|---:|
| Repetitions | {counts['repetitions']} |
| Resident tasks created | {counts['residentTasksCreated']} |
| Normal requests correct | {counts['normalSucceededCorrectly']}/{counts['normalRequests']} |
| Unaffected failure requests correct | {counts['unaffectedFailureSucceededCorrectly']}/{counts['unaffectedFailureRequests']} |
| Terminated-task requests failed as expected | {counts['targetedTerminatedRequestsFailed']}/{counts['targetedTerminatedRequests']} |
| Cross-task leaks | {counts['crossTaskLeaks']} |
| Successful task termination calls | {counts['terminateCallsSucceeded']}/{counts['cleanupRecords']} |

## Billing

- Promotion: `{billing.get('promotionCode')}`
- Starter checkout amount: `{billing.get('starterPrice', {}).get('amount')}`
- Billing gate passed: `{str(summary['billingGatePassed']).lower()}`
- Renewal disabled: `{str((billing.get('subscription') or {}).get('cancelAtPeriodEnd') is True).lower()}`

This appendix is independently auditable operational evidence. It remains
unsubmitted until RocketRide maintainers accept it, and it does not replace the
pinned local benchmark.
"""


async def run(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file)
    environment = load_external_env(env_file)
    key = environment.get("ROCKETRIDE_APIKEY", "")
    uri = environment.get("ROCKETRIDE_URI", URI)
    if not key:
        raise RuntimeError("ROCKETRIDE_APIKEY is missing from the external env file")
    if uri.rstrip("/") != URI:
        raise RuntimeError(f"pre-registered URI is {URI}, got {uri}")

    run_id = args.run_id or dt.datetime.now(dt.timezone.utc).strftime("cloud-%Y%m%dT%H%M%SZ")
    run_root = Path(args.output_root).resolve() / run_id
    if run_root.exists():
        raise RuntimeError(f"run directory already exists: {run_root}")
    run_root.mkdir(parents=True)
    started_at = utc_now()
    capture_sources(run_root)
    log_lines = [f"{started_at} run_started id={run_id}"]

    billing_before = await billing_snapshot(uri, key, "before")
    write_json(run_root / "billing-before.json", billing_before)
    log_lines.append(f"{utc_now()} billing_before_captured")

    exact = await exact_upstream_attempt(uri, key)
    write_json(run_root / "exact-upstream-attempt.json", exact)
    log_lines.append(
        f"{utc_now()} exact_upstream status={exact['exactUpstreamCloudStatus']}"
    )

    repetitions: list[dict[str, Any]] = []
    run_errors: list[str] = []
    for repetition in range(1, REPETITIONS + 1):
        try:
            record = await run_repetition(
                uri=uri, key=key, run_id=run_id, repetition=repetition
            )
            repetitions.append(record)
            write_json(run_root / f"repetition-{repetition:02d}.json", record)
            log_lines.append(f"{utc_now()} repetition={repetition} complete")
        except Exception as exc:
            error = safe_error(exc, key)
            run_errors.append(f"repetition {repetition}: {error}")
            log_lines.append(f"{utc_now()} repetition={repetition} failed error={error}")
            break

    billing_after = await billing_snapshot(uri, key, "after")
    write_json(run_root / "billing-after.json", billing_after)
    summary = summarize(repetitions, billing_after)
    summary["issues"].extend(run_errors)
    if run_errors:
        summary["passed"] = False

    current_commit = git_output("rev-parse", "HEAD")
    receipt = {
        "schemaVersion": 1,
        "runId": run_id,
        "startedAt": started_at,
        "endedAt": utc_now(),
        "evidenceStatus": "complete" if not run_errors else "incomplete",
        "controlAdmissionStatus": "passed" if summary["passed"] else "failed",
        "exactUpstreamCloudStatus": exact["exactUpstreamCloudStatus"],
        "officialStatus": "cloud_operational_appendix_unsubmitted",
        "claimBoundary": (
            "Cloud-native operational control only; not an upstream benchmark score "
            "and not an official RocketRide result."
        ),
        "protocol": {
            "poolSize": POOL_SIZE,
            "documentsPerRepetition": DOCUMENTS,
            "repetitions": REPETITIONS,
            "measuredRetries": 0,
            "modelCalls": 0,
            "paidModelCostUsd": 0,
            "cloudCheckoutChargeUsd": 0,
        },
        "provenance": {
            "upstreamCommit": UPSTREAM_COMMIT,
            "preRegistrationCommit": PREREG_COMMIT,
            "runnerCommit": current_commit,
            "rocketrideSdk": importlib.metadata.version("rocketride"),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "uri": uri,
            "credentialFingerprint": sha256_text(key),
            "credentialStoredOutsideRepository": True,
        },
        "exactUpstreamAttempt": exact,
        "controlSummary": summary,
        "billingBefore": billing_before,
        "billingAfter": billing_after,
        "repetitionFiles": [f"repetition-{index:02d}.json" for index in range(1, len(repetitions) + 1)],
        "runErrors": run_errors,
    }
    write_json(run_root / "receipt.json", receipt)
    (run_root / "RESULTS.md").write_text(results_markdown(receipt), encoding="utf-8")
    log_lines.append(
        f"{utc_now()} run_complete control={receipt['controlAdmissionStatus']} "
        f"exact={receipt['exactUpstreamCloudStatus']}"
    )
    (run_root / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    write_json(run_root / "artifact-manifest.json", artifact_manifest(run_root))
    write_json(
        HERE / "latest-run.json",
        {
            "runId": run_id,
            "path": f"runs/{run_id}",
            "receiptSha256": sha256_bytes((run_root / "receipt.json").read_bytes()),
            "controlAdmissionStatus": receipt["controlAdmissionStatus"],
            "exactUpstreamCloudStatus": receipt["exactUpstreamCloudStatus"],
            "officialStatus": receipt["officialStatus"],
        },
    )
    print(str(run_root))
    print(json.dumps(summary["counts"], sort_keys=True))
    print(f"control={receipt['controlAdmissionStatus']}")
    print(f"exact={receipt['exactUpstreamCloudStatus']}")
    return 0 if summary["passed"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env-file",
        default=os.environ.get("ROCKETRIDE_ENV_FILE"),
        help="External file containing ROCKETRIDE_URI and ROCKETRIDE_APIKEY",
    )
    parser.add_argument("--output-root", default=str(RUNS))
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if not args.env_file:
        parser.error("--env-file or ROCKETRIDE_ENV_FILE is required")
    return args


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(parse_args())))
    except KeyboardInterrupt:
        raise SystemExit(130)
