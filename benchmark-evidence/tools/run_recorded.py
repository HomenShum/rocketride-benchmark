#!/usr/bin/env python3
"""Run an unchanged benchmark command while preserving process and retry evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO_ROOT / "benchmark-evidence"
COMMAND_LOG = EVIDENCE_ROOT / "commands.log"
FAILURE_LEDGER = EVIDENCE_ROOT / "failures.jsonl"
ALLOWED_ENV = {
    "BENCH_DB_DIR",
    "BENCH_M",
    "BENCH_MS",
    "BENCH_PY",
    "ENGINE_DIR",
    "MAX_ATTEMPTS",
    "PYTHONIOENCODING",
    "REPS",
    "RESTART",
    "ROCKETRIDE_BENCH_PARAMS",
    "ROCKETRIDE_PORT",
    "ROCKETRIDE_URI",
}
RETRY_RE = re.compile(
    r"\.\.\.retry\s+(?P<benchmark>\S+)\s+(?P<run>\S+)\s+"
    r"\(attempt\s+(?P<attempt>\d+)(?:,\s+rc=(?P<rc>[^)]+)|\s+failed)\)"
)
FAIL_RE = re.compile(r"(?:^|\s)FAIL\s+(?P<benchmark>\S+)(?:\s+(?P<run>\S+))?")
ENGINE_RE = re.compile(r"engine (?:did not become healthy|down)", re.IGNORECASE)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def append_jsonl(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def append_command_log(line: str) -> None:
    with COMMAND_LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line.rstrip() + "\n")


def parse_env(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"invalid --env value: {value}")
        name, raw = value.split("=", 1)
        if name not in ALLOWED_ENV:
            raise ValueError(f"refusing to record unapproved environment variable: {name}")
        parsed[name] = raw
    return parsed


def display_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command) if os.name == "nt" else " ".join(command)


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--log", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        parser.error("a command is required after --")

    env_overrides = parse_env(args.env)
    environment = dict(os.environ)
    environment.update(env_overrides)
    cwd = (REPO_ROOT / args.cwd).resolve()
    log_path = (EVIDENCE_ROOT / args.log).resolve()
    receipt_path = (EVIDENCE_ROOT / args.receipt).resolve()
    for path in (log_path, receipt_path):
        if EVIDENCE_ROOT not in path.parents:
            raise ValueError(f"evidence path escapes benchmark-evidence: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    started_at = utc_now()
    started = time.monotonic()
    rendered = display_command(command)
    append_command_log(
        f"{started_at} START id={args.id} cwd={cwd.relative_to(REPO_ROOT)} command={rendered}"
    )

    detected_failures: list[dict] = []
    sha256 = hashlib.sha256()
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as error:
        finished_at = utc_now()
        duration_seconds = round(time.monotonic() - started, 3)
        message = f"{type(error).__name__}: {error}"
        log_path.write_text(message + "\n", encoding="utf-8")
        digest = hashlib.sha256((message + "\n").encode("utf-8")).hexdigest()
        failure_record = {
            "schemaVersion": "node.rocketride.failure/v1",
            "event": "process_spawn_failed",
            "failure": True,
            "at": finished_at,
            "commandId": args.id,
            "command": command,
            "cwd": str(cwd.relative_to(REPO_ROOT)).replace("\\", "/"),
            "message": message,
            "log": str(log_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        }
        append_jsonl(FAILURE_LEDGER, failure_record)
        receipt = {
            "schemaVersion": "node.rocketride.command-receipt/v1",
            "commandId": args.id,
            "command": command,
            "renderedCommand": rendered,
            "cwd": str(cwd.relative_to(REPO_ROOT)).replace("\\", "/"),
            "environment": env_overrides,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "durationSeconds": duration_seconds,
            "exitCode": 127,
            "passed": False,
            "detectedFailureSignals": 1,
            "log": str(log_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "logSha256": digest,
            "spawnError": message,
        }
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        append_command_log(
            f"{finished_at} END id={args.id} exit=127 duration_s={duration_seconds} "
            f"failure_signals=1 log_sha256={digest}"
        )
        print(message, file=sys.stderr)
        return 127
    assert process.stdout is not None
    with log_path.open("w", encoding="utf-8", newline="\n") as log_handle:
        for line in process.stdout:
            sys.stdout.write(line)
            log_handle.write(line)
            sha256.update(line.encode("utf-8", errors="replace"))

            retry = RETRY_RE.search(line)
            failure = FAIL_RE.search(line)
            if retry:
                record = {
                    "schemaVersion": "node.rocketride.failure/v1",
                    "event": "runner_attempt_failed",
                    "failure": True,
                    "at": utc_now(),
                    "commandId": args.id,
                    "benchmark": retry.group("benchmark"),
                    "run": retry.group("run"),
                    "attempt": int(retry.group("attempt")),
                    "exitCode": retry.group("rc") or "not_emitted",
                    "log": str(log_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                }
                detected_failures.append(record)
                append_jsonl(FAILURE_LEDGER, record)
            elif failure or ENGINE_RE.search(line):
                record = {
                    "schemaVersion": "node.rocketride.failure/v1",
                    "event": "runner_failure_signal",
                    "failure": True,
                    "at": utc_now(),
                    "commandId": args.id,
                    "benchmark": failure.group("benchmark") if failure else "engine",
                    "run": failure.group("run") if failure else None,
                    "message": line.strip(),
                    "log": str(log_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                }
                detected_failures.append(record)
                append_jsonl(FAILURE_LEDGER, record)

    exit_code = process.wait()
    finished_at = utc_now()
    duration_seconds = round(time.monotonic() - started, 3)
    if exit_code != 0:
        record = {
            "schemaVersion": "node.rocketride.failure/v1",
            "event": "process_failed",
            "failure": True,
            "at": finished_at,
            "commandId": args.id,
            "exitCode": exit_code,
            "command": command,
            "cwd": str(cwd.relative_to(REPO_ROOT)).replace("\\", "/"),
            "log": str(log_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        }
        detected_failures.append(record)
        append_jsonl(FAILURE_LEDGER, record)

    receipt = {
        "schemaVersion": "node.rocketride.command-receipt/v1",
        "commandId": args.id,
        "command": command,
        "renderedCommand": rendered,
        "cwd": str(cwd.relative_to(REPO_ROOT)).replace("\\", "/"),
        "environment": env_overrides,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "durationSeconds": duration_seconds,
        "exitCode": exit_code,
        "passed": exit_code == 0,
        "detectedFailureSignals": len(detected_failures),
        "log": str(log_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "logSha256": sha256.hexdigest(),
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    append_command_log(
        f"{finished_at} END id={args.id} exit={exit_code} duration_s={duration_seconds} "
        f"failure_signals={len(detected_failures)} log_sha256={sha256.hexdigest()}"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
