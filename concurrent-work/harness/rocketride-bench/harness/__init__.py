"""rocketride-bench harness — the shared measurement library.

This package only *drives* and *measures* the genuine RocketRide product (engine + EAAS
server + SDK + tracer). It never reimplements engine behavior. See the repo README and
NOTICE for the "what's RocketRide vs what's ours" breakdown.
"""
# Force UTF-8 on stdout/stderr so the runners' unicode (→, ×, …) prints on any console.
# Windows defaults to a legacy codepage (cp1252), where a bare `print("… → …")` raises
# UnicodeEncodeError and aborts a run mid-benchmark. Guarded + idempotent; no-op on POSIX,
# which is already UTF-8. reconfigure() exists on TextIOWrapper (Py3.7+).
import sys as _sys

for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
