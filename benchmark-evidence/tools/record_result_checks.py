#!/usr/bin/env python3
"""Append idempotent benchmark-owned check failures to the external ledger."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "concurrent-work" / "runs-windows"
LEDGER = REPO / "benchmark-evidence" / "failures.jsonl"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def existing_keys() -> set[str]:
    keys: set[str] = set()
    if not LEDGER.exists():
        return keys
    for raw in LEDGER.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        value = json.loads(raw)
        if isinstance(value.get("eventKey"), str):
            keys.add(value["eventKey"])
    return keys


def append(value: dict) -> None:
    with LEDGER.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def main() -> int:
    known = existing_keys()
    added = 0
    for result_path in sorted(RUNS.glob("*/run-*/results.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        benchmark = str(result.get("benchmark", result_path.parents[1].name))
        run_name = result_path.parent.name
        checks: list[tuple[str, str]] = []
        if benchmark == "concurrent-processing":
            for cell in result.get("rocketride", []):
                if cell.get("status") != "ok":
                    checks.append(
                        (
                            f"M={cell.get('M')}",
                            f"RocketRide status={cell.get('status')}; rows={cell.get('sqlite_rows')}/{cell.get('rows_expected')}; node_errors={cell.get('node_errors')}",
                        )
                    )
        elif benchmark == "data-isolation":
            cell = result.get("rocketride", {})
            if cell.get("status") != "ok":
                checks.append(
                    (
                        f"M={cell.get('M')}",
                        f"RocketRide status={cell.get('status')}; lost={cell.get('docs_lost')}; leaked={cell.get('docs_duplicated_or_leaked')}",
                    )
                )
        elif benchmark == "fault-isolation":
            if result.get("verdict_metrics", {}).get("rr_isolation_holds") is not True:
                checks.append(("fault-isolation", "RocketRide isolation verdict did not hold"))

        for cell, message in checks:
            key = f"baseline:{benchmark}:{run_name}:{cell}"
            if key in known:
                continue
            append(
                {
                    "schemaVersion": "node.rocketride.failure/v1",
                    "event": "benchmark_result_check",
                    "eventKey": key,
                    "failure": True,
                    "at": utc_now(),
                    "commandId": "baseline-isolated-windows-n10",
                    "benchmark": benchmark,
                    "run": run_name,
                    "cell": cell,
                    "message": message,
                    "result": result_path.relative_to(REPO).as_posix(),
                    "rerunEligible": False,
                    "handling": "Preserve and report; do not replace an unfavorable valid result.",
                }
            )
            known.add(key)
            added += 1
    print(json.dumps({"added": added, "known": len(known)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
