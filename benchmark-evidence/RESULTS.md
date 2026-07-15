# Results

## Claim Status

- **Track A:** evidence complete, independent unsubmitted reproduction.
- **Track B:** evidence complete, orchestration gate passed, protocol admission
  failed, promotion blocked.
- **Official status:** no external RocketRide acceptance or publication receipt.
- **Paid spend:** USD 0 model cost and USD 0 cloud cost.

## Track A: Supported Linux

The unchanged upstream suite completed at commit
`43be41acb58558dfae8e2e3deb86d8a00cb1b1c8` with no aggregate gate issues.

| Dimension | RocketRide | LangChain control |
|---|---|---|
| Hard-failure isolation, N=10 | Held 10/10 | Lost all work 10/10 |
| Concurrent work, pool 8 | 10/10 clean; wall median 1.285 s, p95 1.548 s | `batch_shared` crashed; `abatch` median 7.522 s; sequential median 7.530 s |
| Concurrent work, pool 16 | 10/10 clean; wall median 0.867 s, p95 1.040 s | Same controls as above |
| Data isolation, N=10 | 10/10 clean; 0 lost, duplicated, or leaked; wall median 5.508 s | Not a direct equivalent result in this cell |
| Warm deployment cost | Pool 8 median 9.160 s; pool 16 median 15.590 s; data median 30.085 s | Reported separately from measured work |
| Authoring descriptor | 0 imperative lines in the authored pipe | 14-17 imperative lines; 5 decision points for the correct idiom |

The thread-count appendix emitted a median 31 node errors and is not used as a
headline result.

## Track A: Windows Appendix

The unchanged Windows path is evidence-incomplete. Fault and concurrency cells
completed, but data-isolation repetition 1 timed out on all five unchanged
360-second attempts.

- RocketRide pool 8 was clean 10/10 but had wall median 45.514 s versus
  LangChain `abatch` 7.292 s.
- RocketRide pool 16 was clean 0/10, retained 152 rows where 80 were expected,
  and had wall median 60.821 s. Open SQLite cleanup on Windows is a recorded
  inference, not a patched or promoted result.
- This appendix cannot replace the supported Linux reproduction.

## Track B: Node Applications

The app verifier passed all four immutable adapter commits, base ancestry,
canonical fixture parity, application tests, and shared protocol hash
`b9b8b9f293c486fcd68f532f177e40f86c07c9310f31a64aa316ba469c1b1d59`.

The completed matrix contains five fixtures, two variants, three repetitions,
three frameworks, 30 requests, 90 result envelopes, 30 RocketRide traces, and
30 aggregate rows.

| Dimension | Native | RocketRide | LangChain |
|---|---|---|---|
| Normal correctness | 4/4 units in all 15 runs | 4/4 units in all 15 runs | 4/4 units in all 15 runs |
| Injected hard failure | 3 unaffected units in all 15 runs | 3 unaffected units in all 15 runs; engine healthy after every run | Shared interpreter completed 0/4 in all 15 runs |
| Normal total median range | 190.836-203.875 ms | 25,966.952-31,814.868 ms | 1,220.388-1,390.712 ms |
| Hard-failure total median range | 176.464-222.259 ms | 31,934.275-37,909.386 ms | 1,057.141-1,139.453 ms before process loss was recorded |
| Candidate digest | Frozen candidate parity held | Frozen candidate parity held | Frozen candidate parity held |
| Model/cloud cost | USD 0 / USD 0 | USD 0 / USD 0 | USD 0 / USD 0 |

### Promotion Blocker

The original scorecard's completion/isolation gate reports `passed`. The later
audit mirrors the shared app protocol and supersedes that status for promotion:
all 30 RocketRide envelopes had `totalMs > deadlineMs` (10,000 ms). They would be
rejected before candidate admission. The audit therefore reports:

```text
evidenceStatus: complete
protocolAdmissionStatus: failed
promotionStatus: blocked
officialStatus: separate_application_study_unsubmitted
```

This is still a useful integration result: RocketRide isolated worker failure,
but the tested local resident-pool lifecycle is too slow for the pre-registered
application contract. The appropriate next experiment is a newly pre-registered
warm-service topology or deadline budget study, not retroactively changing this
run.
