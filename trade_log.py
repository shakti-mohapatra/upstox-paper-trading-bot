"""CSV trade log - one row per fill, shared format for backtest and paper."""
import csv
import os

FIELDS = ["ts", "symbol", "strategy", "side", "qty", "intended", "fill", "gross", "cost", "net", "reason"]


def log_fill(path: str, **row) -> None:
    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
