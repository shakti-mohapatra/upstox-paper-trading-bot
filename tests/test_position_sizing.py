import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from position_sizing import size_position


def test_size_position_is_capped_by_buying_power_when_it_binds_tighter_than_risk():
    qty = size_position(capital=100000.0, risk_pct=0.01, entry_price=100.0, stop_loss_pct=0.5, buying_power=100000.0)

    assert qty == 1000  # floor(100000/100); risk allows floor(1000/(100*0.005))=2000, affordability binds


def test_size_position_is_capped_by_risk_when_buying_power_is_generous():
    qty = size_position(capital=100000.0, risk_pct=0.01, entry_price=100.0, stop_loss_pct=0.5, buying_power=1000000.0)

    assert qty == 2000  # floor(1000/(100*0.005))=2000; affordability floor(1000000/100)=10000 doesn't bind
