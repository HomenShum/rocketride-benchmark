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
- Track B V1's `totalMs` includes RocketRide pool warmup and remains protocol
  blocked. V2 is the separately pre-registered always-warm study and cannot
  replace that unfavorable result.
- V2 excludes RocketRide engine and pool readiness from the request clock while
  retaining those values as standing and recovery metrics. Native and LangChain
  retain subprocess startup in their totals, so cross-framework speed rankings
  are not symmetric and are not claimed.
- V2 pool warmup remained substantial: 6,976.188-11,940.908 ms across the 20
  provisioned pools. Meeting the request deadline therefore does not erase
  deployment and failed-worker replacement cost.
- Native controls are additive deterministic workers, not a claim about every
  production deployment topology in the four applications.
- Application validation, version checks, CAS, proposals, and review are
  application guarantees. No framework receives credit for them, and Track B
  attempted no final writes.
- Local compute and engineer time are not monetized. Only model and cloud API spend
  are stated as USD 0.
- RocketRide Cloud was run only for the separately pre-registered deterministic
  Track C control. It used no model provider and cannot replace the pinned local
  baseline or supply a LangChain comparison.
- The exact upstream Cloud pipeline remains blocked because its custom
  `workload` service is absent from the hosted catalog. Cloud validation did not
  expose that incompatibility before execution.
- Track C injects failure by terminating a hosted task through the API. It does
  not prove isolation from an operating-system-level hard crash inside a hosted
  worker.
- Hosted task startup was 25.867-44.476 seconds in Track C. Request latency
  excludes that standing cost but reports it separately.
- The Starter promotion is 100 percent off for the checkout period only. Renewal
  was disabled and verified with `cancelAtPeriodEnd=true`; future account state
  remains external to this repository.
- Physical and non-blank line counts are descriptive authoring evidence, not a
  semantic complexity score.
- Failed provisioning and harness attempts are preserved. Later successful runs
  do not erase the missing-provider, unbounded-send, or connection-lifecycle
  failures recorded in `failures.jsonl` and `deviations.json`.
