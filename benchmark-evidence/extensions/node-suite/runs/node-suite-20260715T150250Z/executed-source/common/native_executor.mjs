#!/usr/bin/env node
import { readFile, writeFile } from "node:fs/promises";
import { isMainThread, parentPort, workerData, Worker } from "node:worker_threads";
import process from "node:process";

if (!isMainThread) {
  const { unit, delayMs, failureUnit } = workerData;
  await new Promise((resolve) => setTimeout(resolve, delayMs));
  if (unit.id === failureUnit) process.exit(86);
  parentPort.postMessage({ id: unit.id });
} else {
  const [inputPath, outputPath] = process.argv.slice(2);
  if (!inputPath || !outputPath) {
    console.error("usage: native_executor.mjs INPUT.json OUTPUT.json");
    process.exit(2);
  }
  const input = JSON.parse(await readFile(inputPath, "utf8"));
  const started = process.hrtime.bigint();
  const cpuStarted = process.cpuUsage();
  const completed = [];
  const failed = [];
  const queue = [...input.units];
  const concurrency = Math.max(1, Math.min(input.concurrency, queue.length));

  async function workerLoop() {
    while (queue.length > 0) {
      const unit = queue.shift();
      const outcome = await runIsolated(unit, input.delayMs, input.failureUnit);
      if (outcome.ok) completed.push(unit.id);
      else failed.push(unit.id);
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => workerLoop()));
  const elapsedMs = Number(process.hrtime.bigint() - started) / 1e6;
  const cpu = process.cpuUsage(cpuStarted);
  await writeFile(
    outputPath,
    JSON.stringify(
      {
        completed,
        failed,
        totalMs: elapsedMs,
        executionMs: elapsedMs,
        coldStartMs: 0,
        warmupMs: 0,
        peakRssBytes: process.memoryUsage.rss(),
        cpuTimeMs: (cpu.user + cpu.system) / 1000,
        runtimeVersion: process.version,
      },
      null,
      2,
    ) + "\n",
  );
}

function runIsolated(unit, delayMs, failureUnit) {
  return new Promise((resolve) => {
    const worker = new Worker(new URL(import.meta.url), {
      workerData: { unit, delayMs, failureUnit },
    });
    let settled = false;
    worker.once("message", () => {
      settled = true;
      resolve({ ok: true });
    });
    worker.once("error", () => {
      if (!settled) {
        settled = true;
        resolve({ ok: false });
      }
    });
    worker.once("exit", (code) => {
      if (!settled) {
        settled = true;
        resolve({ ok: code === 0 });
      }
    });
  });
}
