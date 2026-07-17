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
