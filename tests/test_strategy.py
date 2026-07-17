import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import MACrossoverStrategy, ORBStrategy, ORBv2Strategy, Strategy


def tick(ltp, ts=None):
    t = {"ltp": ltp}
    if ts is not None:
        t["ts"] = f"2026-07-16T{ts}+05:30"
    return t


def test_orb_strategy_is_a_strategy():
    assert isinstance(ORBStrategy(), Strategy)


def candle(ts_time, high):
    return {"timestamp": f"2026-07-16T{ts_time}+05:30", "high": high}


def test_orb_high_from_candles_takes_max_high_inside_window():
    from strategy import orb_high_from_candles

    candles = [
        candle("09:14:00", 200.0),  # before window, ignored
        candle("09:16:00", 99.0),
        candle("09:20:00", 101.5),
        candle("09:29:00", 100.0),
        candle("09:30:00", 300.0),  # window end exclusive, ignored
    ]

    assert orb_high_from_candles(candles) == 101.5


def test_orb_high_from_candles_returns_none_when_no_candles_in_window():
    from strategy import orb_high_from_candles

    assert orb_high_from_candles([candle("09:31:00", 100.0)]) is None


def test_signal_holds_during_orb_window_and_records_high():
    strat = ORBStrategy()

    result = strat.signal(tick(99.0, "09:16:00"), {}, None)

    assert result == {"action": "hold"}
    assert strat.orb_high == 99.0


def test_signal_enters_when_no_timestamp_and_price_inside_entry_zone():
    strat = ORBStrategy()
    params = {"entry_zone": {"low": 0.0, "high": 1_000_000.0}}

    result = strat.signal(tick(100.5), params, None)

    assert result == {"action": "enter"}


def test_signal_holds_after_window_until_price_breaks_above_orb_high():
    strat = ORBStrategy()
    params = {"entry_zone": {"low": 0.0, "high": 1_000_000.0}}
    strat.signal(tick(99.0, "09:16:00"), params, None)
    strat.signal(tick(100.0, "09:25:00"), params, None)  # orb_high now 100.0

    at_high = strat.signal(tick(100.0, "09:31:00"), params, None)
    breakout = strat.signal(tick(100.5, "09:32:00"), params, None)

    assert at_high == {"action": "hold"}
    assert breakout == {"action": "enter"}


def test_signal_exits_at_target_when_in_position():
    strat = ORBStrategy()
    params = {"target_pct": 1.0, "stop_loss_pct": 0.5, "trail_pct": 0.3}
    position = {"entry_price": 100.0, "high_water": 100.0}

    result = strat.signal(tick(101.0), params, position)

    assert result == {"action": "exit", "reason": "target"}


def test_signal_exits_at_hard_stop_when_in_position():
    strat = ORBStrategy()
    params = {"target_pct": 1.0, "stop_loss_pct": 0.5, "trail_pct": 0.3}
    position = {"entry_price": 100.0, "high_water": 100.0}

    result = strat.signal(tick(99.5), params, position)

    assert result == {"action": "exit", "reason": "stop_loss"}


def test_signal_exits_at_trailing_stop_below_hard_stop_level():
    strat = ORBStrategy()
    params = {"target_pct": 1.0, "stop_loss_pct": 0.5, "trail_pct": 0.3}
    position = {"entry_price": 100.0, "high_water": 100.8}  # trail stop = 100.4976

    result = strat.signal(tick(100.4), params, position)

    assert result == {"action": "exit", "reason": "trailing_stop"}


def test_ma_crossover_strategy_is_a_strategy():
    assert isinstance(MACrossoverStrategy(), Strategy)


def test_ma_crossover_enters_on_bullish_cross():
    strat = MACrossoverStrategy(fast_period=2, slow_period=4)
    strat.signal(tick(100.0), {}, None)
    strat.signal(tick(90.0), {}, None)  # fast EMA drops below slow -> bearish baseline established

    result = strat.signal(tick(130.0), {}, None)  # fast EMA jumps back above slow -> bullish cross

    assert result == {"action": "enter"}


def test_ma_crossover_exits_on_bearish_cross_while_in_position():
    strat = MACrossoverStrategy(fast_period=2, slow_period=4)
    params = {"target_pct": 50.0, "stop_loss_pct": 50.0, "trail_pct": 50.0}  # wide enough to isolate the cross logic
    position = {"entry_price": 130.0, "high_water": 130.0}
    strat.signal(tick(100.0), params, None)
    strat.signal(tick(90.0), params, None)
    strat.signal(tick(130.0), params, None)  # establishes bullish state (as if this tick triggered entry)

    result = strat.signal(tick(95.0), params, position)  # fast EMA crosses back below slow

    assert result == {"action": "exit", "reason": "bearish_cross"}


def test_ma_crossover_still_exits_at_target_pct_when_in_position():
    strat = MACrossoverStrategy()
    params = {"target_pct": 1.0, "stop_loss_pct": 0.5, "trail_pct": 0.3}
    position = {"entry_price": 100.0, "high_water": 100.0}

    result = strat.signal(tick(101.0), params, position)

    assert result == {"action": "exit", "reason": "target"}


def test_ma_crossover_holds_before_a_direction_is_established():
    strat = MACrossoverStrategy()

    result = strat.signal(tick(100.0), {}, None)

    assert result == {"action": "hold"}


def test_orb_v2_strategy_is_a_strategy():
    assert isinstance(ORBv2Strategy(), Strategy)


def test_orb_v2_holds_and_accumulates_range_during_window():
    strat = ORBv2Strategy()

    result = strat.signal(tick(100.0, "09:16:00"), {}, None)

    assert result == {"action": "hold"}
    assert strat.range_high == 100.0
    assert strat.range_low == 100.0


def test_orb_v2_no_entry_when_no_prior_day_close_to_measure_gap():
    strat = ORBv2Strategy()
    strat.signal(tick(100.0, "09:16:00"), {}, None)
    strat.signal(tick(102.0, "09:29:00"), {}, None)

    result = strat.signal(tick(200.0, "09:35:00"), {}, None)

    assert result == {"action": "hold"}


def _seed_gap_ok_orb_v2(day1_close=100.0):
    """Runs one full day (window + a post-window hold) so day 2 has a prior
    close to measure a gap against, then rolls to day 2."""
    strat = ORBv2Strategy()
    strat.signal(tick(day1_close, "09:16:00"), {}, None)
    strat.signal(tick(day1_close, "09:35:00"), {}, None)
    strat.new_day()
    return strat


def test_orb_v2_skips_entry_when_gap_outside_filter_band():
    strat = _seed_gap_ok_orb_v2(day1_close=100.0)
    strat.signal(tick(100.05, "09:16:00"), {}, None)
    strat.signal(tick(102.0, "09:29:00"), {}, None)

    result = strat.signal(tick(200.0, "09:35:00"), {}, None)

    assert result == {"action": "hold"}


def test_orb_v2_skips_entry_when_range_too_tight():
    strat = _seed_gap_ok_orb_v2(day1_close=100.0)
    strat.signal(tick(101.0, "09:16:00"), {}, None)
    strat.signal(tick(101.1, "09:29:00"), {}, None)

    result = strat.signal(tick(200.0, "09:35:00"), {}, None)

    assert result == {"action": "hold"}


def test_orb_v2_enters_on_breakout_above_range_high_plus_confirmation():
    strat = _seed_gap_ok_orb_v2(day1_close=100.0)
    strat.signal(tick(101.0, "09:16:00"), {}, None)
    strat.signal(tick(102.0, "09:29:00"), {}, None)
    strat.signal(tick(101.5, "09:31:00"), {}, None)

    result = strat.signal(tick(102.2, "09:32:00"), {}, None)

    assert result["action"] == "enter"
    assert result["stop_loss_pct"] == pytest.approx((102.2 - 101.0) / 102.2 * 100)


def test_orb_v2_no_new_entries_after_max_hold_cutoff():
    strat = _seed_gap_ok_orb_v2(day1_close=100.0)
    strat.signal(tick(101.0, "09:16:00"), {}, None)
    strat.signal(tick(102.0, "09:29:00"), {}, None)

    result = strat.signal(tick(200.0, "11:05:00"), {}, None)

    assert result == {"action": "hold"}


def test_orb_v2_enters_short_on_breakdown_below_range_low():
    strat = _seed_gap_ok_orb_v2(day1_close=100.0)
    strat.signal(tick(99.0, "09:16:00"), {}, None)  # 1% gap down, passes gap filter
    strat.signal(tick(98.0, "09:29:00"), {}, None)  # range 98.0-99.0, ~1% width, passes range floor

    result = strat.signal(tick(97.8, "09:32:00"), {}, None)  # < 98.0*0.9995

    assert result["action"] == "enter"
    assert result["side"] == "short"
    assert result["stop_loss_pct"] == pytest.approx((99.0 - 97.8) / 97.8 * 100)


def test_orb_v2_short_position_exits_at_range_derived_target_when_price_falls():
    strat = ORBv2Strategy()
    strat._entry_side = "short"
    strat._entry_target_price = 90.0
    strat._entry_stop_price = 110.0

    result = strat.signal(tick(85.0), {}, {"entry_price": 100.0})  # fell past target - long-style ">=" would wrongly hold here

    assert result == {"action": "exit", "reason": "target"}


def test_orb_v2_short_position_exits_at_stop_when_price_rises():
    strat = ORBv2Strategy()
    strat._entry_side = "short"
    strat._entry_target_price = 90.0
    strat._entry_stop_price = 110.0

    result = strat.signal(tick(115.0), {}, {"entry_price": 100.0})  # rose past stop - long-style "<=" would wrongly hold here

    assert result == {"action": "exit", "reason": "stop_loss"}


def test_orb_v2_full_signal_sets_short_side_state_used_by_exit_branch():
    strat = _seed_gap_ok_orb_v2(day1_close=100.0)
    strat.signal(tick(99.0, "09:16:00"), {}, None)
    strat.signal(tick(98.0, "09:29:00"), {}, None)
    strat.signal(tick(97.8, "09:32:00"), {}, None)  # real breakdown entry, sets _entry_side via the actual code path

    result = strat.signal(tick(96.0), {}, {"entry_price": 97.8})  # further favorable move for a short

    assert result["action"] == "exit"


def test_orb_v2_exits_at_range_derived_target():
    strat = ORBv2Strategy()
    strat._entry_target_price = 110.0
    strat._entry_stop_price = 90.0

    result = strat.signal(tick(110.0), {}, {"entry_price": 100.0})

    assert result == {"action": "exit", "reason": "target"}


def test_orb_v2_exits_at_range_low_stop():
    strat = ORBv2Strategy()
    strat._entry_target_price = 110.0
    strat._entry_stop_price = 90.0

    result = strat.signal(tick(90.0), {}, {"entry_price": 100.0})

    assert result == {"action": "exit", "reason": "stop_loss"}


def test_orb_v2_exits_at_max_hold_time_when_still_in_position():
    strat = ORBv2Strategy()
    strat._entry_target_price = 999.0
    strat._entry_stop_price = 1.0

    result = strat.signal(tick(100.0, "11:00:00"), {}, {"entry_price": 100.0})

    assert result == {"action": "exit", "reason": "max_hold"}
