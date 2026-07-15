# RocketRide Cloud Appendix Results

## Status

- Evidence status: `complete`
- Cloud control admission: `passed`
- Exact upstream Cloud status: `blocked_missing_workload_service`
- Official status: `cloud_operational_appendix_unsubmitted`
- Control gate: **PASS**

The unchanged upstream pipeline did not receive an official Cloud score. Its
hosted attempt returned `The service workload was not found`. The separate
built-in-service control used no model provider and made no paid model calls.

## Control Counts

| Check | Result |
|---|---:|
| Repetitions | 3 |
| Resident tasks created | 12 |
| Normal requests correct | 48/48 |
| Unaffected failure requests correct | 9/9 |
| Terminated-task requests failed as expected | 3/3 |
| Cross-task leaks | 0 |
| Successful task termination calls | 12/12 |

## Billing

- Promotion: `JULY2026BENCHMARK`
- Starter checkout amount: `$50`
- Billing gate passed: `true`
- Renewal disabled: `true`

This appendix is independently auditable operational evidence. It remains
unsubmitted until RocketRide maintainers accept it, and it does not replace the
pinned local benchmark.
