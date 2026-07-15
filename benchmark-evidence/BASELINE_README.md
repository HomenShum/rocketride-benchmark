# Independent RocketRide Benchmark Study

This evidence bundle contains two deliberately separate tracks.

## Track A: Upstream Reproduction

Track A reproduces `rocketride-org/rocketride-benchmark` at commit
`43be41acb58558dfae8e2e3deb86d8a00cb1b1c8`. The benchmark source, fixtures,
competitor implementations, pool sizes, retries, and timeouts remain unchanged.
The run uses the upstream-documented Windows path in
`concurrent-work/harness/REPRODUCE-WINDOWS.md`.

Track A may support only an independent reproduction claim. It does not support a
general framework-superiority claim, a raw single-request speed claim, or an
official RocketRide submission claim unless the RocketRide team accepts the
result and evidence bundle.

## Track B: Node Application Extension

Track B compares each application's current native runtime with candidate-only
RocketRide and LangChain execution adapters. Candidate artifacts still pass
through each application's existing validation, version, CAS, proposal, and
review boundaries. Results from Track B are Node ecosystem findings, not upstream
RocketRide benchmark results.

The fixed protocol is in
`extensions/node-suite/PRE_REGISTRATION.md`. Raw credentials, the promotional
code, cloud tokens, and local environment files are excluded from this bundle.

## Frozen Inputs

- Upstream and fork commit: `43be41acb58558dfae8e2e3deb86d8a00cb1b1c8`
- NodeRoom: `ca25e347dc467bc37f06918e1a18656f7336ee28`
- NodeBenchAI: `6ed0a58eeda993ff2a937ea4bacc2856756dd521`
- NodeSlide: `dd67e4c642c40e6bb414af617a67a31dbed507c5`
- NodeVideo: `bb79bc385de93c90cee89b160fc801d18372d89e`

## Completion Rule

No result is promoted from a transcript or an implementation assertion. A result
must point to deterministic output, a raw run, a trace, a verifier receipt, or an
accepted external scorer. Failed attempts remain in `failures.jsonl` even if a
later rerun succeeds.
