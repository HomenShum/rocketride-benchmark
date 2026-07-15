# Supported Linux Reproduction

Evidence status: **evidence_complete**. External status: **independent_unsubmitted_reproduction**.
This is an unchanged benchmark-source reproduction on WSL2 Ubuntu, not a RocketRide-accepted official result.

| Benchmark | Expected | Observed | Complete |
|---|---:|---:|---|
| fault-isolation | 10 | 10 | true |
| concurrent-processing | 10 | 10 | true |
| data-isolation | 10 | 10 | true |
| authoring-effort | 1 | 1 | true |

## Dimensional Results

- Fault isolation: RocketRide held in 10/10 runs; LangChain lost all work in 10/10.
- RocketRide M=8: wall median 1.285 s, p95 1.548 s; warm-up median 9.16 s; clean 10/10.
- RocketRide M=16: wall median 0.867 s, p95 1.04 s; warm-up median 15.59 s; clean 10/10.
- LangChain batch_shared: statuses crash; wall median 0.057 s, p95 0.08 s.
- LangChain abatch_blocking: statuses ok; wall median 7.522 s, p95 7.592 s.
- LangChain seq: statuses ok; wall median 7.53 s, p95 7.968 s.
- Data isolation: RocketRide clean 10/10; lost median 0.0; duplicated/leaked median 0.0.
- Preserved Linux failure signals: 14 total, 0 retries.
