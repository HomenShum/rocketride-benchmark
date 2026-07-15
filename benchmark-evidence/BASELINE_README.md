# Independent RocketRide Benchmark Study

This bundle contains two deliberately separate tracks at upstream commit
`43be41acb58558dfae8e2e3deb86d8a00cb1b1c8`.

| Track | Evidence status | Promotion status |
|---|---|---|
| A: unchanged upstream reproduction | Complete on supported Linux; Windows appendix incomplete | Independent, unsubmitted |
| B: Node application extension | Complete, 90 results and 30 RocketRide traces | Blocked by the fixed 10 s protocol deadline |

## Track A

The primary reproduction ran the unchanged benchmark source, fixtures,
competitors, pool sizes, retries, and timeouts on Ubuntu 22.04 under WSL2. All
10 fault-isolation, 10 concurrent-processing, 10 data-isolation, and one
authoring-effort cells completed. The earlier Windows run is retained as an
incomplete exploratory appendix rather than substituted for the supported Linux
result.

This supports only an independent reproduction claim. It does not support a
general framework-superiority claim or an official RocketRide claim without an
external acceptance receipt.

## Track B

Track B compares native worker threads, RocketRide 1.2.0 with local engine
3.2.1.30, and real `langchain-core==0.3.86`. All executors return candidate-only
results; application validation, version checks, CAS, proposals, review, and
final writes remain application-owned.

The N=3 matrix completed for five frozen fixtures in normal and injected
hard-failure variants. Its orchestration gate passed, but the post-run protocol
audit found that all 30 RocketRide envelopes exceeded the fixed 10,000 ms total
deadline. Evidence is complete; protocol admission and promotion are blocked.

## Frozen Applications

| App | Frozen base | Adapter commit |
|---|---|---|
| NodeRoom | `ca25e347dc467bc37f06918e1a18656f7336ee28` | `353ddcce5b4ee791c4a0d70713a47ab302a643b9` |
| NodeBenchAI | `6ed0a58eeda993ff2a937ea4bacc2856756dd521` | `651020807ed13ea3f36cdf6be601f5a874705b29` |
| NodeSlide | `dd67e4c642c40e6bb414af617a67a31dbed507c5` | `702020d5cdd9785bfb4e6b79a30246a3c88a23b5` |
| NodeVideo | `bb79bc385de93c90cee89b160fc801d18372d89e` | `cf2c696e1c0ccea6ebb43617dc81a23f05e785da` |

## Evidence Map

- Track A primary summary: `baseline/linux/linux-20260715T122439Z/aggregate/summary.json`
- Track A Windows appendix: `baseline/concurrent-work/aggregate/summary.json`
- Track B pre-registration: `extensions/node-suite/PRE_REGISTRATION.md`
- App verifier: `extensions/node-suite/app-verification.json`
- Post-run app verifier: `extensions/node-suite/app-verification-post-run.json`
- Track B original scorecard: `extensions/node-suite/runs/node-suite-20260715T150250Z/scorecard.json`
- Track B superseding protocol audit: `extensions/node-suite/runs/node-suite-20260715T150250Z/audit.json`
- Rerun history: `failures.jsonl` and `deviations.json`

No model or cloud API was called. Model and cloud spend are both USD 0. Raw
credentials, promotion codes, cloud tokens, and local environment files are not
included.
