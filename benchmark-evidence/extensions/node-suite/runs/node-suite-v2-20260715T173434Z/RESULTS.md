# Node Application Resident-Runtime Study V2

Gate status: **passed**. External status: **separate_application_study_unsubmitted**.

V1 remains a failed protocol result with 30 RocketRide deadline overruns; V2 does not replace it.
All V2 work is deterministic and local. Model and cloud cost are USD 0.
RocketRide request totals exclude separately reported engine and pool readiness costs under the pre-registered resident topology.

| App | Variant | Framework | Completed p50 | Failed p50 | Deadline overruns | Request p50 ms | Request p95 ms | Standing warmup p50 ms |
|---|---|---|---:|---:|---:|---:|---:|---:|
| nodebenchai | normal | native | 4.0 | 0.0 | 0 | 149.334 | 160.864 | 0.0 |
| nodebenchai | normal | rocketride | 4.0 | 0.0 | 0 | 1047.66 | 1047.715 | 6976.188 |
| nodebenchai | normal | langchain | 4.0 | 0.0 | 0 | 849.079 | 3717.075 | 0.0 |
| nodebenchai | hard-failure | native | 3.0 | 1.0 | 0 | 143.617 | 144.594 | 0.0 |
| nodebenchai | hard-failure | rocketride | 3.0 | 1.0 | 0 | 3015.926 | 3020.947 | 7516.513 |
| nodebenchai | hard-failure | langchain | 0.0 | 4.0 | 0 | 746.131 | 757.176 | 0.0 |
| noderoom | normal | native | 4.0 | 0.0 | 0 | 154.232 | 171.398 | 0.0 |
| noderoom | normal | rocketride | 4.0 | 0.0 | 0 | 1066.442 | 1117.888 | 7721.659 |
| noderoom | normal | langchain | 4.0 | 0.0 | 0 | 790.117 | 837.536 | 0.0 |
| noderoom | hard-failure | native | 3.0 | 1.0 | 0 | 137.18 | 164.19 | 0.0 |
| noderoom | hard-failure | rocketride | 3.0 | 1.0 | 0 | 3008.731 | 3020.075 | 10270.205 |
| noderoom | hard-failure | langchain | 0.0 | 4.0 | 0 | 733.217 | 843.463 | 0.0 |
| noderoom | normal | native | 4.0 | 0.0 | 0 | 136.618 | 138.367 | 0.0 |
| noderoom | normal | rocketride | 4.0 | 0.0 | 0 | 1090.228 | 1161.292 | 7098.088 |
| noderoom | normal | langchain | 4.0 | 0.0 | 0 | 813.877 | 861.757 | 0.0 |
| noderoom | hard-failure | native | 3.0 | 1.0 | 0 | 161.455 | 183.519 | 0.0 |
| noderoom | hard-failure | rocketride | 3.0 | 1.0 | 0 | 3010.899 | 3026.015 | 10564.903 |
| noderoom | hard-failure | langchain | 0.0 | 4.0 | 0 | 930.532 | 944.139 | 0.0 |
| nodeslide | normal | native | 4.0 | 0.0 | 0 | 156.006 | 182.081 | 0.0 |
| nodeslide | normal | rocketride | 4.0 | 0.0 | 0 | 1046.107 | 1715.671 | 10734.274 |
| nodeslide | normal | langchain | 4.0 | 0.0 | 0 | 897.225 | 966.281 | 0.0 |
| nodeslide | hard-failure | native | 3.0 | 1.0 | 0 | 161.048 | 170.257 | 0.0 |
| nodeslide | hard-failure | rocketride | 3.0 | 1.0 | 0 | 3025.511 | 3033.088 | 10816.273 |
| nodeslide | hard-failure | langchain | 0.0 | 4.0 | 0 | 905.507 | 909.288 | 0.0 |
| nodevideo | normal | native | 4.0 | 0.0 | 0 | 149.746 | 155.421 | 0.0 |
| nodevideo | normal | rocketride | 4.0 | 0.0 | 0 | 1043.073 | 1048.59 | 9061.812 |
| nodevideo | normal | langchain | 4.0 | 0.0 | 0 | 817.925 | 948.426 | 0.0 |
| nodevideo | hard-failure | native | 3.0 | 1.0 | 0 | 145.608 | 178.383 | 0.0 |
| nodevideo | hard-failure | rocketride | 3.0 | 1.0 | 0 | 3024.154 | 3038.027 | 8669.367 |
| nodevideo | hard-failure | langchain | 0.0 | 4.0 | 0 | 776.022 | 830.844 | 0.0 |

## Standing And Recovery Cost

- Engine cold start: 1569.703 ms.
- Normal pool warmup p50: 7721.659 ms.
- Hard-failure replacement warmup p50: 10109.896 ms.
- Pools provisioned: 20.

## Boundaries

- The 10,000 ms request deadline and all frozen candidates are unchanged.
- A fixed 2,000 ms per-unit timeout bounds failed RocketRide sends.
- Native and LangChain retain subprocess wall-clock measurement, including startup.
- Product correctness comes from clean merged-commit app verifier receipts.
- Candidate executors have no application mutation authority.
- Local promotion eligibility is not an official RocketRide result.
