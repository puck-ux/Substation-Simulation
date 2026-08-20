"""
Shared target configuration for the substation attack scripts.

All attacks import from here instead of hardcoding IPs/MACs, so you only
edit one file (targets.env) when the DHCP addresses drift.

Usage in an attack script — add this near the top:

    from config import VM1_IP, VM1_MAC, VM2_IP, VM2_MAC, IFACE

Then use those variables instead of hardcoded values. If a value is
missing from targets.env the script exits with a clear message rather
than running against the wrong target.
"""

import os
import sys

# ------------------------------------------------------------------
# Locate and load targets.env from the same folder as this file,
# regardless of where the attack script is run from.
# ------------------------------------------------------------------
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "targets.env")

def _load_env(path):
    values = {}
    if not os.path.exists(path):
        print(f"[!] {os.path.basename(path)} not found.")
        print(f"    Copy the template and fill it in:")
        print(f"        cp targets.env.example targets.env")
        sys.exit(1)
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip()
    return values

_cfg = _load_env(_ENV_PATH)

def _require(key):
    val = _cfg.get(key)
    if not val:
        print(f"[!] {key} is not set in targets.env — fill it in before running.")
        sys.exit(1)
    return val

# ------------------------------------------------------------------
# Exported values — import these in the attack scripts
# ------------------------------------------------------------------
VM1_IP  = _require("VM1_IP")
VM1_MAC = _require("VM1_MAC")
VM2_IP  = _require("VM2_IP")
VM2_MAC = _require("VM2_MAC")
IFACE   = _require("IFACE")

# Convenience: the OpenPLC IP is VM1 (used by Modbus-targeting scripts)
OPENPLC_IP = VM1_IP
