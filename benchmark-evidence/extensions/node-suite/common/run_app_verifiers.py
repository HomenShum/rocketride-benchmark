#!/usr/bin/env python3
"""Run each application's candidate-only verifier and emit hashed receipts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


HERE = Path(__file__).resolve().parent
SUITE = HERE.parent
EVIDENCE = SUITE.parent.parent
REPO = EVIDENCE.parent
LOGS = SUITE / "app-verification-logs"
APPS = {
    "noderoom": {
        "directory": "NodeRoom",
        "baseCommit": "ca25e347dc467bc37f06918e1a18656f7336ee28",
        "protocol": "src/nodeagent/integrations/workflowExecutionPort.ts",
        "adapters": ["src/nodeagent/integrations/roomWorkflowCandidate.ts"],
        "domainTools": [
            "src/nodeagent/skills/spreadsheet/algorithmArtifacts.ts",
            "src/nodeagent/skills/spreadsheet/semanticRebase.ts",
        ],
        "tests": ["tests/nodeWorkflowExecutionPort.test.ts"],
        "fixtures": [
            {
                "app": "tests/fixtures/rocketride-noderoom-independent-writes.json",
                "study": "noderoom-independent-writes.json",
            },
            {
                "app": "tests/fixtures/rocketride-noderoom-conflict-proposal.json",
                "study": "noderoom-conflict-proposal.json",
            },
        ],
        "command": ["npm", "test", "--", "--run", "tests/nodeWorkflowExecutionPort.test.ts"],
    },
    "nodebenchai": {
        "directory": "NodeBenchAI",
        "baseCommit": "6ed0a58eeda993ff2a937ea4bacc2856756dd521",
        "protocol": "src/shared/workflowExecutionPort.ts",
        "adapters": [
            "src/shared/nodeBenchWorkflowCandidate.ts",
            "src/shared/rocketRideEvidenceBundle.ts",
            "scripts/verify-rocketride-evidence-bundle.ts",
        ],
        "domainTools": ["src/shared/agentOutputContract.ts"],
        "tests": [
            "src/shared/nodeBenchWorkflowCandidate.test.ts",
            "src/shared/rocketRideEvidenceBundle.test.ts",
        ],
        "fixtures": [
            {
                "app": "src/shared/fixtures/rocketride-nodebenchai-frozen-sources.json",
                "study": "nodebenchai-frozen-sources.json",
            }
        ],
        "command": [
            "npx",
            "vitest",
            "run",
            "src/shared/nodeBenchWorkflowCandidate.test.ts",
            "src/shared/rocketRideEvidenceBundle.test.ts",
        ],
    },
    "nodeslide": {
        "directory": "NodeSlide",
        "baseCommit": "dd67e4c642c40e6bb414af617a67a31dbed507c5",
        "protocol": "shared/workflowExecutionPort.ts",
        "adapters": ["convex/lib/nodeslideWorkflowCandidate.ts"],
        "domainTools": [
            "shared/nodeslide.ts",
            "convex/lib/nodeslidePatches.ts",
        ],
        "tests": ["convex/lib/nodeslideWorkflowCandidate.test.ts"],
        "fixtures": [
            {
                "app": "convex/lib/fixtures/rocketride-nodeslide-independent-elements.json",
                "study": "nodeslide-independent-elements.json",
            }
        ],
        "command": ["npm", "test", "--", "--run", "convex/lib/nodeslideWorkflowCandidate.test.ts"],
    },
    "nodevideo": {
        "directory": "NodeVideo",
        "baseCommit": "bb79bc385de93c90cee89b160fc801d18372d89e",
        "protocol": "src/lib/workflowExecutionPort.ts",
        "adapters": ["src/lib/nodeVideoWorkflowCandidate.ts"],
        "domainTools": [
            "src/lib/contracts.ts",
            "src/lib/runtime.ts",
        ],
        "tests": ["src/lib/nodeVideoWorkflowCandidate.test.ts"],
        "fixtures": [
            {
                "app": "src/lib/fixtures/rocketride-nodevideo-resume-shots.json",
                "study": "nodevideo-resume-shots.json",
            }
        ],
        "command": ["npm", "test", "--", "--run", "src/lib/nodeVideoWorkflowCandidate.test.ts"],
    },
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    encoded = json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def source_metrics(repo: Path, paths: list[str]) -> dict:
    files = []
    for relative in paths:
        path = repo / relative
        if not path.is_file():
            files.append({"path": relative, "missing": True})
            continue
        text = path.read_text(encoding="utf-8")
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "physicalLines": len(text.splitlines()),
                "nonBlankLines": sum(1 for line in text.splitlines() if line.strip()),
                "sha256": sha256(path),
            }
        )
    return {
        "files": files,
        "physicalLines": sum(int(item.get("physicalLines", 0)) for item in files),
        "nonBlankLines": sum(int(item.get("nonBlankLines", 0)) for item in files),
        "bytes": sum(int(item.get("bytes", 0)) for item in files),
    }


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8", errors="replace"
    ).strip()


def git_succeeds(repo: Path, *args: str) -> bool:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def resolve_command(command: list[str]) -> list[str]:
    if not command:
        raise ValueError("verifier command cannot be empty")
    executable = shutil.which(command[0])
    if executable is None:
        raise FileNotFoundError(
            f"verifier executable is not available on PATH: {command[0]}"
        )
    return [executable, *command[1:]]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apps-root", type=Path, required=True)
    parser.add_argument("--evidence-bundle", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=SUITE / "app-verification.json",
    )
    parser.add_argument("--logs-dir", type=Path, default=LOGS)
    args = parser.parse_args()
    root = args.apps_root.resolve()
    evidence_bundle = args.evidence_bundle.resolve()
    output = args.output.resolve()
    logs_dir = args.logs_dir.resolve()
    if not evidence_bundle.is_file():
        raise SystemExit(f"missing evidence bundle: {evidence_bundle}")
    output.parent.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    receipts = []
    for app, config in APPS.items():
        repo = root / config["directory"]
        if not repo.is_dir():
            raise SystemExit(f"missing app repository: {repo}")
        started_at = utc_now()
        commands = [config["command"]]
        if app == "nodebenchai":
            commands.append(
                [
                    "npx",
                    "tsx",
                    "scripts/verify-rocketride-evidence-bundle.ts",
                    str(evidence_bundle),
                ]
            )
        command_results = []
        resolved_commands = []
        log_parts = []
        for command in commands:
            resolved_command = resolve_command(command)
            resolved_commands.append(resolved_command)
            process = subprocess.run(
                resolved_command,
                cwd=repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20 * 60,
            )
            command_results.append(process.returncode)
            log_parts.extend(
                [
                    "$ " + subprocess.list2cmdline(resolved_command),
                    process.stdout,
                    process.stderr,
                ]
            )
        finished_at = utc_now()
        log = logs_dir / f"{app}.log"
        log.write_text("\n".join(log_parts), encoding="utf-8")
        status = git(repo, "status", "--porcelain=v1")
        clean = status == ""
        base_is_ancestor = git_succeeds(
            repo, "merge-base", "--is-ancestor", config["baseCommit"], "HEAD"
        )
        test_passed = all(exit_code == 0 for exit_code in command_results)
        protocol_path = repo / config["protocol"]
        protocol_sha256 = sha256(protocol_path) if protocol_path.is_file() else None
        fixture_receipts = []
        for pair in config["fixtures"]:
            fixture_sha256 = canonical_json_sha256(repo / pair["app"])
            study_fixture_sha256 = canonical_json_sha256(SUITE / "fixtures" / pair["study"])
            fixture_receipts.append(
                {
                    "appFixture": pair["app"],
                    "studyFixture": pair["study"],
                    "fixtureSha256": fixture_sha256,
                    "studyFixtureSha256": study_fixture_sha256,
                    "parity": fixture_sha256 is not None
                    and fixture_sha256 == study_fixture_sha256,
                }
            )
        fixture_parity = all(item["parity"] for item in fixture_receipts)
        authoring = {
            "sharedProtocol": source_metrics(repo, [config["protocol"]]),
            "applicationAdapter": source_metrics(repo, config["adapters"]),
            "domainTools": source_metrics(repo, config["domainTools"]),
            "verification": source_metrics(
                repo, [*config["tests"], *(pair["app"] for pair in config["fixtures"])]
            ),
            "interpretation": "Physical and non-blank lines are descriptive, not semantic complexity scores.",
        }
        authoring_complete = all(
            not item.get("missing", False)
            for group in (
                "sharedProtocol",
                "applicationAdapter",
                "domainTools",
                "verification",
            )
            for item in authoring[group]["files"]
        )
        receipt = {
            "schemaVersion": "node.workflow-app-verifier/v1",
            "app": app,
            "baseCommit": config["baseCommit"],
            "adapterCommit": git(repo, "rev-parse", "HEAD"),
            "branch": git(repo, "branch", "--show-current"),
            "clean": clean,
            "baseCommitIsAncestor": base_is_ancestor,
            "commands": commands,
            "resolvedCommands": resolved_commands,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "exitCodes": command_results,
            "testPassed": test_passed,
            "protocol": config["protocol"],
            "protocolSha256": protocol_sha256,
            "fixtures": fixture_receipts,
            "fixtureParity": fixture_parity,
            "authoring": authoring,
            "authoringComplete": authoring_complete,
            "passed": (
                test_passed
                and clean
                and base_is_ancestor
                and protocol_sha256 is not None
                and fixture_parity
                and authoring_complete
            ),
            "log": log.relative_to(SUITE).as_posix(),
            "logSha256": sha256(log),
        }
        receipts.append(receipt)
    protocol_hashes = {item["protocolSha256"] for item in receipts}
    protocol_parity = len(protocol_hashes) == 1 and None not in protocol_hashes
    if not protocol_parity:
        for item in receipts:
            item["passed"] = False
    for item in receipts:
        print(f"{item['app']}: {'PASS' if item['passed'] else 'FAIL'}", flush=True)
    value = {
        "schemaVersion": "node.workflow-app-verification/v1",
        "generatedAt": utc_now(),
        "evidenceBundle": {
            "path": evidence_bundle.relative_to(REPO).as_posix(),
            "bytes": evidence_bundle.stat().st_size,
            "sha256": sha256(evidence_bundle),
        },
        "protocolParity": protocol_parity,
        "protocolSha256": next(iter(protocol_hashes)) if protocol_parity else None,
        "status": "passed" if all(item["passed"] for item in receipts) else "failed",
        "apps": receipts,
    }
    output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return 0 if value["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
