"""Deterministic loop: live ticks vs strategy_params.json -> SL/target/trailing orders.

on_tick() is a stub until Phase 2 build (see PLAN.md roadmap). Must read
strategy_params.json atomically (whole-file read) since analytical_bridge
rewrites it every 15 min via os.replace().
"""
import json

SCHEMA_VERSION = 1


class ExecutionEngine:
    def __init__(self, broker, params_path: str = "strategy_params.json", daily_max_loss: float | None = None):
        self.broker = broker
        self.params_path = params_path
        self.daily_max_loss = daily_max_loss
        self.params: dict | None = None
        self.position: dict | None = None
        self.realized_pnl_today = 0.0
        self.halted = False

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
            zone = self.params["entry_zone"]
            if not (zone["low"] <= ltp <= zone["high"]):
                return
            qty = self.params["max_position_qty"]
            self.broker.place_order(self.params["instrument"], "BUY", qty, ltp)
            self.position = {"qty": qty, "entry_price": ltp, "high_water": ltp}
            return

        pos = self.position
        pos["high_water"] = max(pos["high_water"], ltp)
        entry = pos["entry_price"]
        target_price = entry * (1 + self.params["target_pct"] / 100)
        hard_stop = entry * (1 - self.params["stop_loss_pct"] / 100)
        trail_stop = pos["high_water"] * (1 - self.params["trail_pct"] / 100)
        effective_stop = max(hard_stop, trail_stop)

        if ltp >= target_price or ltp <= effective_stop:
            self.broker.place_order(self.params["instrument"], "SELL", pos["qty"], ltp)
            self.position = None
            self.realized_pnl_today += (ltp - entry) * pos["qty"]
            if self.daily_max_loss is not None and self.realized_pnl_today <= -self.daily_max_loss:
                self.halted = True
