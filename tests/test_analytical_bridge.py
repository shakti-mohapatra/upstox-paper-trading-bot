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


def test_write_params_entry_zone_is_not_degenerate():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "strategy_params.json")
        write_params("NSE_EQ|TEST", path=path)
        with open(path) as f:
            data = json.load(f)
        assert data["entry_zone"]["low"] < data["entry_zone"]["high"]
