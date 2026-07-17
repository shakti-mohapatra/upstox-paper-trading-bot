"""Strategy interface (SONNET_BUILD_PLAN.md Phase 1): pulls the entry/exit
rule out of ExecutionEngine.on_tick so strategies are swappable/comparable.
Strategy only decides; the engine still owns risk/ops controls (sizing,
costs, square-off, kill switch).
"""
from abc import ABC, abstractmethod
from datetime import datetime, time as dtime

ORB_WINDOW_START = dtime(9, 15)
ORB_WINDOW_END = dtime(9, 30)


def _tick_time(tick: dict) -> dtime | None:
    ts = tick.get("ts")
    if not ts:
        return None
    return datetime.fromisoformat(ts).time()


def orb_high_from_candles(candles: list[dict]) -> float | None:
    """max 'high' among 1-min candles falling inside the ORB window, or None."""
    highs = [
        c["high"]
        for c in candles
        if ORB_WINDOW_START <= datetime.fromisoformat(c["timestamp"]).time() < ORB_WINDOW_END
    ]
    return max(highs) if highs else None


class Strategy(ABC):
    @abstractmethod
    def signal(self, tick: dict, params: dict, position: dict | None) -> dict:
        """Returns {"action": "hold"|"enter"|"exit", "reason": str (exit only)}."""

    def new_day(self) -> None:
        """Reset per-day state. Default no-op for stateless strategies."""


class ORBStrategy(Strategy):
    def __init__(self):
        self.orb_high: float | None = None

    def new_day(self) -> None:
        self.orb_high = None

    def signal(self, tick, params, position):
        ltp = tick["ltp"]
        tick_time = _tick_time(tick)

        if position is not None:
            entry = position["entry_price"]
            target_price = entry * (1 + params["target_pct"] / 100)
            hard_stop = entry * (1 - params["stop_loss_pct"] / 100)
            trail_stop = position["high_water"] * (1 - params["trail_pct"] / 100)
            effective_stop = max(hard_stop, trail_stop)
            if ltp >= target_price:
                return {"action": "exit", "reason": "target"}
            if ltp <= effective_stop:
                reason = "stop_loss" if ltp <= hard_stop else "trailing_stop"
                return {"action": "exit", "reason": reason}
            return {"action": "hold"}

        if tick_time is not None and ORB_WINDOW_START <= tick_time < ORB_WINDOW_END:
            self.orb_high = ltp if self.orb_high is None else max(self.orb_high, ltp)
            return {"action": "hold"}
        if tick_time is not None and (self.orb_high is None or ltp <= self.orb_high):
            return {"action": "hold"}
        zone = params["entry_zone"]
        if not (zone["low"] <= ltp <= zone["high"]):
            return {"action": "hold"}
        return {"action": "enter"}


class ORBv2Strategy(Strategy):
    """trading_bot_mandatory_rules.md §4A ORB, as actually specified (unlike
    ORBStrategy, which is a simpler unrelated baseline). Gap filter, range
    filter, breakout confirmation, range-derived stop/target, max-hold cutoff.
    Long-only: short entries are §4A's own spec too but deliberately deferred
    here (execution_engine/broker.paper are long-only end to end; wiring real
    shorting is a bigger, riskier engine change than this filter/timeframe cut
    needs to test its core hypothesis) — ask before building that half."""

    GAP_MIN_PCT = 0.003
    GAP_MAX_PCT = 0.02
    RANGE_MIN_PCT = 0.003
    CONFIRM_PCT = 0.0005
    MIN_TARGET_PCT = 0.008
    TARGET_RANGE_MULT = 1.5
    MAX_HOLD_TIME = dtime(11, 0)

    def __init__(self):
        self._last_ltp: float | None = None
        self._pending_prev_close: float | None = None
        self.new_day()

    def new_day(self) -> None:
        self._pending_prev_close = self._last_ltp
        self.range_high: float | None = None
        self.range_low: float | None = None
        self.gap_ok: bool | None = None
        self._entry_target_price: float | None = None
        self._entry_stop_price: float | None = None

    def signal(self, tick, params, position):
        ltp = tick["ltp"]
        tick_time = _tick_time(tick)

        if position is not None:
            if ltp >= self._entry_target_price:
                return {"action": "exit", "reason": "target"}
            if ltp <= self._entry_stop_price:
                return {"action": "exit", "reason": "stop_loss"}
            if tick_time is not None and tick_time >= self.MAX_HOLD_TIME:
                return {"action": "exit", "reason": "max_hold"}
            return {"action": "hold"}

        if tick_time is None:
            return {"action": "hold"}

        if self.gap_ok is None:
            if self._pending_prev_close:
                gap = (ltp - self._pending_prev_close) / self._pending_prev_close
                self.gap_ok = self.GAP_MIN_PCT <= abs(gap) <= self.GAP_MAX_PCT
            else:
                self.gap_ok = False  # no prior close to measure a gap against (first day in dataset) - don't trade blind
        self._last_ltp = ltp

        if tick_time < ORB_WINDOW_END:
            if tick_time >= ORB_WINDOW_START:
                self.range_high = ltp if self.range_high is None else max(self.range_high, ltp)
                self.range_low = ltp if self.range_low is None else min(self.range_low, ltp)
            return {"action": "hold"}

        if self.range_high is None or self.range_low is None or not self.gap_ok:
            return {"action": "hold"}
        if tick_time >= self.MAX_HOLD_TIME:
            return {"action": "hold"}

        range_width = self.range_high - self.range_low
        if range_width < self.range_high * self.RANGE_MIN_PCT:
            return {"action": "hold"}

        breakout_price = self.range_high * (1 + self.CONFIRM_PCT)
        if ltp <= breakout_price:
            return {"action": "hold"}

        self._entry_target_price = max(
            ltp + range_width * self.TARGET_RANGE_MULT,
            ltp * (1 + self.MIN_TARGET_PCT),
        )
        self._entry_stop_price = self.range_low
        stop_loss_pct = (ltp - self.range_low) / ltp * 100
        return {"action": "enter", "stop_loss_pct": stop_loss_pct}


class MACrossoverStrategy(Strategy):
    def __init__(self, fast_period: int = 9, slow_period: int = 21):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.fast_ema: float | None = None
        self.slow_ema: float | None = None
        self.bullish: bool | None = None  # None until a confirmed (non-tied) direction is observed

    def _update_emas(self, ltp: float) -> bool | None:
        if self.fast_ema is None:
            self.fast_ema = ltp
            self.slow_ema = ltp
        else:
            fast_k = 2 / (self.fast_period + 1)
            slow_k = 2 / (self.slow_period + 1)
            self.fast_ema = ltp * fast_k + self.fast_ema * (1 - fast_k)
            self.slow_ema = ltp * slow_k + self.slow_ema * (1 - slow_k)
        if self.fast_ema == self.slow_ema:
            return None
        return self.fast_ema > self.slow_ema

    def signal(self, tick, params, position):
        ltp = tick["ltp"]
        currently_bullish = self._update_emas(ltp)
        bullish_cross = self.bullish is False and currently_bullish is True
        bearish_cross = self.bullish is True and currently_bullish is False
        if currently_bullish is not None:
            self.bullish = currently_bullish

        if position is not None:
            entry = position["entry_price"]
            target_price = entry * (1 + params["target_pct"] / 100)
            hard_stop = entry * (1 - params["stop_loss_pct"] / 100)
            trail_stop = position["high_water"] * (1 - params["trail_pct"] / 100)
            effective_stop = max(hard_stop, trail_stop)
            if ltp >= target_price:
                return {"action": "exit", "reason": "target"}
            if ltp <= effective_stop:
                reason = "stop_loss" if ltp <= hard_stop else "trailing_stop"
                return {"action": "exit", "reason": reason}
            if bearish_cross:
                return {"action": "exit", "reason": "bearish_cross"}
            return {"action": "hold"}

        if bullish_cross:
            return {"action": "enter"}
        return {"action": "hold"}
