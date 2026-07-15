# RocketRide Cloud Appendix

This directory contains a separately pre-registered hosted operational study.
It is not a substitute for the unchanged local benchmark and does not carry an
official RocketRide score.

The measured runner and auditor are added after the pre-registration commit.
Credentials are loaded from an external environment file and must never be
placed under this repository.

Expected execution shape:

```powershell
$env:ROCKETRIDE_ENV_FILE = 'C:\path\outside\the\repo\rocketride.env'
python benchmark-evidence/cloud/run_cloud_appendix.py
python benchmark-evidence/cloud/audit_cloud_appendix.py benchmark-evidence/cloud/runs/<run-id>
```

See `PRE_REGISTRATION.md` for the frozen protocol and
`SETUP_ATTEMPTS.md` for excluded setup probes.
