#!/usr/bin/env python3
"""Deterministic tests for the RocketRide Cloud runner and auditor."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import audit_cloud_appendix as auditor
import run_cloud_appendix as runner


class CloudAppendixTests(unittest.TestCase):
    def test_sanitize_redacts_credentials_and_identifiers(self) -> None:
        secret = "live-secret-value"
        value = {
            "token": "task-token",
            "nested": {"email": "user@example.com", "message": f"bad {secret}"},
        }
        sanitized = runner.sanitize(value, (secret,))
        serialized = json.dumps(sanitized)
        self.assertNotIn("task-token", serialized)
        self.assertNotIn("user@example.com", serialized)
        self.assertNotIn(secret, serialized)
        self.assertIn("sha256:", serialized)

    def test_sanitize_preserves_billing_token_counts(self) -> None:
        sanitized = runner.sanitize(
            {"balances": {"tokens": 7500}, "taskToken": "private-task-token"}
        )
        self.assertEqual(sanitized["balances"]["tokens"], 7500)
        self.assertNotEqual(sanitized["taskToken"], "private-task-token")

    def test_marker_evidence_detects_cross_task_leak(self) -> None:
        expected = "RR_EXPECTED"
        other = "RR_OTHER"
        clean = runner.marker_evidence({"text": expected}, expected, [expected, other])
        leaked = runner.marker_evidence(
            {"text": f"{expected} {other}"}, expected, [expected, other]
        )
        self.assertTrue(clean["markerPresent"])
        self.assertFalse(clean["crossTaskLeak"])
        self.assertEqual(clean["seenMarkers"], [expected])
        self.assertTrue(leaked["crossTaskLeak"])

    def test_manifest_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            required = {
                "receipt.json": "{}\n",
                "RESULTS.md": "result\n",
                "run.log": "log\n",
                "source-manifest.json": "{}\n",
                "billing-before.json": "{}\n",
                "billing-after.json": "{}\n",
                "exact-upstream-attempt.json": "{}\n",
                **{f"repetition-{index:02d}.json": "{}\n" for index in range(1, 4)},
            }
            for name, content in required.items():
                (root / name).write_text(content, encoding="utf-8")
            manifest = runner.artifact_manifest(root)
            runner.write_json(root / "artifact-manifest.json", manifest)
            self.assertEqual(auditor.verify_manifest(root), [])
            (root / "run.log").write_text("changed\n", encoding="utf-8")
            issues = auditor.verify_manifest(root)
            self.assertTrue(any("run.log" in issue for issue in issues))

    def test_terminal_status_accepts_numeric_and_named_states(self) -> None:
        self.assertTrue(runner.terminal_status({"state": 5}))
        self.assertTrue(runner.terminal_status({"state": "terminated"}))
        self.assertFalse(runner.terminal_status({"state": 2}))

    def test_account_organizations_accepts_cloud_and_documented_shapes(self) -> None:
        current = {"organization": {"id": "current"}}
        documented = {"organizations": [{"id": "documented"}]}
        self.assertEqual(runner.account_organizations(current), [{"id": "current"}])
        self.assertEqual(
            runner.account_organizations(documented), [{"id": "documented"}]
        )

    def test_starter_price_accepts_cloud_and_documented_shapes(self) -> None:
        cloud = [
            {
                "nickname": "Starter",
                "amountCents": 5000,
                "currency": "usd",
                "interval": "month",
                "stripePriceId": "price_cloud",
            }
        ]
        documented = [
            {
                "label": "Starter",
                "amount": "$50",
                "cents": 5000,
                "currency": "usd",
                "interval": "month",
                "priceId": "price_documented",
            }
        ]
        self.assertEqual(runner.starter_monthly_price(cloud)["priceId"], "price_cloud")
        self.assertEqual(
            runner.starter_monthly_price(documented)["priceId"], "price_documented"
        )

    def test_billing_gate_accepts_current_promo_shape(self) -> None:
        snapshot = {
            "promoValidation": {
                "valid": True,
                "percentOff": 100.0,
                "discountedAmountCents": 0,
            },
            "subscription": {
                "planNickname": "Starter",
                "status": "active",
                "cancelAtPeriodEnd": True,
            },
        }
        self.assertEqual(runner.billing_gate(snapshot), (True, []))


if __name__ == "__main__":
    unittest.main()
