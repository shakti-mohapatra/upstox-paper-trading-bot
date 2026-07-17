import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytical_bridge import write_params


def test_write_params_creates_frozen_schema_atomically():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "strategy_params.json")
        write_params("NSE_EQ|TEST", path=path)
        with open(path) as f:
            data = json.load(f)
        assert data["version"] == 1
        assert data["instrument"] == "NSE_EQ|TEST"
        assert "target_pct" in data
        assert not os.path.exists(path + ".tmp")


def test_write_params_default_max_position_qty_is_not_degenerate():
    # qty=1 makes every trade fail the MIN_TURNOVER floor at any real NSE price - not a usable
    # default. This is a ceiling (position_sizing.size_position does the real risk-based capping),
    # so it just needs to be high enough to not bind in practice.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "strategy_params.json")
        write_params("NSE_EQ|TEST", path=path)
        with open(path) as f:
            data = json.load(f)
        assert data["max_position_qty"] >= 100


def test_write_params_entry_zone_is_not_degenerate():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "strategy_params.json")
        write_params("NSE_EQ|TEST", path=path)
        with open(path) as f:
            data = json.load(f)
        assert data["entry_zone"]["low"] < data["entry_zone"]["high"]


def test_write_params_preserves_manually_set_max_position_qty_on_restart():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "strategy_params.json")
        write_params("NSE_EQ|TEST", path=path)
        with open(path) as f:
            data = json.load(f)
        data["max_position_qty"] = 15  # simulates a manual fix applied between sessions
        with open(path, "w") as f:
            json.dump(data, f)

        write_params("NSE_EQ|TEST", path=path)  # e.g. a restart calling build_system() again

        with open(path) as f:
            data = json.load(f)
        assert data["max_position_qty"] == 15
