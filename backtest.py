"""Replay harness (SONNET_BUILD_PLAN.md Phase 1): feeds historical candles
through the same ExecutionEngine used for live/paper trading, via a CSV of
candles instead of a live socket. Runs a strategy over months of history in
seconds.
"""
import argparse
import csv
import json
import os

from broker.paper import PaperBroker
from execution_engine import ExecutionEngine
from strategy import MACrossoverStrategy, ORBStrategy, ORBv2Strategy

STRATEGIES = {"orb": ORBStrategy, "ma_crossover": MACrossoverStrategy, "orb_v2": ORBv2Strategy}


def load_candles(path: str) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def candle_to_tick(candle: dict, instrument: str) -> dict:
    return {"instrument": instrument, "ltp": float(candle["close"]), "ts": candle["timestamp"]}


def run_backtest(data_path, params_path, trade_log_path, instrument, strategy=None, daily_max_loss=None):
    if os.path.exists(trade_log_path):
        os.remove(trade_log_path)  # re-runs must not append to a stale log

    engine = ExecutionEngine(
        PaperBroker(),
        params_path=params_path,
        daily_max_loss=daily_max_loss,
        trade_log_path=trade_log_path,
        strategy=strategy,
    )
    engine.load_params()

    for candle in load_candles(data_path):
        engine.on_tick(candle_to_tick(candle, instrument))


def run_backtest_on_candles(candles, params_path, trade_log_path, instrument, strategy=None, daily_max_loss=None):
    if os.path.exists(trade_log_path):
        os.remove(trade_log_path)

    engine = ExecutionEngine(
        PaperBroker(),
        params_path=params_path,
        daily_max_loss=daily_max_loss,
        trade_log_path=trade_log_path,
        strategy=strategy,
    )
    engine.load_params()

    for candle in candles:
        engine.on_tick(candle_to_tick(candle, instrument))


def summarize(trade_log_path: str) -> dict:
    with open(trade_log_path, newline="") as f:
        rows = list(csv.DictReader(f))

    total_cost = sum(float(r["cost"]) for r in rows)
    total_notional = sum(float(r["fill"]) * float(r["qty"]) for r in rows)
    net_pnl = sum(float(r["net"]) for r in rows)

    trade_nets = []
    running = 0.0
    for r in rows:
        if r["reason"] == "entry":
            running = float(r["net"])
        else:
            running += float(r["net"])
            trade_nets.append(running)

    num_trades = len(trade_nets)
    win_rate = (sum(1 for n in trade_nets if n > 0) / num_trades) if num_trades else 0.0
    cost_pct = (total_cost / total_notional * 100) if total_notional else 0.0

    cum = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for r in rows:
        cum += float(r["net"])
        peak = max(peak, cum)
        max_drawdown = max(max_drawdown, peak - cum)

    return {
        "num_trades": num_trades,
        "net_pnl": net_pnl,
        "cost_pct": cost_pct,
        "win_rate": win_rate,
        "max_drawdown": max_drawdown,
    }


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="Replay historical candles through the paper-trading engine.")
    parser.add_argument("--strategy", default="orb", choices=sorted(STRATEGIES))
    parser.add_argument("--data", required=True, help="CSV of timestamp,open,high,low,close,volume candles")
    parser.add_argument("--params", default="strategy_params.json")
    parser.add_argument("--trade-log", default="logs/backtest_trades.csv")
    parser.add_argument("--instrument", default=None, help="defaults to the instrument in --params")
    args = parser.parse_args(argv)

    with open(args.params) as f:
        instrument = args.instrument or json.load(f)["instrument"]

    run_backtest(args.data, args.params, args.trade_log, instrument, strategy=STRATEGIES[args.strategy]())
    summary = summarize(args.trade_log)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
