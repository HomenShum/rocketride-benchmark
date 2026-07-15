#!/usr/bin/env python3
"""Run the pre-registered Node fixture matrix on native, RocketRide, and LangChain."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request

import psutil


HERE = Path(__file__).resolve().parent
SUITE = HERE.parent
EVIDENCE = SUITE.parent.parent
REPO = EVIDENCE.parent
BENCH = REPO / "concurrent-work" / "harness" / "rocketride-bench"
ENGINE = BENCH / "engine" / ("engine.exe" if os.name == "nt" else "engine")
VENV_PY = BENCH / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
FIXTURES = SUITE / "fixtures"
RUNS = SUITE / "runs"
PORT = 5567
URI = f"ws://localhost:{PORT}"
MARKER = re.compile(r"NODEWORKFLOW\t(?P<status>OK|FAIL)\t(?P<name>[^\t]+)\tpid=(?P<pid>\d+)")

os.environ["ROCKETRIDE_URI"] = URI
os.environ["ROCKETRIDE_PORT"] = str(PORT)
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(HERE))

from harness import pipes  # noqa: E402
from harness.runner import Bench, WarmPool  # noqa: E402
from harness.tracesink import TraceSink  # noqa: E402
from async_utils import close_warm_pool, send_with_timeout  # noqa: E402
from protocol import canonical_json, digest, request_for, result_for  # noqa: E402


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def gzip_file(path: Path) -> Path:
    compressed = Path(str(path) + ".gz")
    with path.open("rb") as source, gzip.open(compressed, "wb", compresslevel=9) as target:
        shutil.copyfileobj(source, target)
    path.unlink()
    return compressed


def source_metrics(paths: list[Path]) -> dict:
    files = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        files.append(
            {
                "path": path.relative_to(SUITE).as_posix(),
                "bytes": path.stat().st_size,
                "physicalLines": len(text.splitlines()),
                "nonBlankLines": sum(1 for line in text.splitlines() if line.strip()),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "files": files,
        "physicalLines": sum(item["physicalLines"] for item in files),
        "nonBlankLines": sum(item["nonBlankLines"] for item in files),
        "bytes": sum(item["bytes"] for item in files),
    }


def authoring_evidence() -> dict:
    return {
        "interpretation": "Physical and non-blank lines are descriptive, not semantic complexity scores.",
        "sharedHarness": source_metrics([HERE / "protocol.py", HERE / "run_suite.py"]),
        "native": source_metrics([HERE / "native_executor.mjs"]),
        "rocketride": source_metrics([HERE / "rocketride-node" / "nodeworkflow" / "IInstance.py"]),
        "langchain": source_metrics([HERE / "langchain_executor.py"]),
    }


def require_app_verification(fixtures: list[dict]) -> dict:
    path = SUITE / "app-verification.json"
    if not path.is_file():
        raise RuntimeError(
            "application verifier receipt is missing; run run_app_verifiers.py first"
        )
    receipt = json.loads(path.read_text(encoding="utf-8"))
    verified_apps = {
        item.get("app")
        for item in receipt.get("apps", [])
        if item.get("passed") is True
    }
    required_apps = {fixture["app"] for fixture in fixtures}
    missing_apps = sorted(required_apps - verified_apps)
    if (
        receipt.get("status") != "passed"
        or receipt.get("protocolParity") is not True
        or missing_apps
    ):
        detail = f"; missing apps: {', '.join(missing_apps)}" if missing_apps else ""
        raise RuntimeError(f"application verifier receipt did not pass{detail}")
    return receipt


def environment_evidence() -> dict:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpuCount": os.cpu_count(),
        "memoryBytes": psutil.virtual_memory().total,
        "python": platform.python_version(),
        "node": process_version("node"),
        "rocketrideSdk": importlib.metadata.version("rocketride"),
        "langchainCore": importlib.metadata.version("langchain-core"),
        "engineVersion": engine_version(),
        "engineBytes": ENGINE.stat().st_size,
        "engineSha256": hashlib.sha256(ENGINE.read_bytes()).hexdigest(),
        "enginePort": PORT,
    }


def write_manifest(run_root: Path) -> None:
    files = []
    manifest_path = run_root / "manifest.json"
    for path in sorted(
        item
        for item in run_root.rglob("*")
        if item.is_file() and item != manifest_path
    ):
        files.append(
            {
                "path": path.relative_to(run_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    write_json(
        manifest_path,
        {"schemaVersion": "node.workflow-extension-manifest/v1", "files": files},
    )


def write_harness_failure(run_id: str, error: Exception) -> None:
    run_root = RUNS / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    traceback_text = traceback.format_exc()
    traceback_lines = (
        [] if traceback_text.strip() == "NoneType: None" else traceback_text.splitlines()
    )
    write_json(
        run_root / "harness-failure.json",
        {
            "schemaVersion": "node.workflow-harness-failure/v1",
            "runId": run_id,
            "failedAt": utc_now(),
            "exceptionType": type(error).__name__,
            "message": str(error),
            "traceback": traceback_lines,
            "publicationStatus": "independent_unsubmitted",
            "modelCostUsd": 0,
            "cloudCostUsd": 0,
        },
    )
    write_manifest(run_root)


def install_study_node() -> None:
    source = HERE / "rocketride-node" / "nodeworkflow"
    destination = ENGINE.parent / "nodes" / "nodeworkflow"
    shutil.copytree(source, destination, dirs_exist_ok=True)


def listener_pid(port: int) -> int | None:
    for connection in psutil.net_connections(kind="inet"):
        if connection.laddr and connection.laddr.port == port and connection.status == "LISTEN":
            return connection.pid
    return None


def healthy(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=2)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def start_engine(log_path: Path) -> tuple[subprocess.Popen, float]:
    if listener_pid(PORT):
        raise RuntimeError(f"refusing to reuse occupied extension port {PORT}")
    install_study_node()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("wb")
    started = time.perf_counter()
    process = subprocess.Popen(
        [str(ENGINE), "ai/eaas.py", "--host=127.0.0.1", f"--port={PORT}"],
        cwd=ENGINE.parent,
        stdout=log_handle,
        stderr=log_handle,
        env=dict(os.environ),
    )
    deadline = time.perf_counter() + 180
    while time.perf_counter() < deadline:
        if process.poll() is not None:
            log_handle.close()
            raise RuntimeError(f"extension engine exited {process.returncode}")
        if healthy(PORT) and listener_pid(PORT):
            log_handle.close()
            return process, (time.perf_counter() - started) * 1000.0
        time.sleep(1)
    stop_process_tree(process)
    log_handle.close()
    raise RuntimeError("extension engine did not become healthy")


def stop_process_tree(process: subprocess.Popen) -> None:
    try:
        parent = psutil.Process(process.pid)
    except psutil.Error:
        return
    children = parent.children(recursive=True)
    for child in children:
        try:
            child.terminate()
        except psutil.Error:
            pass
    try:
        parent.terminate()
    except psutil.Error:
        pass
    _, alive = psutil.wait_procs(children + [parent], timeout=10)
    for item in alive:
        try:
            item.kill()
        except psutil.Error:
            pass


def process_tree_metrics(pid: int) -> tuple[int, float]:
    try:
        processes = [psutil.Process(pid)] + psutil.Process(pid).children(recursive=True)
    except psutil.Error:
        return 0, 0.0
    rss = 0
    cpu_seconds = 0.0
    for process in processes:
        try:
            rss += process.memory_info().rss
            cpu = process.cpu_times()
            cpu_seconds += cpu.user + cpu.system
        except psutil.Error:
            pass
    return rss, cpu_seconds * 1000.0


def workflow_pipe() -> dict:
    return pipes.make_pipe(
        [
            pipes.webhook_node(),
            {
                "id": "candidate_1",
                "provider": "nodeworkflow",
                "config": {},
                "input": [{"from": "webhook_1", "lane": "tags"}],
            },
        ],
        source="webhook_1",
        project_id="00000000-0000-4000-8000-0000000000bb",
    )


async def validate_pipe(pipe: dict, run_root: Path) -> None:
    path = run_root / "nodeworkflow.pipe"
    pipes.write_pipe(str(path), pipe)
    async with Bench() as bench:
        validation = await bench.validate_file(str(path))
    if not validation.get("ok"):
        raise RuntimeError(f"Node workflow pipe failed validation: {validation.get('errors')}")


async def run_rocketride(
    fixture: dict,
    failure_unit: str | None,
    trace_path: Path,
) -> dict:
    units = fixture["units"]
    pipe = workflow_pipe()
    engine_pid = listener_pid(PORT)
    rss_before, cpu_before = process_tree_metrics(engine_pid or 0)
    completed: list[str] = []
    failed: list[str] = []
    total_started = time.perf_counter()
    send_failures: set[str] = set()
    warmup_ms = 0.0
    execution_ms = 0.0
    async with TraceSink(uri=URI) as sink:
        pool = WarmPool(
            pipe,
            len(units),
            threads=1,
            ttl=120,
            uri=URI,
            trace_level="full",
        )
        await pool.__aenter__()
        try:
            warmup_ms = float(pool.warm_s or 0) * 1000.0
            sink.clear()
            execution_started = time.perf_counter()
            send_timeout_s = max(1.0, float(fixture["deadlineMs"]) / 1000.0)

            async def send(index: int, unit: dict) -> None:
                name = f"{unit['id']}.txt"
                if unit["id"] == failure_unit:
                    name = "crash__" + name
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
                    send_failures.add(str(unit["id"]))

            await asyncio.gather(*(send(index, unit) for index, unit in enumerate(units)))
            await sink.drain(1.0)
            events = sink.snapshot()
            sink.write_jsonl(str(trace_path), events)
            execution_ms = (time.perf_counter() - execution_started) * 1000.0
            gzip_file(trace_path)
        finally:
            await close_warm_pool(pool, timeout_seconds=5.0)

    for event in events:
        for text in nested_strings(event):
            for marker in MARKER.finditer(text):
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
    rss_after, cpu_after = process_tree_metrics(engine_pid or 0)
    total_ms = (time.perf_counter() - total_started) * 1000.0
    return {
        "completed": sorted(completed),
        "failed": sorted(set(failed)),
        "totalMs": total_ms,
        "executionMs": execution_ms,
        "coldStartMs": 0,
        "warmupMs": warmup_ms,
        "peakRssBytes": max(rss_before, rss_after),
        "cpuTimeMs": max(0.0, cpu_after - cpu_before),
        "serverHealthyAfter": healthy(PORT),
    }


def nested_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from nested_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from nested_strings(item)


def subprocess_executor(
    command: list[str],
    payload: dict,
    directory: Path,
    framework: str,
) -> dict:
    input_path = directory / f"{framework}-input.json"
    output_path = directory / f"{framework}-execution.json"
    write_json(input_path, payload)
    started = time.perf_counter()
    process = subprocess.run(
        [*command, str(input_path), str(output_path)],
        cwd=HERE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    wall_ms = (time.perf_counter() - started) * 1000.0
    (directory / f"{framework}.stdout.log").write_text(process.stdout, encoding="utf-8")
    (directory / f"{framework}.stderr.log").write_text(process.stderr, encoding="utf-8")
    if process.returncode == 0 and output_path.exists():
        execution = json.loads(output_path.read_text(encoding="utf-8"))
        execution["coldStartMs"] = max(0.0, wall_ms - float(execution.get("totalMs", 0)))
        execution["totalMs"] = wall_ms
        return execution
    expected = [unit["id"] for unit in payload["units"]]
    return {
        "completed": [],
        "failed": expected,
        "totalMs": wall_ms,
        "executionMs": wall_ms,
        "coldStartMs": 0,
        "warmupMs": 0,
        "peakRssBytes": 0,
        "cpuTimeMs": 0,
        "processExitCode": process.returncode,
    }


def percentile(values: list[float], p: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p / 100
    low = int(position)
    high = min(len(ordered) - 1, low + 1)
    weight = position - low
    return round(ordered[low] * (1 - weight) + ordered[high] * weight, 3)


def metric(values: list[float]) -> dict:
    return {
        "count": len(values),
        "median": round(statistics.median(values), 3) if values else None,
        "p95": percentile(values, 95),
        "min": round(min(values), 3) if values else None,
        "max": round(max(values), 3) if values else None,
    }


def aggregate(run_root: Path, fixture_records: list[dict], engine_cold_ms: float) -> dict:
    frameworks = ("native", "rocketride", "langchain")
    rows = []
    gate_issues: list[str] = []
    for fixture in fixture_records:
        expected = len(fixture["units"])
        for variant in ("normal", "hard-failure"):
            for framework in frameworks:
                results = fixture["results"][variant][framework]
                totals = [float(result["metrics"]["totalMs"]) for result in results]
                executions = [float(result["metrics"]["executionMs"]) for result in results]
                warmups = [float(result["metrics"]["warmupMs"]) for result in results]
                completed = [int(result["metrics"]["completedUnits"]) for result in results]
                failed = [int(result["metrics"]["failedUnits"]) for result in results]
                healthy_after = [result["metrics"].get("runtimeHealthyAfter") for result in results]
                rows.append(
                    {
                        "fixtureId": fixture["fixtureId"],
                        "app": fixture["app"],
                        "variant": variant,
                        "framework": framework,
                        "repetitions": len(results),
                        "totalMs": metric(totals),
                        "executionMs": metric(executions),
                        "warmupMs": metric(warmups),
                        "completedUnits": metric([float(value) for value in completed]),
                        "failedUnits": metric([float(value) for value in failed]),
                        "runtimeHealthyAfter": {
                            "reported": sum(isinstance(value, bool) for value in healthy_after),
                            "healthy": sum(value is True for value in healthy_after),
                        },
                        "candidateDigest": results[0]["outputDigest"],
                        "modelCalls": 0,
                        "modelCostUsd": 0,
                        "cloudCostUsd": 0,
                    }
                )
                if variant == "normal":
                    if any(value != expected for value in completed) or any(failed):
                        gate_issues.append(f"{fixture['fixtureId']} {framework}: normal run incomplete")
                elif framework in ("native", "rocketride"):
                    if any(value != expected - 1 for value in completed):
                        gate_issues.append(
                            f"{fixture['fixtureId']} {framework}: unaffected hard-failure units did not complete"
                        )
                    if framework == "rocketride" and any(value is not True for value in healthy_after):
                        gate_issues.append(
                            f"{fixture['fixtureId']} rocketride: runtime was not healthy after hard failure"
                        )
            normal_digests = {
                result["outputDigest"]
                for framework in frameworks
                for result in fixture["results"]["normal"][framework]
            }
            if len(normal_digests) != 1:
                gate_issues.append(f"{fixture['fixtureId']}: candidate digest parity failed")

    app_verification_path = SUITE / "app-verification.json"
    app_verification = (
        json.loads(app_verification_path.read_text(encoding="utf-8"))
        if app_verification_path.exists()
        else {"status": "not_run", "apps": []}
    )
    verified_apps = {
        item.get("app") for item in app_verification.get("apps", []) if item.get("passed") is True
    }
    missing_apps = sorted({fixture["app"] for fixture in fixture_records} - verified_apps)
    if missing_apps:
        gate_issues.append("application verifier receipts missing: " + ", ".join(missing_apps))

    scorecard = {
        "schemaVersion": "node.workflow-extension-scorecard/v1",
        "generatedAt": utc_now(),
        "status": "passed" if not gate_issues else "incomplete",
        "officialStatus": "separate_application_study_unsubmitted",
        "engineColdStartMs": round(engine_cold_ms, 3),
        "environment": environment_evidence(),
        "conditions": {
            "deterministic": True,
            "paidModelCalls": 0,
            "cloudRuns": 0,
            "sameCandidateDigestRequired": True,
            "finalWritesAttempted": 0,
        },
        "rows": rows,
        "authoring": authoring_evidence(),
        "appVerification": app_verification,
        "gateIssues": gate_issues,
    }
    write_json(run_root / "scorecard.json", scorecard)
    return scorecard


def report(scorecard: dict) -> str:
    lines = [
        "# Node Application Runtime Study",
        "",
        f"Gate status: **{scorecard['status']}**. External status: **{scorecard['officialStatus']}**.",
        "",
        "All scored work is deterministic and local. Model calls, model cost, and cloud cost are zero.",
        "Candidates are never committed by these executors; app-owned validation, CAS, proposals, and review remain authoritative.",
        "",
        "| App | Variant | Framework | Completed units median | Failed units median | Total p50 ms | Total p95 ms | Warm-up p50 ms |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in scorecard["rows"]:
        lines.append(
            "| {app} | {variant} | {framework} | {completed} | {failed} | {p50} | {p95} | {warmup} |".format(
                app=row["app"],
                variant=row["variant"],
                framework=row["framework"],
                completed=row["completedUnits"]["median"],
                failed=row["failedUnits"]["median"],
                p50=row["totalMs"]["median"],
                p95=row["totalMs"]["p95"],
                warmup=row["warmupMs"]["median"],
            )
        )
    lines.extend(
        [
            "",
            "## Authoring Surface",
            "",
            "| Surface | Physical lines | Non-blank lines | Bytes |",
            "|---|---:|---:|---:|",
        ]
    )
    for surface in ("sharedHarness", "native", "rocketride", "langchain"):
        metrics = scorecard["authoring"][surface]
        lines.append(
            f"| {surface} | {metrics['physicalLines']} | {metrics['nonBlankLines']} | {metrics['bytes']} |"
        )
    lines.append("")
    lines.append(scorecard["authoring"]["interpretation"])
    lines.extend(
        [
            "",
            "## Interpretation Boundaries",
            "",
            "- Native is the additive Node worker-thread control in this study, not a claim about every production deployment topology.",
            "- RocketRide is the pinned local engine with one resident pipe process per work unit.",
            "- LangChain is real langchain-core RunnableLambda.abatch in one Python interpreter.",
            "- Hard-failure rows measure unaffected work completion; they are expected to reject the candidate envelope.",
            "- Product correctness credit belongs to the application verifier receipts, not the executor.",
        ]
    )
    if scorecard["gateIssues"]:
        lines.extend(["", "## Gate Issues", ""])
        lines.extend(f"- {issue}" for issue in scorecard["gateIssues"])
    return "\n".join(lines) + "\n"


async def run(args: argparse.Namespace) -> int:
    run_id = args.run_id or dt.datetime.now(dt.timezone.utc).strftime("node-suite-%Y%m%dT%H%M%SZ")
    run_root = RUNS / run_id
    fixtures = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(FIXTURES.glob("*.json"))]
    require_app_verification(fixtures)
    run_root.mkdir(parents=True, exist_ok=False)
    engine_process = None
    engine_cold_ms = 0.0
    records = []
    try:
        engine_process, engine_cold_ms = start_engine(run_root / "engine.log")
        await validate_pipe(workflow_pipe(), run_root)
        for fixture in fixtures:
            record = {
                "fixtureId": fixture["fixtureId"],
                "app": fixture["app"],
                "units": fixture["units"],
                "results": {
                    "normal": {"native": [], "rocketride": [], "langchain": []},
                    "hard-failure": {"native": [], "rocketride": [], "langchain": []},
                },
            }
            for variant in ("normal", "hard-failure"):
                failure_unit = fixture["units"][0]["id"] if variant == "hard-failure" else None
                for repetition in range(1, args.repetitions + 1):
                    directory = run_root / fixture["fixtureId"] / variant / f"rep-{repetition:02d}"
                    directory.mkdir(parents=True, exist_ok=True)
                    request = request_for(fixture, variant, repetition)
                    write_json(directory / "request.json", request)
                    payload = {
                        "units": fixture["units"],
                        "concurrency": fixture["concurrency"],
                        "delayMs": fixture["delayMs"],
                        "failureUnit": failure_unit,
                    }
                    native_execution = subprocess_executor(
                        ["node", str(HERE / "native_executor.mjs")], payload, directory, "native"
                    )
                    langchain_execution = subprocess_executor(
                        [str(VENV_PY), str(HERE / "langchain_executor.py")],
                        payload,
                        directory,
                        "langchain",
                    )
                    rocketride_execution = await run_rocketride(
                        fixture,
                        failure_unit,
                        directory / "rocketride-trace.jsonl",
                    )
                    executions = {
                        "native": (native_execution, "node-worker-threads", native_execution.get("runtimeVersion", process_version("node"))),
                        "rocketride": (rocketride_execution, "rocketride-engine", engine_version()),
                        "langchain": (
                            langchain_execution,
                            "python-langchain",
                            "python={python};langchain-core={langchain}".format(
                                python=langchain_execution.get("runtimeVersion", "unknown"),
                                langchain=langchain_execution.get("langchainCoreVersion", "0.3.86"),
                            ),
                        ),
                    }
                    for framework, (execution, runtime, runtime_version) in executions.items():
                        result = result_for(
                            fixture=fixture,
                            request=request,
                            framework=framework,
                            repetition=repetition,
                            execution=execution,
                            runtime=runtime,
                            runtime_version=str(runtime_version),
                        )
                        write_json(directory / f"{framework}-result.json", result)
                        record["results"][variant][framework].append(result)
                    print(
                        f"{fixture['fixtureId']} {variant} rep-{repetition:02d}: "
                        f"native={len(native_execution.get('completed', []))} "
                        f"rr={len(rocketride_execution.get('completed', []))} "
                        f"lc={len(langchain_execution.get('completed', []))}",
                        flush=True,
                    )
            records.append(record)
    finally:
        if engine_process is not None:
            stop_process_tree(engine_process)

    scorecard = aggregate(run_root, records, engine_cold_ms)
    (run_root / "RESULTS.md").write_text(report(scorecard), encoding="utf-8")
    write_manifest(run_root)
    write_json(
        SUITE / "latest-run.json",
        {"runId": run_id, "path": run_root.relative_to(REPO).as_posix(), "status": scorecard["status"]},
    )
    print(json.dumps({"runId": run_id, "status": scorecard["status"]}), flush=True)
    return 0 if scorecard["status"] == "passed" or args.allow_incomplete else 1


def process_version(command: str) -> str:
    return subprocess.check_output([command, "--version"], text=True, encoding="utf-8").strip()


def engine_version() -> str:
    return subprocess.check_output([str(ENGINE), "--version"], text=True, encoding="utf-8").strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--run-id")
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    if args.repetitions < 1 or args.repetitions > 10:
        raise SystemExit("repetitions must be between 1 and 10")
    try:
        return asyncio.run(run(args))
    except Exception as error:
        write_harness_failure(args.run_id, error)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
