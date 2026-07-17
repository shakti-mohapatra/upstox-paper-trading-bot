"""Writes strategy_params.json.

Stub now (static placeholder values). Same frozen schema gets filled by a
Python rule (Phase 3), then Ollama later - execution_engine never changes.
"""
import json
import os
import tempfile
from datetime import datetime, timezone

SCHEMA_VERSION = 1


def write_params(instrument: str, path: str = "strategy_params.json") -> None:
    max_position_qty = 1000  # safety ceiling, not the sizer - position_sizing.size_position does the real risk-based cap
    if os.path.exists(path):
        try:
            with open(path) as f:
                max_position_qty = json.load(f).get("max_position_qty", max_position_qty)
        except (OSError, json.JSONDecodeError):
            pass  # no valid prior file to preserve from - fall back to the stub default

    params = {
        "version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "instrument": instrument,
        "enabled": True,
        "regime": "range",
        "entry_zone": {"low": 0.0, "high": 1_000_000.0},  # stub: wide-open, no live signal yet
        "target_pct": 1.0,
        "stop_loss_pct": 0.5,
        "trail_pct": 0.3,
        "max_position_qty": max_position_qty,  # preserved across restarts, not reset to the stub every boot
        "notes": "stub: static placeholder params, no live signal yet",
    }
    dir_ = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(params, f, indent=2)
    os.replace(tmp_path, path)  # atomic swap, engine never reads a half-written file
