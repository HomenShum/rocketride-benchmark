# Node Application Resident-Runtime Study V2 Pre-Registration

Recorded on 2026-07-15 after the V1 post-run audit and before implementing or
executing the V2 runner. This is a new experiment. It does not amend, rerun,
replace, or promote the unfavorable V1 result in
`runs/node-suite-20260715T150250Z/`.

## Motivation

V1 included RocketRide engine and four-process pool provisioning in every
request's `totalMs`, although the pinned upstream harness defines `WarmPool` as
a resident production-serving topology whose standing deployment cost is
reported separately. All 30 V1 RocketRide envelopes consequently exceeded the
fixed 10,000 ms request deadline. A post-V1 lifecycle diagnostic also showed
that an intentionally killed worker leaves its client send pending until the
caller timeout while unaffected workers finish and the engine remains healthy.

V2 tests the pre-declared hypothesis that a resident pool can meet the existing
request deadline when readiness and request clocks are separated and failed
worker detection is bounded. V2 must publish standing and recovery costs next
to request latency, even if the request gate passes.

## Frozen Sources

- Upstream benchmark source: `43be41acb58558dfae8e2e3deb86d8a00cb1b1c8`
- RocketRide SDK: `1.2.0`
- RocketRide engine: `3.2.1.30`
- LangChain Core: `0.3.86`
- NodeRoom production merge: `2ba12a33a9f77a5152096ccf1277d355948b78f6`
- NodeBenchAI production merge: `259d78150fd6bf0d670557707af3ddfefcc4fdc5`
- NodeSlide production merge: `81e0e512cfd4a3d80d24f371bc690810d4f65dd5`
- NodeVideo production merge: `88fab347f853a0d5834eb7559986176ac953d9f8`

The five V1 candidate fixtures and application-owned domain validators remain
unchanged. V2 fixture IDs use a `-v2` suffix and bind the merged application
commit, protocol source hash, adapter source hash, fixture hash, and one
canonical resolved-definition digest. A request and every result envelope must
carry that same definition digest.

## Resolved Definition

Each application workflow is compiled into a canonical JSON definition before
the engine starts. The definition fixes:

- application, workflow, fixture, and merged production commit;
- protocol, candidate adapter, and domain-fixture source hashes;
- candidate-only authority with zero backend mutation capabilities;
- four units, concurrency four, and a 20 ms deterministic unit delay;
- three repetitions of normal and injected hard-failure variants;
- a 2,000 ms per-unit transport/failure-detection timeout;
- the unchanged 10,000 ms request deadline;
- zero retries, paid model calls, and cloud calls;
- pool size four, one thread per pipe, 120 second TTL, and full tracing.

Native, RocketRide, and LangChain receive the same resolved definition and
frozen candidate. The executors still measure scheduling and fault isolation;
they do not receive application write authority or earn model-quality credit.
Application verifier receipts remain the product-correctness evidence.

## Runtime Lifecycle

The engine is started once for the V2 run. RocketRide uses these fixed pool
lifecycles:

1. A normal-variant pool is provisioned and warmed before its first scored
   request, then reused for all three repetitions of that fixture.
2. Every hard-failure repetition begins with a healthy, prewarmed pool. The
   injected hard exit intentionally destroys one member, so that pool is
   retired after the request rather than silently reused.
3. Engine cold start, initial pool provisioning, warmup, faulted-pool teardown,
   and replacement-pool warmup are standing or recovery metrics. None are
   folded into request `totalMs`.
4. `totalMs` starts immediately before dispatching the four request units and
   ends after the fixed one-second trace drain. It therefore includes transport,
   unit execution, bounded failure detection, and trace capture.
5. The two-second per-unit timeout applies to normal and faulted sends. It is
   not a retry and cannot extend the ten-second request deadline.

Native and LangChain retain their V1 subprocess lifecycle and wall-clock
measurement, including process startup. This is conservative for those controls
and is reported as such; V2 makes no raw framework-speed winner claim.

## Acceptance Gates

V2 is locally promotion-ready only when all of the following hold:

- all 90 request/result bindings and candidate digests verify;
- every request and result has the expected resolved-definition digest;
- every normal repetition completes four unique, in-scope units;
- every native and RocketRide hard-failure repetition completes the three
  unaffected units and reports exactly one failed unit;
- the RocketRide engine is healthy after every injected hard failure;
- every framework result has `totalMs <= 10000`;
- all required RocketRide traces exist and the evidence manifest verifies;
- clean merged-commit app verifier receipts pass with protocol and fixture
  parity;
- model calls, model cost, cloud calls, and cloud cost remain zero.

Passing these gates means only that V2 is eligible for external submission.
Official or accepted wording still requires acknowledgment from the RocketRide
team. The V1 protocol failure remains published with equal prominence.

## Deviation and Rerun Policy

- The topology and two-second unit timeout are intentional V2 changes disclosed
  before implementation. They may not be backported into V1 receipts.
- After the first V2 scored execution begins, fixtures, deadlines, unit timeout,
  pool size, retry count, and clock boundaries are frozen.
- Harness defects may be repaired only in a new run with the failed attempt and
  reason retained. Unfavorable valid results are not replaced.
- Live RocketRide Cloud work, if later authorized, is an operational appendix
  and cannot replace either local result.
