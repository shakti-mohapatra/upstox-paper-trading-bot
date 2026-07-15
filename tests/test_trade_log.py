import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_log import log_fill

FIELDS = ["ts", "symbol", "strategy", "side", "qty", "intended", "fill", "gross", "cost", "net", "reason"]


def test_log_fill_writes_header_and_row_to_fresh_file(tmp_path):
    path = str(tmp_path / "trades.csv")

    log_fill(
        path,
        ts="2026-07-16T09:16:00+05:30",
        symbol="NSE_EQ|INE002A01018",
        strategy="orb",
        side="BUY",
        qty=10,
        intended=100.0,
        fill=100.05,
        gross=-1000.5,
        cost=0.66,
        net=-1001.16,
        reason="entry",
    )

    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows == [
        {
            "ts": "2026-07-16T09:16:00+05:30",
            "symbol": "NSE_EQ|INE002A01018",
            "strategy": "orb",
            "side": "BUY",
            "qty": "10",
            "intended": "100.0",
            "fill": "100.05",
            "gross": "-1000.5",
            "cost": "0.66",
            "net": "-1001.16",
            "reason": "entry",
        }
    ]


def test_log_fill_appends_without_rewriting_header(tmp_path):
    path = str(tmp_path / "trades.csv")
    row = dict(
        ts="2026-07-16T09:16:00+05:30",
        symbol="NSE_EQ|INE002A01018",
        strategy="orb",
        side="BUY",
        qty=10,
        intended=100.0,
        fill=100.05,
        gross=-1000.5,
        cost=0.66,
        net=-1001.16,
        reason="entry",
    )

    log_fill(path, **row)
    log_fill(path, **{**row, "side": "SELL", "reason": "target"})

    with open(path) as f:
        lines = f.readlines()

    assert lines[0].startswith("ts,")
    assert len(lines) == 3
