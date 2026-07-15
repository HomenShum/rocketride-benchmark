# Independent Windows Baseline

Evidence status: **evidence_incomplete**. External status: **independent_unsubmitted_reproduction**.
This is an unchanged local reproduction, not a RocketRide-accepted official result.

## Completeness

| Benchmark | Expected | Observed | Complete |
|---|---:|---:|---|
| fault-isolation | 10 | 10 | true |
| concurrent-processing | 10 | 10 | true |
| data-isolation | 10 | 0 | false |
| authoring-effort | 1 | 1 | true |

## Dimensional Results

- Fault isolation: RocketRide held in 10/10 runs; the in-process LangChain probe lost all work in 10/10 runs.
- RocketRide pool M=8: warm execution median 45.514 s, p95 80.232 s; warm-up median 26.775 s; clean 10/10.
- RocketRide pool M=16: warm execution median 60.821 s, p95 81.444 s; warm-up median 63.655 s; clean 0/10.
- LangChain batch_shared: statuses crash; wall median 0.042 s, p95 0.056 s.
- LangChain abatch_blocking: statuses ok; wall median 7.292 s, p95 7.344 s.
- LangChain seq: statuses ok; wall median 7.435 s, p95 7.612 s.
- Data isolation: RocketRide clean 0/0; lost-doc median None; duplicated/leaked median None.
- Preserved retry signals: {"concurrent-processing": 9, "data-isolation": 5}.

Cold start, warm-up, and warm execution remain separate. Resource fields are reported only where the upstream result emits them.

## Evidence Gaps

- data-isolation: expected 10 results, observed 0
