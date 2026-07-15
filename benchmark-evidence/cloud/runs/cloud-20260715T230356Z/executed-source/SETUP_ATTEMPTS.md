# RocketRide Cloud Setup Attempts

These unscored probes occurred before the Cloud appendix was frozen. They are
retained because setup and portability friction are part of an honest study.
No credential or private account identifier is included.

| Sequence | Probe | Result |
|---|---|---|
| 1 | Connect to the endpoint shown by an older TypeScript quickstart | `https://cloud.rocketride.ai` timed out because it serves the web application rather than the current API endpoint. |
| 2 | Connect to the current documented endpoint with `timeout=30` | Timed out because SDK 1.2.0 interprets the value as milliseconds. `timeout=30000` connected and authenticated. |
| 3 | Run with a Development-scoped key carrying control, data, and monitor selections | Task creation returned `Permission 'task.control' denied`; the result repeated when the team identifier was supplied. |
| 4 | Run with an all-team benchmark key | Connected successfully and listed 128 hosted services. The key is stored outside every repository and expires after the study window. |
| 5 | Execute the unchanged upstream `.pipe` on Cloud | Validation reported no error, but task creation failed after about 8 seconds because service `workload` was not found in the hosted catalog. |
| 6 | Execute a built-in-service control smoke | `webhook -> parse -> response_text` started in 11878.294 ms and returned a 294-byte response in 640.951 ms. This setup smoke is not a scored repetition. |
| 7 | Validate and redeem `JULY2026BENCHMARK` for Starter | Validation returned 100 percent off and USD 0 due at checkout. Starter became active. |
| 8 | Disable paid renewal | The cancellation call returned `Internal error: 'str' object has no attribute 'tzinfo'`; immediate billing readback nevertheless reported `cancelAtPeriodEnd=true`. The measured receipt must verify this state again. |

The Development-scoped key failure, hosted `workload` absence, endpoint drift,
timeout-unit ambiguity, and cancellation response error remain reportable
RocketRide findings even if the Cloud-native control passes.

