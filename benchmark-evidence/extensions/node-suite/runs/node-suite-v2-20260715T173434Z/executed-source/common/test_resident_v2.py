from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from audit_run_v2 import result_issues_v2
from protocol import digest
from resolved_definition import (
    FROZEN_PRODUCTION_COMMITS,
    compile_definitions,
    request_for_v2,
)
import run_suite as v1
from run_suite_v2 import decorate_result


FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def verification_receipt(fixture_name: str) -> dict:
    app = "noderoom"
    return {
        "status": "passed",
        "protocolParity": True,
        "apps": [
            {
                "app": app,
                "passed": True,
                "clean": True,
                "adapterCommit": FROZEN_PRODUCTION_COMMITS[app],
                "protocol": "src/nodeagent/integrations/workflowExecutionPort.ts",
                "protocolSha256": "1" * 64,
                "fixtures": [
                    {
                        "studyFixture": fixture_name,
                        "studyFixtureSha256": "2" * 64,
                        "parity": True,
                    }
                ],
                "authoring": {
                    "applicationAdapter": {
                        "files": [{"path": "adapter.ts", "sha256": "3" * 64}]
                    },
                    "domainTools": {
                        "files": [{"path": "domain.ts", "sha256": "4" * 64}]
                    },
                    "verification": {
                        "files": [{"path": "adapter.test.ts", "sha256": "5" * 64}]
                    },
                },
            }
        ],
    }


class ResidentDefinitionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = FIXTURES / "noderoom-independent-writes.json"
        self.source_fixture = json.loads(self.path.read_text(encoding="utf-8"))
        self.fixtures, self.bundle = compile_definitions(
            [(self.path, self.source_fixture)], verification_receipt(self.path.name)
        )
        self.fixture = self.fixtures[0]
        self.definition_item = self.bundle["definitions"][0]

    def test_compiler_binds_production_sources_and_is_stable(self) -> None:
        definition = self.definition_item["definition"]
        self.assertEqual(self.fixture["fixtureId"], "noderoom-independent-writes-v2")
        self.assertEqual(
            definition["application"]["productionCommit"],
            FROZEN_PRODUCTION_COMMITS["noderoom"],
        )
        self.assertEqual(
            self.definition_item["definitionDigest"], digest(definition)
        )
        fixtures_again, bundle_again = compile_definitions(
            [(self.path, self.source_fixture)], verification_receipt(self.path.name)
        )
        self.assertEqual(bundle_again, self.bundle)
        self.assertEqual(fixtures_again, self.fixtures)

    def test_request_identity_includes_definition_and_variant(self) -> None:
        normal = request_for_v2(self.fixture, "normal", 1)
        failed = request_for_v2(self.fixture, "hard-failure", 1)
        self.assertEqual(normal["definitionDigest"], self.fixture["definitionDigest"])
        self.assertEqual(normal["unitTimeoutMs"], 2_000)
        self.assertNotEqual(normal["inputDigest"], failed["inputDigest"])
        self.assertNotEqual(normal["traceId"], failed["traceId"])

    def test_auditor_accepts_and_rejects_definition_binding(self) -> None:
        request = request_for_v2(self.fixture, "normal", 1)
        execution = {
            "completed": [unit["id"] for unit in self.fixture["units"]],
            "failed": [],
            "totalMs": 100,
            "executionMs": 80,
            "coldStartMs": 0,
            "warmupMs": 10_000,
            "serverHealthyAfter": True,
        }
        result = v1.result_for(
            fixture=self.fixture,
            request=request,
            framework="native",
            repetition=1,
            execution=execution,
            runtime="node-worker-threads",
            runtime_version="test",
            adapter_version="2.0.0",
        )
        decorate_result(result, self.fixture, "native", execution)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native-result.json"
            path.write_text(json.dumps(result), encoding="utf-8")
            self.assertEqual(
                result_issues_v2(path, request, self.definition_item, "native-result.json"),
                [],
            )
            result["definitionDigest"] = "sha256:" + "0" * 64
            path.write_text(json.dumps(result), encoding="utf-8")
            issues = result_issues_v2(
                path, request, self.definition_item, "native-result.json"
            )
            self.assertIn("definition_binding", {item["code"] for item in issues})

    def test_compiler_rejects_unmerged_adapter_commit(self) -> None:
        receipt = verification_receipt(self.path.name)
        receipt["apps"][0]["adapterCommit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "frozen production commit"):
            compile_definitions([(self.path, self.source_fixture)], receipt)


if __name__ == "__main__":
    unittest.main()
