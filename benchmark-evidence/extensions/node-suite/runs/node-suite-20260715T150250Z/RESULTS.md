# Node Application Runtime Study

Gate status: **passed**. External status: **separate_application_study_unsubmitted**.

All scored work is deterministic and local. Model calls, model cost, and cloud cost are zero.
Candidates are never committed by these executors; app-owned validation, CAS, proposals, and review remain authoritative.

| App | Variant | Framework | Completed units median | Failed units median | Total p50 ms | Total p95 ms | Warm-up p50 ms |
|---|---|---|---:|---:|---:|---:|---:|
| nodebenchai | normal | native | 4.0 | 0.0 | 203.795 | 209.231 | 0.0 |
| nodebenchai | normal | rocketride | 4.0 | 0.0 | 27890.281 | 28829.475 | 18096.814 |
| nodebenchai | normal | langchain | 4.0 | 0.0 | 1300.084 | 1339.62 | 0.0 |
| nodebenchai | hard-failure | native | 3.0 | 1.0 | 194.193 | 201.38 | 0.0 |
| nodebenchai | hard-failure | rocketride | 3.0 | 1.0 | 33572.497 | 35197.145 | 20015.996 |
| nodebenchai | hard-failure | langchain | 0.0 | 4.0 | 1139.453 | 1152.603 | 0.0 |
| noderoom | normal | native | 4.0 | 0.0 | 196.81 | 200.27 | 0.0 |
| noderoom | normal | rocketride | 4.0 | 0.0 | 25966.952 | 31353.016 | 18205.906 |
| noderoom | normal | langchain | 4.0 | 0.0 | 1278.346 | 1402.813 | 0.0 |
| noderoom | hard-failure | native | 3.0 | 1.0 | 202.053 | 227.869 | 0.0 |
| noderoom | hard-failure | rocketride | 3.0 | 1.0 | 31934.275 | 34343.774 | 18043.553 |
| noderoom | hard-failure | langchain | 0.0 | 4.0 | 1066.724 | 1102.285 | 0.0 |
| noderoom | normal | native | 4.0 | 0.0 | 190.836 | 197.205 | 0.0 |
| noderoom | normal | rocketride | 4.0 | 0.0 | 29586.421 | 31716.471 | 20191.251 |
| noderoom | normal | langchain | 4.0 | 0.0 | 1353.289 | 1395.582 | 0.0 |
| noderoom | hard-failure | native | 3.0 | 1.0 | 176.464 | 229.921 | 0.0 |
| noderoom | hard-failure | rocketride | 3.0 | 1.0 | 37909.386 | 38717.674 | 22938.415 |
| noderoom | hard-failure | langchain | 0.0 | 4.0 | 1057.141 | 1275.969 | 0.0 |
| nodeslide | normal | native | 4.0 | 0.0 | 200.23 | 215.663 | 0.0 |
| nodeslide | normal | rocketride | 4.0 | 0.0 | 31814.868 | 32349.741 | 21170.067 |
| nodeslide | normal | langchain | 4.0 | 0.0 | 1390.712 | 1397.297 | 0.0 |
| nodeslide | hard-failure | native | 3.0 | 1.0 | 222.259 | 225.162 | 0.0 |
| nodeslide | hard-failure | rocketride | 3.0 | 1.0 | 34287.676 | 35839.943 | 20002.825 |
| nodeslide | hard-failure | langchain | 0.0 | 4.0 | 1135.858 | 1207.565 | 0.0 |
| nodevideo | normal | native | 4.0 | 0.0 | 203.875 | 215.058 | 0.0 |
| nodevideo | normal | rocketride | 4.0 | 0.0 | 26099.987 | 27879.021 | 18688.817 |
| nodevideo | normal | langchain | 4.0 | 0.0 | 1220.388 | 1351.645 | 0.0 |
| nodevideo | hard-failure | native | 3.0 | 1.0 | 200.311 | 201.472 | 0.0 |
| nodevideo | hard-failure | rocketride | 3.0 | 1.0 | 32593.96 | 36694.823 | 18276.309 |
| nodevideo | hard-failure | langchain | 0.0 | 4.0 | 1067.634 | 1086.447 | 0.0 |

## Authoring Surface

| Surface | Physical lines | Non-blank lines | Bytes |
|---|---:|---:|---:|
| sharedHarness | 873 | 790 | 32993 |
| native | 80 | 76 | 2378 |
| rocketride | 42 | 36 | 1171 |
| langchain | 71 | 62 | 2220 |

Physical and non-blank lines are descriptive, not semantic complexity scores.

## Interpretation Boundaries

- Native is the additive Node worker-thread control in this study, not a claim about every production deployment topology.
- RocketRide is the pinned local engine with one resident pipe process per work unit.
- LangChain is real langchain-core RunnableLambda.abatch in one Python interpreter.
- Hard-failure rows measure unaffected work completion; they are expected to reject the candidate envelope.
- Product correctness credit belongs to the application verifier receipts, not the executor.
