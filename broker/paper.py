"""Local fill simulator.

execution_engine only ever places orders at the current live tick price (no
resting limit orders away from market), so a fill against a real observed
tick means: fill immediately at the given price. That price IS the real
tick that crossed it - honest, unlike Upstox sandbox's idealized fills.
"""
from broker.base import BrokerAdapter


class PaperBroker(BrokerAdapter):
    def __init__(self):
        self._orders: dict = {}
        self._positions: dict = {}

    def place_order(self, instrument, side, qty, price=None):
        order_id = f"paper-{len(self._orders) + 1}"
        self._orders[order_id] = {"instrument": instrument, "side": side, "qty": qty, "price": price}
        signed_qty = qty if side == "BUY" else -qty
        self._positions[instrument] = self._positions.get(instrument, 0) + signed_qty
        return order_id

    def modify_order(self, order_id, **kwargs):
        raise ValueError(f"order {order_id} already filled, nothing to modify")

    def cancel_order(self, order_id):
        raise ValueError(f"order {order_id} already filled, nothing to cancel")

    def positions(self):
        return self._positions
