# RocketRide Cloud Appendix Results

## Status

- Evidence status: `complete`
- Cloud control admission: `failed`
- Exact upstream Cloud status: `blocked_missing_workload_service`
- Official status: `cloud_operational_appendix_unsubmitted`
- Control gate: **FAIL**

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

- Promotion: `None`
- Starter checkout amount: `None`
- Billing gate passed: `false`
- Renewal disabled: `false`

This appendix is independently auditable operational evidence. It remains
unsubmitted until RocketRide maintainers accept it, and it does not replace the
pinned local benchmark.
