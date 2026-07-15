"""Study-only RocketRide node for deterministic unit completion and hard failure."""

import os
import sys
import time

from rocketlib import IInstanceBase


def object_name(obj):
    for key in ("name", "filename", "objname"):
        try:
            value = getattr(obj, key, None)
            if value:
                return str(value)
        except Exception:
            pass
        try:
            value = obj.get(key) if hasattr(obj, "get") else None
            if value:
                return str(value)
        except Exception:
            pass
    try:
        info = getattr(obj, "objinfo", None)
        if isinstance(info, dict) and info.get("name"):
            return str(info["name"])
    except Exception:
        pass
    return "unknown"


class IInstance(IInstanceBase):
    def open(self, obj):
        name = object_name(obj)
        time.sleep(0.02)
        if name.startswith("crash__"):
            sys.stderr.write("NODEWORKFLOW\tFAIL\t%s\tpid=%d\n" % (name, os.getpid()))
            sys.stderr.flush()
            os._exit(86)
        sys.stderr.write("NODEWORKFLOW\tOK\t%s\tpid=%d\n" % (name, os.getpid()))
        sys.stderr.flush()
