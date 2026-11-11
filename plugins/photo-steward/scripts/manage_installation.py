#!/usr/bin/env python3
"""Portable installation entry point, also included in the OPL Package."""
import importlib.util
from pathlib import Path
import sys

implementation = Path(__file__).resolve().parents[1] / "tools/icloud_photo_sync/installation.py"
spec = importlib.util.spec_from_file_location("photo_steward_installation", implementation)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if __name__ == "__main__":
    raise SystemExit(module.main(sys.argv[1:]))
