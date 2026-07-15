# Node Application Extension Pre-Registration

This protocol is fixed before implementing or executing any Node application
adapter. It is separate from the unchanged upstream reproduction.

The V1 run and its unfavorable deadline audit remain immutable. A separate
resident-runtime experiment is pre-registered in `PRE_REGISTRATION_V2.md` and
must not be presented as a rerun or replacement of V1.

## Systems

Every scored fixture compares three systems:

1. The application's current native runtime.
2. A RocketRide execution adapter.
3. A LangChain execution adapter.

The native runtime is the control. A RocketRide win over LangChain does not justify
adoption when RocketRide regresses against the application's current runtime.

## Runtime Boundary

All systems receive the same request and return a candidate result. Neither
RocketRide nor LangChain may mutate application state directly.

```ts
type NodeWorkflowRequest = {
  app: "nodevideo" | "nodeslide" | "noderoom" | "nodebenchai";
  workflow: string;
  fixtureId: string;
  traceId: string;
  inputDigest: string;
  baseVersion?: number;
  idempotencyKey: string;
  concurrency: number;
  deadlineMs: number;
  failureSeed?: string;
};

type NodeWorkflowResult<TCandidate> = {
  runId: string;
  traceId: string;
  framework: "native" | "rocketride" | "langchain";
  candidate: TCandidate;
  inputDigest: string;
  outputDigest: string;
  events: NodeRunEvent[];
  metrics: NodeRunMetrics;
  provenance: RuntimeProvenance;
  error?: StructuredRunError;
};
```

Candidate results are then passed through the same domain validation, version,
CAS, proposal, and review path. Frameworks receive no credit for guarantees
provided by those application-owned gates.

## Fixed Conditions

- Same frozen application commit and fixture seed.
- Same input digest and base version.
- Same deterministic model stub for scored runs.
- Same prompts and tool implementations.
- Same candidate output schema and domain validators.
- Same retry budget, deadline, concurrency, and failure injection.
- Same idempotency-key behavior.
- No paid model-provider call in a deterministic scored lane.
- Live providers and RocketRide Cloud are reported only as operational appendices.

## Required Dimensions

Results remain dimensional; there is no opaque combined winner score.

| Dimension | Required evidence |
|---|---|
| Correctness | Lost, duplicated, leaked, stale, or invalid outputs |
| Failure isolation | Unaffected work completed after one failure |
| Recovery | Checkpoint, resume, retry, and idempotency behavior |
| Product fidelity | Domain validation and artifact invariants |
| Authoring | Application-specific code, configuration, and hidden decisions |
| Performance | Cold, warm, p50, p95, throughput |
| Cost | Model, compute, cloud, and wasted retry/render cost |
| Operability | Trace completeness, debugging effort, deployment complexity |

## Application Fixtures

## Amendment 1: V1 Scored Matrix

Recorded on 2026-07-15 before the first extension-suite execution. This
amendment narrows the fixture catalog below into an executable V1 matrix; it
does not change a result after observation.

The scored V1 matrix contains these frozen fixtures:

- `noderoom-independent-writes-v1`
- `noderoom-conflict-proposal-v1`
- `nodebenchai-frozen-sources-v1`
- `nodeslide-independent-elements-v1`
- `nodevideo-resume-shots-v1`

Each fixture runs three repetitions on native worker threads, RocketRide, and
LangChain in both normal and injected hard-failure variants. Every repetition
uses four units, concurrency four, a 20 ms deterministic unit delay, a 10 s
deadline, and a hard exit in the first unit for the failure variant.

The candidate object in each V1 fixture is a frozen expected artifact. The
executors exercise unit scheduling and isolation; they do not call a model or
generate that artifact. Candidate-digest parity therefore proves request,
receipt, fixture, and application-verifier binding only. It is not evidence of
model quality or framework-specific candidate generation.

Application-owned verifier tests additionally exercise stale versions,
duplicate targets, replay-key mismatches, cross-room/project/asset boundaries,
and external-publication claim gating. Catalog scenarios below that are not in
the five-item list, including full checkpoint/resume and cancellation studies,
remain future work and receive no V1 score or coverage claim.

### NodeRoom

- Independent writes to different cells and notebook blocks.
- Human/agent conflict on one semantic target from the same base version.
- One worker crash while unaffected research jobs finish.
- Duplicate delivery with one idempotency key.
- Resume after evidence collection and before proposal publication.
- Cross-room isolation for similarly named entities.

Candidates are patch bundles or Compare-Reason-Swap proposals. Final writes remain
behind RoomTools, version checks, CAS, and review.

### NodeBenchAI

- Parallel frozen-source retrieval.
- Partial provider failure and slow-source timeout.
- Evidence extraction and deterministic report compilation.
- Retry/resume, budget enforcement, and cross-run memory isolation.

Candidates are answer/report packets with evidence bindings. Live web research is
not part of the parity score because sources change over time.

### NodeSlide

- Independent slide edits.
- Independent element edits on one slide.
- Stale proposal against a newer base version.
- One slide worker crash.
- Concurrent chart/data and text/layout updates.
- Duplicate proposal delivery and malformed candidate repair.

Candidates are typed patch operations. Deck validation and proposal acceptance stay
inside NodeSlide.

### NodeVideo

- Parallel deterministic segment analysis.
- Beat and text-overlay mapping.
- One renderer timeout and cancellation.
- Resume without rerendering completed shots.
- Duplicate callback delivery.
- Cross-project isolation for similarly named assets.

Candidates are edit-decision lists and render manifests. Worker receipts and final
proposal acceptance stay inside NodeVideo.

## Rerun Policy

1. Every failed process remains in `benchmark-evidence/failures.jsonl`.
2. A rerun is allowed only for a documented environmental failure such as an
   unavailable engine, machine interruption, disk exhaustion, or corrupt
   provisioning.
3. Pool sizes, retries, timeouts, fixtures, prompts, tools, and source functions are
   not changed after observing an unfavorable result.
4. Any required upstream patch is first recorded as an unpatched blocker. Patched
   experiments are separate and cannot replace the baseline.
5. Deviations appear in the top-level evidence file, not only in report footnotes.

## Promotion Rules

- An upstream reproduction finding requires raw results, logs, traces where emitted,
  environment provenance, and a recomputed aggregate.
- An application finding requires the same request digest across all systems plus a
  verifier receipt from the application-owned invariant checker.
- A cloud result is never substituted for the pinned local baseline.
- A framework loss is reported with the same prominence as a win.
- Official or accepted language requires an external RocketRide acknowledgment or
  submission receipt. Local success alone is not official.

## Cloud Rule

RocketRide Cloud may be used only after the pinned local baseline. The promotional
code and all credentials remain outside the repository. Account creation, promotion
redemption, or persistent-token creation requiring a human confirmation is recorded
as an external blocker rather than bypassed.
