#!/usr/bin/env python3
"""Wait for any HTTP response without changing the upstream readiness script."""

from __future__ import annotations

import argparse
import time
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    started = time.monotonic()
    attempt = 0
    last_error = "no attempt"
    while time.monotonic() - started < args.timeout:
        attempt += 1
        try:
            with urllib.request.urlopen(args.url, timeout=2) as response:
                print(f"ready status={response.status} attempts={attempt}")
                return 0
        except urllib.error.HTTPError as error:
            print(f"ready status={error.code} attempts={attempt}")
            return 0
        except Exception as error:  # connection refusal and bootstrap timeouts are expected here
            last_error = f"{type(error).__name__}: {error}"
            if attempt == 1 or attempt % 10 == 0:
                print(f"waiting attempt={attempt} error={last_error}", flush=True)
            time.sleep(1)

    print(f"timeout seconds={args.timeout} last_error={last_error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
