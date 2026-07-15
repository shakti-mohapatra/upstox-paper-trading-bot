"""Deterministic loop: live ticks vs strategy_params.json -> SL/target/trailing orders.

on_tick() is a stub until Phase 2 build (see PLAN.md roadmap). Must read
strategy_params.json atomically (whole-file read) since analytical_bridge
rewrites it every 15 min via os.replace().
"""
import json
from datetime import datetime, time as dtime

from costs import costs
from position_sizing import size_position
from trade_log import log_fill

SCHEMA_VERSION = 1
CAPITAL = 100000.0  # paper profile (SONNET_BUILD_PLAN.md §2); live = 5000.0 at the Phase 4 gate
RISK_PCT = 0.01  # 1% of capital per trade
SQUARE_OFF_TIME = dtime(15, 15)
NO_ENTRY_AFTER = dtime(15, 0)
ORB_WINDOW_START = dtime(9, 15)
ORB_WINDOW_END = dtime(9, 30)


def _tick_time(tick: dict) -> dtime | None:
    ts = tick.get("ts")
    if not ts:
        return None
    return datetime.fromisoformat(ts).time()


class ExecutionEngine:
    def __init__(
        self,
        broker,
        params_path: str = "strategy_params.json",
        daily_max_loss: float | None = None,
        trade_log_path: str | None = None,
    ):
        self.broker = broker
        self.params_path = params_path
        self.daily_max_loss = daily_max_loss
        self.trade_log_path = trade_log_path
        self.params: dict | None = None
        self.position: dict | None = None
        self.realized_pnl_today = 0.0
        self.halted = False
        self.orb_high: float | None = None

    def _log_fill(self, tick, side, qty, price, gross, cost, reason):
        if self.trade_log_path is None:
            return
        log_fill(
            self.trade_log_path,
            ts=tick.get("ts", ""),
            symbol=self.params["instrument"],
            strategy="stub",
            side=side,
            qty=qty,
            intended=price,
            fill=price,
            gross=gross,
            cost=cost,
            net=gross - cost,
            reason=reason,
        )

    def load_params(self) -> dict:
        with open(self.params_path) as f:
            data = json.load(f)
        if data.get("version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported strategy_params schema version: {data.get('version')!r}")
        self.params = data
        return data

    def on_tick(self, tick: dict):
        if self.params is None:
            return
        if tick["instrument"] != self.params["instrument"]:
            return
        ltp = tick["ltp"]
        if self.position is None:
            if self.halted or not self.params["enabled"] or self.params["regime"] == "avoid":
                return
            tick_time = _tick_time(tick)
            if tick_time is not None and tick_time >= NO_ENTRY_AFTER:
                return
            if tick_time is not None and ORB_WINDOW_START <= tick_time < ORB_WINDOW_END:
                self.orb_high = ltp if self.orb_high is None else max(self.orb_high, ltp)
                return
            if tick_time is not None and (self.orb_high is None or ltp <= self.orb_high):
                return
            zone = self.params["entry_zone"]
            if not (zone["low"] <= ltp <= zone["high"]):
                return
            risk_qty = size_position(
                capital=CAPITAL,
                risk_pct=RISK_PCT,
                entry_price=ltp,
                stop_loss_pct=self.params["stop_loss_pct"],
                buying_power=CAPITAL,
            )
            qty = min(risk_qty, self.params["max_position_qty"])
            self.broker.place_order(self.params["instrument"], "BUY", qty, ltp)
            entry_cost = costs("BUY", qty, ltp)
            self.position = {"qty": qty, "entry_price": ltp, "high_water": ltp, "entry_cost": entry_cost}
            self.realized_pnl_today -= entry_cost
            self._log_fill(tick, "BUY", qty, ltp, gross=0.0, cost=entry_cost, reason="entry")
            return

        pos = self.position
        pos["high_water"] = max(pos["high_water"], ltp)
        entry = pos["entry_price"]
        target_price = entry * (1 + self.params["target_pct"] / 100)
        hard_stop = entry * (1 - self.params["stop_loss_pct"] / 100)
        trail_stop = pos["high_water"] * (1 - self.params["trail_pct"] / 100)
        effective_stop = max(hard_stop, trail_stop)

        tick_time = _tick_time(tick)
        square_off = tick_time is not None and tick_time >= SQUARE_OFF_TIME

        if square_off or ltp >= target_price or ltp <= effective_stop:
            self.broker.place_order(self.params["instrument"], "SELL", pos["qty"], ltp)
            self.position = None
            exit_cost = costs("SELL", pos["qty"], ltp)
            gross = (ltp - entry) * pos["qty"]
            self.realized_pnl_today += gross - exit_cost
            if square_off:
                reason = "square_off"
            elif ltp >= target_price:
                reason = "target"
            elif ltp <= hard_stop:
                reason = "stop_loss"
            else:
                reason = "trailing_stop"
            self._log_fill(tick, "SELL", pos["qty"], ltp, gross=gross, cost=exit_cost, reason=reason)
            if self.daily_max_loss is not None and self.realized_pnl_today <= -self.daily_max_loss:
                self.halted = True
