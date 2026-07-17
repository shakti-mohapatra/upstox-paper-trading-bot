"""Phase 2 search: sweep ORB params across rolling train/test windows, gated
by a minimum-trades threshold, with a final untouched out-of-sample holdout.

Params are never "fit" by an optimizer here (ORB has no gradient/loss to fit)
- per window, each grid candidate is backtested on the train slice and the
best-by-net-pnl candidate that clears MIN_TRADES is carried forward to the
test slice. That test-slice result is the walk-forward estimate of how a
freshly-"chosen" config performs on data it didn't pick itself on.
"""
import argparse
import functools
import itertools
import json
import os
import tempfile
from collections import Counter
from datetime import date, timedelta

from backtest import STRATEGIES, load_candles, run_backtest_on_candles, summarize
from strategy import ORBStrategy


def param_grid(grid: dict) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]


def date_windows(from_date: date, to_date: date, train_days: int, test_days: int, step_days: int) -> list[dict]:
    windows = []
    train_start = from_date
    while True:
        train_end = train_start + timedelta(days=train_days - 1)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days - 1)
        if test_end > to_date:
            break
        windows.append({"train_start": train_start, "train_end": train_end, "test_start": test_start, "test_end": test_end})
        train_start += timedelta(days=step_days)
    return windows


def slice_candles(candles: list[dict], start: date, end: date) -> list[dict]:
    start_iso, end_iso = start.isoformat(), end.isoformat()
    return [c for c in candles if start_iso <= c["timestamp"][:10] <= end_iso]


ZERO_SUMMARY = {"num_trades": 0, "net_pnl": 0.0, "cost_pct": 0.0, "win_rate": 0.0, "max_drawdown": 0.0}


def evaluate(candles: list[dict], base_params: dict, overrides: dict, instrument: str, strategy_cls=ORBStrategy) -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        params_path = os.path.join(tmp_dir, "params.json")
        trade_log_path = os.path.join(tmp_dir, "trades.csv")
        with open(params_path, "w") as f:
            json.dump({**base_params, **overrides}, f)
        run_backtest_on_candles(candles, params_path, trade_log_path, instrument, strategy=strategy_cls())
        if not os.path.exists(trade_log_path):
            return dict(ZERO_SUMMARY)
        return summarize(trade_log_path)


def run_walk_forward(candles: list[dict], base_params: dict, grid: list[dict], windows: list[dict], instrument: str, min_trades: int, evaluate_fn) -> list[dict]:
    results = []
    for window in windows:
        train_candles = slice_candles(candles, window["train_start"], window["train_end"])
        best = None
        for overrides in grid:
            summary = evaluate_fn(train_candles, base_params, overrides, instrument)
            if summary["num_trades"] < min_trades:
                continue
            if best is None or summary["net_pnl"] > best["summary"]["net_pnl"]:
                best = {"params": overrides, "summary": summary}

        if best is None:
            results.append({**window, "chosen_params": None, "train_summary": None, "test_summary": None})
            continue

        test_candles = slice_candles(candles, window["test_start"], window["test_end"])
        test_summary = evaluate_fn(test_candles, base_params, best["params"], instrument)
        results.append({**window, "chosen_params": best["params"], "train_summary": best["summary"], "test_summary": test_summary})
    return results


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="Phase 2: walk-forward ORB param search with an untouched OOS holdout.")
    parser.add_argument("--data", required=True)
    parser.add_argument("--params", default="strategy_params.json", help="base params file; target/stop/trail get overridden by the grid")
    parser.add_argument("--instrument", default=None)
    parser.add_argument("--holdout-days", type=int, default=90)
    parser.add_argument("--train-days", type=int, default=365)
    parser.add_argument("--test-days", type=int, default=90)
    parser.add_argument("--step-days", type=int, default=90)
    parser.add_argument("--min-trades", type=int, default=10)
    parser.add_argument("--strategy", default="orb", choices=sorted(STRATEGIES))
    args = parser.parse_args(argv)

    with open(args.params) as f:
        base_params = json.load(f)
    instrument = args.instrument or base_params["instrument"]

    candles = load_candles(args.data)
    timestamps = [c["timestamp"][:10] for c in candles]
    from_date = date.fromisoformat(min(timestamps))
    to_date_all = date.fromisoformat(max(timestamps))
    holdout_start = to_date_all - timedelta(days=args.holdout_days - 1)
    search_end = holdout_start - timedelta(days=1)

    grid = param_grid({
        "target_pct": [0.5, 1.0, 1.5],
        "stop_loss_pct": [0.3, 0.5],
        "trail_pct": [0.2, 0.3],
    })
    windows = date_windows(from_date, search_end, args.train_days, args.test_days, args.step_days)

    evaluate_fn = functools.partial(evaluate, strategy_cls=STRATEGIES[args.strategy])
    results = run_walk_forward(candles, base_params, grid, windows, instrument, args.min_trades, evaluate_fn)

    print(f"{len(windows)} walk-forward windows, {len(grid)} param combos, min_trades={args.min_trades}")
    for r in results:
        chosen, test = r["chosen_params"], r["test_summary"]
        if chosen is None:
            print(f"  {r['test_start']}..{r['test_end']}: no combo cleared min_trades on train")
        else:
            print(f"  {r['test_start']}..{r['test_end']}: chosen={chosen} test_trades={test['num_trades']} test_net_pnl={test['net_pnl']:.2f} test_win_rate={test['win_rate']:.2f}")

    survivors = [r for r in results if r["chosen_params"] is not None]
    if not survivors:
        print("No window produced an eligible combo - nothing to holdout-test.")
        return {"windows": results, "winner_params": None, "holdout": None}

    winner_counts = Counter(tuple(sorted(r["chosen_params"].items())) for r in survivors)
    winner_params = dict(winner_counts.most_common(1)[0][0])

    holdout_candles = slice_candles(candles, holdout_start, to_date_all)
    holdout_summary = evaluate_fn(holdout_candles, base_params, winner_params, instrument)

    print(f"\nMost-selected combo across windows: {winner_params}")
    print(f"Holdout ({holdout_start}..{to_date_all}, never touched during search):")
    print(json.dumps(holdout_summary, indent=2))

    return {"windows": results, "winner_params": winner_params, "holdout": holdout_summary}


if __name__ == "__main__":
    main()
