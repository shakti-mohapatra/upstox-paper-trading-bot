"""Risk-based position sizing, affordability-capped (SONNET_BUILD_PLAN.md §2)."""
import math


MIN_TURNOVER = 10000.0  # below this, brokerage floor + GST dominate the edge (mandatory_rules.md §3)


def size_position(capital: float, risk_pct: float, entry_price: float, stop_loss_pct: float, buying_power: float) -> int:
    """Risk/affordability/exposure-capped qty. Does NOT apply the MIN_TURNOVER
    floor - this qty is pre the caller's own max_position_qty ceiling, so
    checking turnover here would validate a number that gets shrunk later
    (see execution_engine.on_tick, which checks turnover after its own cap)."""
    risk = capital * risk_pct
    sl_frac = stop_loss_pct / 100
    risk_qty = math.floor(risk / (entry_price * sl_frac))
    afford_qty = math.floor(buying_power / entry_price)
    max_turnover_qty = math.floor((capital * 0.20) / entry_price)
    return min(risk_qty, afford_qty, max_turnover_qty)
