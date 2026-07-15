"""Risk-based position sizing, affordability-capped (SONNET_BUILD_PLAN.md §2)."""
import math


def size_position(capital: float, risk_pct: float, entry_price: float, stop_loss_pct: float, buying_power: float) -> int:
    risk = capital * risk_pct
    sl_frac = stop_loss_pct / 100
    risk_qty = math.floor(risk / (entry_price * sl_frac))
    afford_qty = math.floor(buying_power / entry_price)
    return min(risk_qty, afford_qty)
