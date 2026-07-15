# Limitations

- The independent host is Windows x64; upstream committed results were produced on
  Apple Silicon. Correctness outcomes can be compared directly, while timing and
  loss magnitude remain hardware-dependent.
- RocketRide Cloud is not part of the pinned local baseline.
- Deterministic application fixtures test orchestration and isolation; they do not
  predict live-model quality.
- Node application guarantees supplied by artifact validation, CAS, proposals, or
  human review are reported as application guarantees, not framework guarantees.
