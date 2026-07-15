#!/usr/bin/env python3
"""Real LangChain in-process executor; a hard-failing unit kills this child."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

from langchain_core.runnables import RunnableLambda
import langchain_core
import psutil


async def main(input_path: Path, output_path: Path) -> None:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    started = time.perf_counter()
    cpu_started = time.process_time()

    async def execute(unit: dict) -> str:
        await asyncio.sleep(float(payload["delayMs"]) / 1000.0)
        if unit["id"] == payload.get("failureUnit"):
            sys.stderr.write("NODE_SUITE_LANGCHAIN_HARD_FAILURE\n")
            sys.stderr.flush()
            os._exit(86)
        return str(unit["id"])

    results = await RunnableLambda(execute).abatch(
        payload["units"],
        config={"max_concurrency": int(payload["concurrency"])},
        return_exceptions=True,
    )
    completed = [result for result in results if isinstance(result, str)]
    failed = [
        str(payload["units"][index]["id"])
        for index, result in enumerate(results)
        if isinstance(result, BaseException)
    ]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    process = psutil.Process()
    output_path.write_text(
        json.dumps(
            {
                "completed": completed,
                "failed": failed,
                "totalMs": elapsed_ms,
                "executionMs": elapsed_ms,
                "coldStartMs": 0,
                "warmupMs": 0,
                "peakRssBytes": process.memory_info().rss,
                "cpuTimeMs": (time.process_time() - cpu_started) * 1000.0,
                "runtimeVersion": sys.version.split()[0],
                "langchainCoreVersion": langchain_core.__version__,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.input, args.output))
