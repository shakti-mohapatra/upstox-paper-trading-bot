import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from position_sizing import size_position


def test_size_position_is_capped_at_20pct_of_capital_even_when_buying_power_is_tight():
    qty = size_position(capital=100000.0, risk_pct=0.01, entry_price=100.0, stop_loss_pct=0.5, buying_power=100000.0)

    assert qty == 200  # floor(20000/100); risk allows 2000, affordability allows 1000, 20%-capital cap binds


def test_size_position_is_capped_at_20pct_of_capital_even_when_buying_power_is_generous():
    qty = size_position(capital=100000.0, risk_pct=0.01, entry_price=100.0, stop_loss_pct=0.5, buying_power=1000000.0)

    assert qty == 200  # risk allows 2000, affordability allows 10000, 20%-capital cap still binds at 200


def test_size_position_does_not_apply_the_min_turnover_floor():
    # MIN_TURNOVER is checked by the caller (execution_engine), after its own max_position_qty
    # cap - not here, where the qty isn't final yet. See position_sizing.size_position docstring.
    qty = size_position(capital=5000.0, risk_pct=0.01, entry_price=100.0, stop_loss_pct=0.5, buying_power=5000.0)

    assert qty == 10
