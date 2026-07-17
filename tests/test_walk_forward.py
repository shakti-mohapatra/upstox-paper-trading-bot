import csv
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import walk_forward


def test_param_grid_returns_cartesian_product_of_dicts():
    grid = walk_forward.param_grid({"target_pct": [0.5, 1.0], "stop_loss_pct": [0.3]})

    assert grid == [
        {"target_pct": 0.5, "stop_loss_pct": 0.3},
        {"target_pct": 1.0, "stop_loss_pct": 0.3},
    ]


def test_date_windows_rolls_train_test_pairs_forward_by_step():
    windows = walk_forward.date_windows(
        date(2022, 1, 1), date(2022, 12, 26), train_days=180, test_days=90, step_days=90
    )

    assert windows == [
        {
            "train_start": date(2022, 1, 1), "train_end": date(2022, 6, 29),
            "test_start": date(2022, 6, 30), "test_end": date(2022, 9, 27),
        },
        {
            "train_start": date(2022, 4, 1), "train_end": date(2022, 9, 27),
            "test_start": date(2022, 9, 28), "test_end": date(2022, 12, 26),
        },
    ]


def test_slice_candles_filters_by_inclusive_date_range():
    candles = [
        {"timestamp": "2026-01-15T09:16:00+05:30", "close": "1.0"},
        {"timestamp": "2026-01-16T09:16:00+05:30", "close": "2.0"},
        {"timestamp": "2026-01-17T15:29:00+05:30", "close": "3.0"},
        {"timestamp": "2026-01-18T09:16:00+05:30", "close": "4.0"},
    ]

    result = walk_forward.slice_candles(candles, date(2026, 1, 16), date(2026, 1, 17))

    assert [c["close"] for c in result] == ["2.0", "3.0"]


INSTRUMENT = "NSE_EQ|TEST"


def base_params():
    return {
        "version": 1,
        "instrument": INSTRUMENT,
        "enabled": True,
        "regime": "range",
        "entry_zone": {"low": 0.0, "high": 1_000_000.0},
        "target_pct": 1.0,
        "stop_loss_pct": 0.5,
        "trail_pct": 0.3,
        "max_position_qty": 100000,
    }


def test_evaluate_runs_backtest_on_candle_slice_and_returns_summary():
    candles = [
        {"timestamp": "2026-07-16T09:16:00+05:30", "open": "99.0", "high": "99.0", "low": "99.0", "close": "99.0", "volume": "0"},
        {"timestamp": "2026-07-16T09:31:00+05:30", "open": "100.0", "high": "100.0", "low": "100.0", "close": "100.0", "volume": "0"},
        {"timestamp": "2026-07-16T09:32:00+05:30", "open": "99.5", "high": "99.5", "low": "99.5", "close": "99.5", "volume": "0"},
    ]

    summary = walk_forward.evaluate(candles, base_params(), {}, INSTRUMENT)

    assert summary["num_trades"] == 1


def test_evaluate_runs_with_the_injected_strategy_class():
    from strategy import MACrossoverStrategy

    candles = [
        {"timestamp": "2026-07-16T09:16:00+05:30", "open": "99.0", "high": "99.0", "low": "99.0", "close": "99.0", "volume": "0"},
        {"timestamp": "2026-07-16T09:31:00+05:30", "open": "100.0", "high": "100.0", "low": "100.0", "close": "100.0", "volume": "0"},
        {"timestamp": "2026-07-16T09:32:00+05:30", "open": "99.5", "high": "99.5", "low": "99.5", "close": "99.5", "volume": "0"},
    ]

    summary = walk_forward.evaluate(candles, base_params(), {}, INSTRUMENT, strategy_cls=MACrossoverStrategy)

    assert summary["num_trades"] == 0  # MA crossover needs more ticks to establish a confirmed direction before it can cross


def test_main_wires_the_selected_strategy_class_into_evaluate(tmp_path, monkeypatch):
    from strategy import MACrossoverStrategy

    calls = {}

    def fake_load_candles(path):
        return [{"timestamp": "2026-01-01T09:16:00+05:30", "close": "100"}]

    def fake_run_walk_forward(candles, base_p, grid, windows, instrument, min_trades, evaluate_fn):
        calls["evaluate_fn"] = evaluate_fn
        return []

    monkeypatch.setattr(walk_forward, "load_candles", fake_load_candles)
    monkeypatch.setattr(walk_forward, "run_walk_forward", fake_run_walk_forward)

    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps(base_params()))

    walk_forward.main(["--data", "unused.csv", "--params", str(params_path), "--strategy", "ma_crossover"])

    assert calls["evaluate_fn"].keywords["strategy_cls"] is MACrossoverStrategy


def test_evaluate_returns_zero_summary_when_no_trades_occur():
    candles = [
        {"timestamp": "2026-07-16T09:16:00+05:30", "open": "99.0", "high": "99.0", "low": "99.0", "close": "99.0", "volume": "0"},
    ]
    params = base_params()
    params["enabled"] = False

    summary = walk_forward.evaluate(candles, params, {}, INSTRUMENT)

    assert summary == walk_forward.ZERO_SUMMARY


def test_run_walk_forward_picks_best_train_combo_and_scores_it_on_test():
    windows = [{"train_start": date(2022, 1, 1), "train_end": date(2022, 1, 2), "test_start": date(2022, 1, 3), "test_end": date(2022, 1, 4)}]
    grid = [{"target_pct": 0.5}, {"target_pct": 1.0}]
    calls = []

    def fake_evaluate(candles, base_params, overrides, instrument):
        calls.append(overrides)
        net_pnl = 10.0 if overrides["target_pct"] == 0.5 else 3.0
        return {"num_trades": 5, "net_pnl": net_pnl, "cost_pct": 0.1, "win_rate": 0.5, "max_drawdown": 1.0}

    results = walk_forward.run_walk_forward([], {}, grid, windows, INSTRUMENT, min_trades=3, evaluate_fn=fake_evaluate)

    assert results[0]["chosen_params"] == {"target_pct": 0.5}
    assert results[0]["train_summary"]["net_pnl"] == 10.0
    assert results[0]["test_summary"]["net_pnl"] == 10.0
    assert calls[-1] == {"target_pct": 0.5}


def test_run_walk_forward_marks_window_with_no_eligible_combo():
    windows = [{"train_start": date(2022, 1, 1), "train_end": date(2022, 1, 2), "test_start": date(2022, 1, 3), "test_end": date(2022, 1, 4)}]
    grid = [{"target_pct": 0.5}]

    def fake_evaluate(candles, base_params, overrides, instrument):
        return {"num_trades": 1, "net_pnl": 10.0, "cost_pct": 0.1, "win_rate": 1.0, "max_drawdown": 0.0}

    results = walk_forward.run_walk_forward([], {}, grid, windows, INSTRUMENT, min_trades=3, evaluate_fn=fake_evaluate)

    assert results[0]["chosen_params"] is None
    assert results[0]["test_summary"] is None


def test_main_runs_search_and_holdout_from_cli_args(tmp_path):
    data_path = str(tmp_path / "candles.csv")
    rows = []
    for day in ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]:
        rows += [
            {"timestamp": f"{day}T09:16:00+05:30", "open": "99.0", "high": "99.0", "low": "99.0", "close": "99.0", "volume": "0"},
            {"timestamp": f"{day}T09:31:00+05:30", "open": "100.0", "high": "100.0", "low": "100.0", "close": "100.0", "volume": "0"},
            {"timestamp": f"{day}T09:32:00+05:30", "open": "99.5", "high": "99.5", "low": "99.5", "close": "99.5", "volume": "0"},
        ]
    with open(data_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)

    params_path = str(tmp_path / "params.json")
    with open(params_path, "w") as f:
        json.dump(base_params(), f)

    result = walk_forward.main([
        "--data", data_path, "--params", params_path,
        "--holdout-days", "1", "--train-days", "1", "--test-days", "1", "--step-days", "1", "--min-trades", "1",
    ])

    assert len(result["windows"]) == 2
    assert result["holdout"] is not None
    assert result["holdout"]["num_trades"] == 1
