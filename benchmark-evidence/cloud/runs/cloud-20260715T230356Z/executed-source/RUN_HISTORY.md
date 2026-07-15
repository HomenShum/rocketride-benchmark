# RocketRide Cloud Run History

Runs are append-only. A later passing control does not erase an earlier failed
gate or convert the exact upstream pipeline into a hosted result.

| Run | Control operations | Overall gate | Reason |
|---|---|---|---|
| `cloud-20260715T225614Z` | 48/48 normal correct, 9/9 unaffected correct, 3/3 terminated-task failures, 0 leaks | Failed | Billing collector expected the SDK-documented plural `organizations`; Cloud returned singular `organization`. The failed receipt and failed audit are retained. |

The runner was updated only to accept both account-envelope shapes. The frozen
pool size, repetitions, documents, pipeline, retry policy, model-call count,
and admission gates did not change.
