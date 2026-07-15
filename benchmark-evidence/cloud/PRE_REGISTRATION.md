# RocketRide Cloud Operational Appendix Pre-Registration

Status: frozen before the measured hosted run

This appendix answers a narrower question than the pinned local benchmark:
can a fixed resident pool execute isolated concurrent work on RocketRide Cloud,
and does terminating one hosted task leave the other tasks usable? It does not
replace Track A, rescore the upstream suite, or create an official RocketRide
claim.

## Frozen Inputs

- Upstream benchmark commit: `43be41acb58558dfae8e2e3deb86d8a00cb1b1c8`
- Cloud endpoint: `https://api.rocketride.ai`
- RocketRide Python SDK: `1.2.0`
- Pool size: 4 resident tasks
- Normal documents per repetition: 16
- Repetitions: 3
- Retries inside a measured cell: 0
- Model calls: 0
- Workload: deterministic `webhook -> parse -> response_text` pipeline
- Promotion code: `JULY2026BENCHMARK`, recorded only by name and sanitized
  validation result

Setup probes performed before this commit are excluded from scored metrics and
listed in `SETUP_ATTEMPTS.md`.

## Exact Upstream Compatibility Attempt

Each measured run first attempts the unchanged upstream fault-isolation
pipeline on Cloud. The full success or failure is retained. If the hosted
service catalog lacks the benchmark's custom `workload` service, the exact
upstream Cloud status is `blocked_missing_workload_service`; the control run
may still continue but cannot be described as an upstream benchmark result.

## Normal Phase

Each resident task receives a warm-up request outside the measured request
set. Sixteen unique synthetic documents are then distributed deterministically
across the four tasks. The four task workers run concurrently, while requests
assigned to one task remain sequential. Every response must contain exactly
its expected unique marker and no marker belonging to another request.

## Failure Phase

Task 0 is terminated and observed in a terminal state. One new unique request
is sent to each task concurrently. The terminated task must fail, tasks 1-3
must succeed, and each successful response must contain only its expected
marker. This is a task-termination isolation test, not a claim that the hosted
worker process was killed at the operating-system boundary.

## Admission Gates

The Cloud control passes only if all of the following hold:

- all 3 repetitions complete with 4 resident tasks each;
- all 48 normal requests succeed with correct markers;
- all 9 unaffected failure-phase requests succeed with correct markers;
- all 3 requests to terminated task 0 fail;
- no response contains a marker from another request;
- every created task is terminated during cleanup;
- receipt hashes and the independent audit pass;
- billing readback shows Starter active, 100 percent checkout discount,
  charged amount USD 0, and renewal disabled at period end.

The runner records task-token hashes, never task tokens or API credentials.
Raw account, organization, subscription, and team identifiers are excluded or
hashed. The run is invalid if a credential appears in a committed artifact.

## Status Vocabulary

- `evidenceStatus`: whether the declared artifacts are complete and auditable.
- `controlAdmissionStatus`: pass/fail for the Cloud-native control above.
- `exactUpstreamCloudStatus`: result of executing the unchanged upstream pipe.
- `officialStatus`: always `cloud_operational_appendix_unsubmitted` until an
  external RocketRide maintainer accepts or publishes the evidence.

No rerun may erase a prior failure. A rerun must use a new run directory and
retain the reason in the failure ledger. Changing pool size, document count,
repetitions, pipeline, retry policy, or gates requires a new pre-registration.

