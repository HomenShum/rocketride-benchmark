# Node Application Runtime Study

This is Track B of the RocketRide study. It is intentionally separate from the
unchanged upstream reproduction in `benchmark-evidence/baseline/`.

## Boundary

Native, RocketRide, and LangChain executors receive the same versioned request and
return the same candidate schema. They never receive an application mutation port.
Each application branch validates the candidate with its existing domain rules;
the normal application validation, CAS, proposal, and review path retains final
write authority.

The deterministic matrix uses:

- a Node worker-thread native control;
- RocketRide 1.2.0 with pinned local engine 3.2.1.30, one resident pipe process per unit;
- real `langchain-core==0.3.86` `RunnableLambda.abatch` in one Python interpreter.

No LLM or paid provider is called. Model and cloud costs are zero.

## Run

Provision the unchanged upstream environment first. Commit the four application
adapter branches after their repository gates pass, then create the app-verifier
receipts from those clean commits:

```powershell
python benchmark-evidence/extensions/node-suite/common/run_app_verifiers.py `
  --apps-root ..\rocketride-node-apps `
  --evidence-bundle benchmark-evidence/evidence-bundle.json
```

Only after `app-verification.json` reports `passed`, run the scored matrix from
the repository root:

```powershell
python benchmark-evidence/extensions/node-suite/common/run_suite.py --repetitions 3
```

The runner uses port 5567, installs the study-only node into the downloaded local
engine bundle, validates the generated pipe, runs normal and pre-registered hard
failure variants, stops its engine process tree, and writes immutable run evidence
under `benchmark-evidence/extensions/node-suite/runs/`.

Audit the completed run before interpreting or promoting it:

```powershell
python benchmark-evidence/extensions/node-suite/common/audit_run.py `
  benchmark-evidence/extensions/node-suite/runs/<run-id> --write-receipt
python benchmark-evidence/extensions/node-suite/common/audit_run.py `
  benchmark-evidence/extensions/node-suite/runs/<run-id>
```

The runner gate checks completion, isolation, digest parity, app receipts, and the
fixed fixture deadline. The independent audit revalidates all request/result
bindings, provenance, deadlines, trace counts, source snapshots, and manifest
hashes without replacing the original scorecard. Use `--require-promotion-ready`
when a nonzero exit is required unless every promotion condition passes.

Re-run the matrix with the same fixtures only when the pre-registered rerun policy
allows it. Do not replace unfavorable results.

## Interpretation

The native control is additive benchmark code, not a claim about every production
deployment topology. The deterministic fixture matrix measures frozen-candidate
binding, isolation, and orchestration overhead. Its executors do not generate the
fixture candidate, so digest parity is not a model-quality or candidate-generation
result. Application correctness comes only from the app verifier receipts. Cloud
and live-provider work, if run later, belongs in an operational appendix and cannot
replace this local score.
