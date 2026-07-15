# Limitations

- No RocketRide team acceptance, official publication, or external scorer receipt
  exists. Every result is independent and unsubmitted.
- The primary Linux host is Ubuntu 22.04 under WSL2 on x86-64, not the Apple
  Silicon host used for upstream committed results. Timing remains host-dependent.
- The Windows appendix is incomplete: data isolation never completed its first
  repetition within the unchanged retry and timeout contract.
- Track B covers five deterministic fixtures with frozen candidate artifacts. It
  measures binding, scheduling, failure isolation, and admission behavior, not
  model quality or framework-specific artifact generation.
- Broader cancellation, checkpoint/resume, duplicate callback, and malformed
  candidate scenarios remain outside the scored V1 matrix even where app verifier
  tests cover related invariants.
- Track B's `totalMs` includes RocketRide pool warmup. That is consistent with the
  shared result validator and fixed request deadline, but a separately
  pre-registered always-warm service study could answer a different question.
- Native controls are additive deterministic workers, not a claim about every
  production deployment topology in the four applications.
- Application validation, version checks, CAS, proposals, and review are
  application guarantees. No framework receives credit for them, and Track B
  attempted no final writes.
- Local compute and engineer time are not monetized. Only model and cloud API spend
  are stated as USD 0.
- RocketRide Cloud and live providers were not run. A cloud result cannot replace
  the pinned local baseline.
- Physical and non-blank line counts are descriptive authoring evidence, not a
  semantic complexity score.
- Failed provisioning and harness attempts are preserved. Later successful runs
  do not erase the missing-provider, unbounded-send, or connection-lifecycle
  failures recorded in `failures.jsonl` and `deviations.json`.
