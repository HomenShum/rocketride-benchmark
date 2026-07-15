# RocketRide Cloud Appendix

This directory contains a separately pre-registered hosted operational study.
It is not a substitute for the unchanged local benchmark and does not carry an
official RocketRide score.

The measured runner and auditor were added after the pre-registration commit.
Credentials are loaded from an external environment file and must never be
placed under this repository. The SDK client is constructed with `env={}` so it
cannot forward the process credential into a hosted pipeline environment.

Expected execution shape:

```powershell
$env:ROCKETRIDE_ENV_FILE = 'C:\path\outside\the\repo\rocketride.env'
concurrent-work/harness/rocketride-bench/.venv/Scripts/python.exe benchmark-evidence/cloud/test_cloud_appendix.py
concurrent-work/harness/rocketride-bench/.venv/Scripts/python.exe benchmark-evidence/cloud/run_cloud_appendix.py
concurrent-work/harness/rocketride-bench/.venv/Scripts/python.exe benchmark-evidence/cloud/audit_cloud_appendix.py benchmark-evidence/cloud/runs/<run-id>
```

See `PRE_REGISTRATION.md` for the frozen protocol and
`SETUP_ATTEMPTS.md` for excluded setup probes.
