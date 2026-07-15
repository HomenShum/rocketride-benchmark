from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from async_utils import close_warm_pool, send_with_timeout
from audit_run import manifest_issues, result_issues, update_latest_pointer
from protocol import deadline_overrun_count, digest, request_for, result_for
from run_app_verifiers import resolve_command


FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "noderoom-independent-writes.json"
ROCKETRIDE_NODE = Path(__file__).resolve().parent / "rocketride-node" / "nodeworkflow"


class ProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_trace_and_run_identity_are_unique_across_variants(self) -> None:
        normal = request_for(self.fixture, "normal", 1)
        failed = request_for(self.fixture, "hard-failure", 1)

        self.assertNotEqual(normal["traceId"], failed["traceId"])
        self.assertNotEqual(normal["idempotencyKey"], failed["idempotencyKey"])

        execution = {
            "completed": [unit["id"] for unit in self.fixture["units"]],
            "failed": [],
            "totalMs": 10,
            "executionMs": 8,
            "coldStartMs": 1,
            "warmupMs": 1,
            "serverHealthyAfter": True,
        }
        normal_result = result_for(
            fixture=self.fixture,
            request=normal,
            framework="native",
            repetition=1,
            execution=execution,
            runtime="node-worker-threads",
            runtime_version="test",
        )
        failed_result = result_for(
            fixture=self.fixture,
            request=failed,
            framework="native",
            repetition=1,
            execution=execution,
            runtime="node-worker-threads",
            runtime_version="test",
        )

        self.assertEqual(normal_result["traceId"], normal["traceId"])
        self.assertIs(normal_result["metrics"]["runtimeHealthyAfter"], True)
        self.assertNotEqual(normal_result["runId"], failed_result["runId"])
        self.assertEqual(normal_result["outputDigest"], digest(self.fixture["candidate"]))

    def test_verifier_resolves_platform_command_shims(self) -> None:
        with patch(
            "run_app_verifiers.shutil.which",
            return_value=r"C:\\Program Files\\nodejs\\npm.CMD",
        ):
            resolved = resolve_command(["npm", "test", "--", "--run"])

        self.assertEqual(resolved[0], r"C:\\Program Files\\nodejs\\npm.CMD")
        self.assertEqual(resolved[1:], ["test", "--", "--run"])

    def test_verifier_fails_closed_when_executable_is_missing(self) -> None:
        with patch("run_app_verifiers.shutil.which", return_value=None):
            with self.assertRaisesRegex(FileNotFoundError, "missing-tool"):
                resolve_command(["missing-tool", "verify"])

    def test_rocketride_node_has_discovery_metadata(self) -> None:
        services = json.loads((ROCKETRIDE_NODE / "services.json").read_text(encoding="utf-8"))

        self.assertEqual(services["protocol"], "nodeworkflow://")
        self.assertEqual(services["path"], "nodes.nodeworkflow")
        self.assertEqual(services["lanes"], {"tags": ["tags"]})
        self.assertTrue((ROCKETRIDE_NODE / "IGlobal.py").is_file())
        self.assertTrue((ROCKETRIDE_NODE / "IInstance.py").is_file())
        self.assertTrue((ROCKETRIDE_NODE / "__init__.py").is_file())

    def test_hard_failure_transport_and_cleanup_are_bounded(self) -> None:
        class HangingClient:
            def __init__(self) -> None:
                self.detached = False

            async def send(self, *_args, **_kwargs) -> None:
                await asyncio.Event().wait()

            async def terminate(self, _token: str) -> None:
                await asyncio.Event().wait()

            async def detach(self) -> None:
                self.detached = True

        client = HangingClient()
        with self.assertRaises(TimeoutError):
            asyncio.run(
                send_with_timeout(
                    client,
                    "token",
                    "payload",
                    objinfo={"name": "crash.txt"},
                    mimetype="text/plain",
                    timeout_seconds=0.01,
                )
            )

        pool = type("Pool", (), {"clients": [client], "tokens": ["token"]})()
        asyncio.run(close_warm_pool(pool, timeout_seconds=0.01))
        self.assertTrue(client.detached)

    def test_post_run_audit_rejects_deadline_overrun(self) -> None:
        request = {
            "traceId": "trace-1",
            "inputDigest": "sha256:" + "a" * 64,
            "idempotencyKey": "key-1",
            "deadlineMs": 10_000,
        }
        result = {
            "schemaVersion": "node.workflow-execution/v1",
            "traceId": request["traceId"],
            "inputDigest": request["inputDigest"],
            "idempotencyKey": request["idempotencyKey"],
            "framework": "rocketride",
            "events": [{"sequence": 1, "atMs": 0, "kind": "run.started"}],
            "metrics": {
                "totalMs": 10_001,
                "duplicateUnits": 0,
                "leakedUnits": 0,
            },
            "provenance": {"deterministic": True, "location": "local"},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text(json.dumps(result), encoding="utf-8")
            issues = result_issues(path, request, "fixture/rocketride-result.json")

        self.assertEqual([item["code"] for item in issues], ["deadline_exceeded"])
        self.assertEqual(issues[0]["path"], "fixture/rocketride-result.json")

    def test_runner_gate_counts_deadline_overruns(self) -> None:
        results = [
            {"metrics": {"totalMs": 9_999.999}},
            {"metrics": {"totalMs": 10_000}},
            {"metrics": {"totalMs": 10_000.001}},
        ]

        self.assertEqual(deadline_overrun_count(results, 10_000), 1)

    def test_manifest_validation_detects_unmanifested_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifact.txt").write_text("evidence", encoding="utf-8")
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "node.workflow-extension-manifest/v1",
                        "files": [],
                    }
                ),
                encoding="utf-8",
            )
            issues = manifest_issues(root)

        self.assertEqual(issues, ["unmanifested files: artifact.txt"])

    def test_audit_updates_latest_pointer_with_promotion_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            suite = repo / "benchmark-evidence" / "extensions" / "node-suite"
            run_root = suite / "runs" / "run-1"
            run_root.mkdir(parents=True)
            latest = suite / "latest-run.json"
            latest.write_text(
                json.dumps({"runId": "run-1", "status": "passed"}),
                encoding="utf-8",
            )
            audit = {
                "orchestrationGateStatus": "passed",
                "protocolAdmissionStatus": "failed",
                "promotionStatus": "blocked",
            }
            with patch("audit_run.SUITE", suite), patch("audit_run.REPO", repo):
                update_latest_pointer(run_root, audit)

            pointer = json.loads(latest.read_text(encoding="utf-8"))

        self.assertEqual(pointer["status"], "passed")
        self.assertEqual(pointer["protocolAdmissionStatus"], "failed")
        self.assertEqual(pointer["promotionStatus"], "blocked")
        self.assertEqual(
            pointer["auditPath"],
            "benchmark-evidence/extensions/node-suite/runs/run-1/audit.json",
        )


if __name__ == "__main__":
    unittest.main()
