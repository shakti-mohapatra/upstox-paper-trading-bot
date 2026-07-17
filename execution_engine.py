"""Deterministic loop: live ticks vs strategy_params.json -> SL/target/trailing orders.

on_tick() is a stub until Phase 2 build (see PLAN.md roadmap). Must read
strategy_params.json atomically (whole-file read) since analytical_bridge
rewrites it every 15 min via os.replace().
"""
import json
from datetime import datetime, time as dtime

from costs import costs
from position_sizing import MIN_TURNOVER, size_position
from strategy import ORBStrategy
from trade_log import log_fill

SCHEMA_VERSION = 1
CAPITAL = 100000.0  # paper profile (SONNET_BUILD_PLAN.md §2); live = 5000.0 at the Phase 4 gate
RISK_PCT = 0.01  # 1% of capital per trade
SQUARE_OFF_TIME = dtime(15, 15)
NO_ENTRY_AFTER = dtime(15, 0)
MAX_TRADES_PER_DAY = 5
SLIPPAGE_PCT = 0.0005  # assumed adverse slippage per fill in paper trading (mandatory_rules.md §6)


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
        strategy=None,
    ):
        self.broker = broker
        self.params_path = params_path
        self.daily_max_loss = daily_max_loss
        self.trade_log_path = trade_log_path
        self.strategy = strategy if strategy is not None else ORBStrategy()
        self.params: dict | None = None
        self.position: dict | None = None
        self.realized_pnl_today = 0.0
        self.trades_today = 0
        self.consecutive_losses = 0
        self.halted = False
        self.current_day: str | None = None

    def _log_fill(self, tick, side, qty, intended, fill, gross, cost, reason):
        print(f"{tick.get('ts', '')} {side} {qty} @ {intended} ({reason}) net={gross - cost:.2f} pnl_today={self.realized_pnl_today:.2f}")
        if self.trade_log_path is None:
            return
        log_fill(
            self.trade_log_path,
            ts=tick.get("ts", ""),
            symbol=self.params["instrument"],
            strategy="stub",
            side=side,
            qty=qty,
            intended=intended,
            fill=fill,
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
        tick_time = _tick_time(tick)

        day = tick["ts"][:10] if tick.get("ts") else None
        if day is not None and self.current_day is None:
            self.current_day = day  # first tick ever - just record the day, don't wipe pre-seeded state (e.g. backfilled orb_high)
        elif day is not None and day != self.current_day:
            self.current_day = day
            self.trades_today = 0
            self.realized_pnl_today = 0.0
            self.consecutive_losses = 0
            self.halted = False
            self.strategy.new_day()

        if self.position is None:
            if self.halted or not self.params["enabled"] or self.params["regime"] == "avoid":
                return
            if self.trades_today >= MAX_TRADES_PER_DAY:
                return
            if tick_time is not None and tick_time >= NO_ENTRY_AFTER:
                return
            signal = self.strategy.signal(tick, self.params, None)
            if signal["action"] != "enter":
                return
            risk_qty = size_position(
                capital=CAPITAL,
                risk_pct=RISK_PCT,
                entry_price=ltp,
                stop_loss_pct=signal.get("stop_loss_pct", self.params["stop_loss_pct"]),
                buying_power=CAPITAL,
            )
            qty = min(risk_qty, self.params["max_position_qty"])
            if qty <= 0 or qty * ltp < MIN_TURNOVER:
                return
            self.broker.place_order(self.params["instrument"], "BUY", qty, ltp)
            entry_fill = ltp * (1 + SLIPPAGE_PCT)
            entry_cost = costs("BUY", qty, entry_fill)
            self.position = {"qty": qty, "entry_price": ltp, "entry_fill": entry_fill, "high_water": ltp, "entry_cost": entry_cost}
            self.realized_pnl_today -= entry_cost
            self.trades_today += 1
            self._log_fill(tick, "BUY", qty, ltp, entry_fill, gross=0.0, cost=entry_cost, reason="entry")
            return

        pos = self.position
        pos["high_water"] = max(pos["high_water"], ltp)

        square_off = tick_time is not None and tick_time >= SQUARE_OFF_TIME
        signal = {"action": "exit", "reason": "square_off"} if square_off else self.strategy.signal(tick, self.params, pos)

        if signal["action"] == "exit":
            self.broker.place_order(self.params["instrument"], "SELL", pos["qty"], ltp)
            self.position = None
            exit_fill = ltp * (1 - SLIPPAGE_PCT)
            exit_cost = costs("SELL", pos["qty"], exit_fill)
            gross = (exit_fill - pos["entry_fill"]) * pos["qty"]
            net = gross - exit_cost
            self.realized_pnl_today += net
            self._log_fill(tick, "SELL", pos["qty"], ltp, exit_fill, gross=gross, cost=exit_cost, reason=signal["reason"])
            if net < 0:
                self.consecutive_losses += 1
                if self.consecutive_losses >= 3:
                    self.halted = True
            else:
                self.consecutive_losses = 0
            if self.daily_max_loss is not None and self.realized_pnl_today <= -self.daily_max_loss:
                self.halted = True
