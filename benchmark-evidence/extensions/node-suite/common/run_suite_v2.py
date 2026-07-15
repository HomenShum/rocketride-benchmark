#!/usr/bin/env python3
"""Run the pre-registered V2 Node matrix against prewarmed RocketRide pools."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
from pathlib import Path
import time
from typing import Any

import run_suite as v1
from async_utils import close_warm_pool, send_with_timeout
from protocol import canonical_json, deadline_overrun_count
from resolved_definition import EXECUTION_POLICY, compile_definitions, request_for_v2


APP_VERIFICATION = v1.SUITE / "app-verification-v2.json"
PROFILE = "resident-local-v2"


def load_inputs() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if not APP_VERIFICATION.is_file():
        raise RuntimeError(
            "V2 application verifier receipt is missing; run run_app_verifiers.py "
            "with --output app-verification-v2.json first"
        )
    receipt = json.loads(APP_VERIFICATION.read_text(encoding="utf-8"))
    entries = [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(v1.FIXTURES.glob("*.json"))
    ]
    fixtures, definitions = compile_definitions(entries, receipt)
    return fixtures, definitions, receipt


def authoring_evidence_v2() -> dict[str, Any]:
    return {
        "interpretation": (
            "Physical and non-blank lines are descriptive, not semantic complexity scores."
        ),
        "sharedHarness": v1.source_metrics(
            [
                v1.HERE / "protocol.py",
                v1.HERE / "async_utils.py",
                v1.HERE / "resolved_definition.py",
                v1.HERE / "run_suite.py",
                v1.HERE / "run_suite_v2.py",
            ]
        ),
        "native": v1.source_metrics([v1.HERE / "native_executor.mjs"]),
        "rocketride": v1.source_metrics(
            [
                v1.HERE / "rocketride-node" / "nodeworkflow" / "IGlobal.py",
                v1.HERE / "rocketride-node" / "nodeworkflow" / "IInstance.py",
                v1.HERE / "rocketride-node" / "nodeworkflow" / "__init__.py",
                v1.HERE / "rocketride-node" / "nodeworkflow" / "services.json",
            ]
        ),
        "langchain": v1.source_metrics([v1.HERE / "langchain_executor.py"]),
        "verification": v1.source_metrics(
            [
                v1.HERE / "audit_run_v2.py",
                v1.HERE / "run_app_verifiers.py",
                v1.HERE / "test_resident_v2.py",
            ]
        ),
    }


async def create_pool(fixture: dict[str, Any]) -> Any:
    pool = v1.WarmPool(
        v1.workflow_pipe(),
        len(fixture["units"]),
        threads=EXECUTION_POLICY["threadsPerPipe"],
        ttl=EXECUTION_POLICY["ttlSeconds"],
        uri=v1.URI,
        trace_level=EXECUTION_POLICY["traceLevel"],
    )
    await pool.__aenter__()
    return pool


async def run_rocketride_request(
    *,
    pool: Any,
    fixture: dict[str, Any],
    failure_unit: str | None,
    trace_path: Path,
    pool_id: str,
    pool_lifecycle: str,
) -> dict[str, Any]:
    units = fixture["units"]
    engine_pid = v1.listener_pid(v1.PORT)
    rss_before, cpu_before = v1.process_tree_metrics(engine_pid or 0)
    completed: list[str] = []
    failed: list[str] = []
    send_failures: set[str] = set()
    send_durations: dict[str, float] = {}
    events: list[dict[str, Any]] = []
    execution_ms = 0.0
    total_ms = 0.0

    async with v1.TraceSink(uri=v1.URI) as sink:
        sink.clear()
        total_started = time.perf_counter()
        execution_started = time.perf_counter()
        send_timeout_s = float(fixture["unitTimeoutMs"]) / 1000.0

        async def send(index: int, unit: dict[str, Any]) -> None:
            unit_id = str(unit["id"])
            name = f"{unit_id}.txt"
            if unit_id == failure_unit:
                name = "crash__" + name
            send_started = time.perf_counter()
            try:
                await send_with_timeout(
                    pool.clients[index],
                    pool.tokens[index],
                    canonical_json(unit),
                    objinfo={"name": name},
                    mimetype="application/json",
                    timeout_seconds=send_timeout_s,
                )
            except Exception:
                send_failures.add(unit_id)
            finally:
                send_durations[unit_id] = (time.perf_counter() - send_started) * 1000.0

        await asyncio.gather(*(send(index, unit) for index, unit in enumerate(units)))
        execution_ms = (time.perf_counter() - execution_started) * 1000.0
        await sink.drain(EXECUTION_POLICY["traceDrainMs"] / 1000.0)
        events = sink.snapshot()
        total_ms = (time.perf_counter() - total_started) * 1000.0
        sink.write_jsonl(str(trace_path), events)
        v1.gzip_file(trace_path)

    for event in events:
        for text in v1.nested_strings(event):
            for marker in v1.MARKER.finditer(text):
                name = marker.group("name")
                unit_id = name.removeprefix("crash__").removesuffix(".txt")
                if marker.group("status") == "OK":
                    completed.append(unit_id)
                else:
                    failed.append(unit_id)
    completed = sorted(set(completed))
    failed = sorted(set(failed) | send_failures)
    for unit in units:
        unit_id = str(unit["id"])
        if unit_id not in completed and unit_id not in failed:
            failed.append(unit_id)

    rss_after, cpu_after = v1.process_tree_metrics(engine_pid or 0)
    return {
        "completed": completed,
        "failed": sorted(set(failed)),
        "totalMs": total_ms,
        "executionMs": execution_ms,
        "coldStartMs": 0,
        "warmupMs": float(pool.warm_s or 0) * 1000.0,
        "peakRssBytes": max(rss_before, rss_after),
        "cpuTimeMs": max(0.0, cpu_after - cpu_before),
        "serverHealthyAfter": v1.healthy(v1.PORT),
        "poolId": pool_id,
        "poolLifecycle": pool_lifecycle,
        "sendDurationsMs": send_durations,
    }


def decorate_result(
    result: dict[str, Any],
    fixture: dict[str, Any],
    framework: str,
    execution: dict[str, Any],
) -> None:
    result["definitionDigest"] = fixture["definitionDigest"]
    result["provenance"]["definitionDigest"] = fixture["definitionDigest"]
    result["provenance"]["servingProfile"] = PROFILE
    result["runtimeLifecycle"] = {
        "profile": PROFILE,
        "startupExcludedFromTotalMs": framework == "rocketride",
        "poolId": execution.get("poolId"),
        "poolLifecycle": execution.get("poolLifecycle", "subprocess_per_request"),
        "unitTimeoutMs": fixture["unitTimeoutMs"],
    }
    if framework == "rocketride":
        result["runtimeLifecycle"]["sendDurationsMs"] = execution.get(
            "sendDurationsMs", {}
        )


async def run_cell(
    *,
    fixture: dict[str, Any],
    variant: str,
    repetition: int,
    directory: Path,
    pool: Any,
    pool_id: str,
    pool_lifecycle: str,
) -> dict[str, dict[str, Any]]:
    failure_unit = fixture["units"][0]["id"] if variant == "hard-failure" else None
    request = request_for_v2(fixture, variant, repetition)
    v1.write_json(directory / "request.json", request)
    payload = {
        "units": fixture["units"],
        "concurrency": fixture["concurrency"],
        "delayMs": fixture["delayMs"],
        "failureUnit": failure_unit,
    }
    native_execution = v1.subprocess_executor(
        ["node", str(v1.HERE / "native_executor.mjs")], payload, directory, "native"
    )
    langchain_execution = v1.subprocess_executor(
        [str(v1.VENV_PY), str(v1.HERE / "langchain_executor.py")],
        payload,
        directory,
        "langchain",
    )
    rocketride_execution = await run_rocketride_request(
        pool=pool,
        fixture=fixture,
        failure_unit=failure_unit,
        trace_path=directory / "rocketride-trace.jsonl",
        pool_id=pool_id,
        pool_lifecycle=pool_lifecycle,
    )
    executions = {
        "native": (
            native_execution,
            "node-worker-threads",
            native_execution.get("runtimeVersion", v1.process_version("node")),
        ),
        "rocketride": (rocketride_execution, "rocketride-engine", v1.engine_version()),
        "langchain": (
            langchain_execution,
            "python-langchain",
            "python={python};langchain-core={langchain}".format(
                python=langchain_execution.get("runtimeVersion", "unknown"),
                langchain=langchain_execution.get("langchainCoreVersion", "0.3.86"),
            ),
        ),
    }
    results: dict[str, dict[str, Any]] = {}
    for framework, (execution, runtime, runtime_version) in executions.items():
        result = v1.result_for(
            fixture=fixture,
            request=request,
            framework=framework,
            repetition=repetition,
            execution=execution,
            runtime=runtime,
            runtime_version=str(runtime_version),
            adapter_version="2.0.0",
        )
        decorate_result(result, fixture, framework, execution)
        v1.write_json(directory / f"{framework}-result.json", result)
        results[framework] = result
    print(
        f"{fixture['fixtureId']} {variant} rep-{repetition:02d}: "
        f"native={len(native_execution.get('completed', []))} "
        f"rr={len(rocketride_execution.get('completed', []))} "
        f"lc={len(langchain_execution.get('completed', []))} "
        f"rr_total_ms={rocketride_execution['totalMs']:.3f}",
        flush=True,
    )
    return results


def aggregate_v2(
    *,
    run_root: Path,
    records: list[dict[str, Any]],
    engine_cold_ms: float,
    app_verification: dict[str, Any],
    definitions: dict[str, Any],
    lifecycle: dict[str, Any],
) -> dict[str, Any]:
    frameworks = ("native", "rocketride", "langchain")
    rows = []
    gate_issues: list[str] = []
    for fixture in records:
        expected = len(fixture["units"])
        deadline_ms = int(fixture["deadlineMs"])
        for variant in ("normal", "hard-failure"):
            for framework in frameworks:
                results = fixture["results"][variant][framework]
                overruns = deadline_overrun_count(results, deadline_ms)
                totals = [float(result["metrics"]["totalMs"]) for result in results]
                executions = [
                    float(result["metrics"]["executionMs"]) for result in results
                ]
                warmups = [float(result["metrics"]["warmupMs"]) for result in results]
                completed = [int(result["metrics"]["completedUnits"]) for result in results]
                failed = [int(result["metrics"]["failedUnits"]) for result in results]
                healthy_after = [
                    result["metrics"].get("runtimeHealthyAfter") for result in results
                ]
                rows.append(
                    {
                        "fixtureId": fixture["fixtureId"],
                        "app": fixture["app"],
                        "variant": variant,
                        "framework": framework,
                        "repetitions": len(results),
                        "totalMs": v1.metric(totals),
                        "executionMs": v1.metric(executions),
                        "warmupMs": v1.metric(warmups),
                        "completedUnits": v1.metric([float(value) for value in completed]),
                        "failedUnits": v1.metric([float(value) for value in failed]),
                        "runtimeHealthyAfter": {
                            "reported": sum(isinstance(value, bool) for value in healthy_after),
                            "healthy": sum(value is True for value in healthy_after),
                        },
                        "deadlineMs": deadline_ms,
                        "deadlineOverruns": overruns,
                        "candidateDigest": results[0]["outputDigest"],
                        "definitionDigest": fixture["definitionDigest"],
                        "modelCalls": 0,
                        "modelCostUsd": 0,
                        "cloudCostUsd": 0,
                    }
                )
                if overruns:
                    gate_issues.append(
                        f"{fixture['fixtureId']} {variant} {framework}: "
                        f"{overruns}/{len(results)} repetitions exceeded {deadline_ms} ms"
                    )
                if any(
                    result.get("definitionDigest") != fixture["definitionDigest"]
                    or result.get("provenance", {}).get("definitionDigest")
                    != fixture["definitionDigest"]
                    for result in results
                ):
                    gate_issues.append(
                        f"{fixture['fixtureId']} {variant} {framework}: definition binding failed"
                    )
                if variant == "normal":
                    if any(value != expected for value in completed) or any(failed):
                        gate_issues.append(
                            f"{fixture['fixtureId']} {framework}: normal run incomplete"
                        )
                elif framework in ("native", "rocketride"):
                    if any(value != expected - 1 for value in completed) or any(
                        value != 1 for value in failed
                    ):
                        gate_issues.append(
                            f"{fixture['fixtureId']} {framework}: hard-failure isolation failed"
                        )
                    if framework == "rocketride" and any(
                        value is not True for value in healthy_after
                    ):
                        gate_issues.append(
                            f"{fixture['fixtureId']} rocketride: engine unhealthy after fault"
                        )
            digests = {
                result["outputDigest"]
                for framework in frameworks
                for result in fixture["results"][variant][framework]
            }
            if len(digests) != 1:
                gate_issues.append(
                    f"{fixture['fixtureId']} {variant}: candidate digest parity failed"
                )

    pool_events = lifecycle["rocketridePools"]
    normal_warmups = [
        float(item["warmupMs"]) for item in pool_events if item["variant"] == "normal"
    ]
    fault_warmups = [
        float(item["warmupMs"])
        for item in pool_events
        if item["variant"] == "hard-failure"
    ]
    scorecard = {
        "schemaVersion": "node.workflow-extension-scorecard/v2",
        "generatedAt": v1.utc_now(),
        "status": "passed" if not gate_issues else "incomplete",
        "officialStatus": "separate_application_study_unsubmitted",
        "profile": PROFILE,
        "engineColdStartMs": round(engine_cold_ms, 3),
        "environment": v1.environment_evidence(),
        "conditions": {
            "deterministic": True,
            "paidModelCalls": 0,
            "cloudRuns": 0,
            "sameCandidateDigestRequired": True,
            "sameResolvedDefinitionRequired": True,
            "finalWritesAttempted": 0,
            "requestDeadlineMs": EXECUTION_POLICY["deadlineMs"],
            "unitTimeoutMs": EXECUTION_POLICY["unitTimeoutMs"],
        },
        "v1Result": {
            "runId": "node-suite-20260715T150250Z",
            "protocolAdmissionStatus": "failed",
            "deadlineIssueCount": 30,
            "superseded": False,
        },
        "standingRuntime": {
            "engineColdStartMs": round(engine_cold_ms, 3),
            "normalPoolWarmupMs": v1.metric(normal_warmups),
            "hardFailureReplacementWarmupMs": v1.metric(fault_warmups),
            "poolCount": len(pool_events),
            "requestTotalExcludesRocketRideStartup": True,
        },
        "rows": rows,
        "authoring": authoring_evidence_v2(),
        "appVerification": app_verification,
        "resolvedDefinitions": definitions,
        "gateIssues": gate_issues,
    }
    v1.write_json(run_root / "scorecard.json", scorecard)
    return scorecard


def report_v2(scorecard: dict[str, Any]) -> str:
    lines = [
        "# Node Application Resident-Runtime Study V2",
        "",
        f"Gate status: **{scorecard['status']}**. External status: **{scorecard['officialStatus']}**.",
        "",
        "V1 remains a failed protocol result with 30 RocketRide deadline overruns; V2 does not replace it.",
        "All V2 work is deterministic and local. Model and cloud cost are USD 0.",
        "RocketRide request totals exclude separately reported engine and pool readiness costs under the pre-registered resident topology.",
        "",
        "| App | Variant | Framework | Completed p50 | Failed p50 | Deadline overruns | Request p50 ms | Request p95 ms | Standing warmup p50 ms |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in scorecard["rows"]:
        lines.append(
            "| {app} | {variant} | {framework} | {completed} | {failed} | {overruns} | {p50} | {p95} | {warmup} |".format(
                app=row["app"],
                variant=row["variant"],
                framework=row["framework"],
                completed=row["completedUnits"]["median"],
                failed=row["failedUnits"]["median"],
                overruns=row["deadlineOverruns"],
                p50=row["totalMs"]["median"],
                p95=row["totalMs"]["p95"],
                warmup=row["warmupMs"]["median"],
            )
        )
    standing = scorecard["standingRuntime"]
    lines.extend(
        [
            "",
            "## Standing And Recovery Cost",
            "",
            f"- Engine cold start: {standing['engineColdStartMs']} ms.",
            f"- Normal pool warmup p50: {standing['normalPoolWarmupMs']['median']} ms.",
            f"- Hard-failure replacement warmup p50: {standing['hardFailureReplacementWarmupMs']['median']} ms.",
            f"- Pools provisioned: {standing['poolCount']}.",
            "",
            "## Boundaries",
            "",
            "- The 10,000 ms request deadline and all frozen candidates are unchanged.",
            "- A fixed 2,000 ms per-unit timeout bounds failed RocketRide sends.",
            "- Native and LangChain retain subprocess wall-clock measurement, including startup.",
            "- Product correctness comes from clean merged-commit app verifier receipts.",
            "- Candidate executors have no application mutation authority.",
            "- Local promotion eligibility is not an official RocketRide result.",
        ]
    )
    if scorecard["gateIssues"]:
        lines.extend(["", "## Gate Issues", ""])
        lines.extend(f"- {issue}" for issue in scorecard["gateIssues"])
    return "\n".join(lines) + "\n"


async def run(args: argparse.Namespace) -> int:
    if args.repetitions != EXECUTION_POLICY["repetitions"]:
        raise RuntimeError(
            f"V2 is pre-registered for exactly {EXECUTION_POLICY['repetitions']} repetitions"
        )
    run_id = args.run_id or dt.datetime.now(dt.timezone.utc).strftime(
        "node-suite-v2-%Y%m%dT%H%M%SZ"
    )
    run_root = v1.RUNS / run_id
    fixtures, definitions, app_verification = load_inputs()
    run_root.mkdir(parents=True, exist_ok=False)
    v1.write_json(run_root / "resolved-definitions.json", definitions)
    v1.write_json(run_root / "app-verification.json", app_verification)
    engine_process = None
    engine_cold_ms = 0.0
    records: list[dict[str, Any]] = []
    lifecycle: dict[str, Any] = {
        "schemaVersion": "node.workflow-runtime-lifecycle/v2",
        "profile": PROFILE,
        "rocketridePools": [],
    }
    try:
        engine_process, engine_cold_ms = v1.start_engine(run_root / "engine.log")
        await v1.validate_pipe(v1.workflow_pipe(), run_root)
        for fixture in fixtures:
            record = {
                "fixtureId": fixture["fixtureId"],
                "app": fixture["app"],
                "deadlineMs": fixture["deadlineMs"],
                "definitionDigest": fixture["definitionDigest"],
                "units": fixture["units"],
                "results": {
                    "normal": {"native": [], "rocketride": [], "langchain": []},
                    "hard-failure": {
                        "native": [],
                        "rocketride": [],
                        "langchain": [],
                    },
                },
            }

            normal_pool = await create_pool(fixture)
            normal_pool_id = f"{fixture['fixtureId']}:normal:resident"
            lifecycle["rocketridePools"].append(
                {
                    "poolId": normal_pool_id,
                    "fixtureId": fixture["fixtureId"],
                    "variant": "normal",
                    "repetitionScope": "all",
                    "warmupMs": round(float(normal_pool.warm_s or 0) * 1000.0, 3),
                    "retiredReason": "fixture_complete",
                }
            )
            try:
                for repetition in range(1, args.repetitions + 1):
                    directory = (
                        run_root
                        / fixture["fixtureId"]
                        / "normal"
                        / f"rep-{repetition:02d}"
                    )
                    directory.mkdir(parents=True, exist_ok=True)
                    results = await run_cell(
                        fixture=fixture,
                        variant="normal",
                        repetition=repetition,
                        directory=directory,
                        pool=normal_pool,
                        pool_id=normal_pool_id,
                        pool_lifecycle="fixture_variant_resident",
                    )
                    for framework, result in results.items():
                        record["results"]["normal"][framework].append(result)
            finally:
                await close_warm_pool(normal_pool, timeout_seconds=5.0)

            for repetition in range(1, args.repetitions + 1):
                fault_pool = await create_pool(fixture)
                fault_pool_id = (
                    f"{fixture['fixtureId']}:hard-failure:rep-{repetition:02d}"
                )
                lifecycle["rocketridePools"].append(
                    {
                        "poolId": fault_pool_id,
                        "fixtureId": fixture["fixtureId"],
                        "variant": "hard-failure",
                        "repetitionScope": f"rep-{repetition:02d}",
                        "warmupMs": round(float(fault_pool.warm_s or 0) * 1000.0, 3),
                        "retiredReason": "injected_worker_exit",
                    }
                )
                try:
                    directory = (
                        run_root
                        / fixture["fixtureId"]
                        / "hard-failure"
                        / f"rep-{repetition:02d}"
                    )
                    directory.mkdir(parents=True, exist_ok=True)
                    results = await run_cell(
                        fixture=fixture,
                        variant="hard-failure",
                        repetition=repetition,
                        directory=directory,
                        pool=fault_pool,
                        pool_id=fault_pool_id,
                        pool_lifecycle="request_prewarmed_then_retired",
                    )
                    for framework, result in results.items():
                        record["results"]["hard-failure"][framework].append(result)
                finally:
                    await close_warm_pool(fault_pool, timeout_seconds=5.0)
            records.append(record)
    finally:
        if engine_process is not None:
            v1.stop_process_tree(engine_process)

    lifecycle["engineColdStartMs"] = round(engine_cold_ms, 3)
    v1.write_json(run_root / "runtime-lifecycle.json", lifecycle)
    scorecard = aggregate_v2(
        run_root=run_root,
        records=records,
        engine_cold_ms=engine_cold_ms,
        app_verification=app_verification,
        definitions=definitions,
        lifecycle=lifecycle,
    )
    (run_root / "RESULTS.md").write_text(report_v2(scorecard), encoding="utf-8")
    v1.write_manifest(run_root)
    v1.write_json(
        v1.SUITE / "latest-run.json",
        {
            "runId": run_id,
            "path": run_root.relative_to(v1.REPO).as_posix(),
            "status": scorecard["status"],
            "profile": PROFILE,
            "orchestrationStatus": scorecard["status"],
            "protocolAdmissionStatus": "pending_post_run_audit",
            "promotionStatus": "pending_post_run_audit",
            "v1ProtocolFailurePreserved": True,
        },
    )
    print(json.dumps({"runId": run_id, "status": scorecard["status"]}), flush=True)
    return 0 if scorecard["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if args.run_id is None:
        args.run_id = dt.datetime.now(dt.timezone.utc).strftime(
            "node-suite-v2-%Y%m%dT%H%M%SZ"
        )
    try:
        return asyncio.run(run(args))
    except Exception as error:
        v1.write_harness_failure(args.run_id, error)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
