"""Local fill simulator.

Fills only when a real tick crosses the order price (honest slippage) -
Upstox sandbox gives idealized instant fills, not used for tuning. place_order
/modify_order/cancel_order are stubs until Phase 2 build (see PLAN.md roadmap).
"""
from broker.base import BrokerAdapter


class PaperBroker(BrokerAdapter):
    def __init__(self):
        self._orders: dict = {}
        self._positions: dict = {}

    def place_order(self, instrument, side, qty, price=None):
        raise NotImplementedError("TODO Phase 2: queue order, fill on tick cross")

    def modify_order(self, order_id, **kwargs):
        raise NotImplementedError("TODO Phase 2")

    def cancel_order(self, order_id):
        raise NotImplementedError("TODO Phase 2")

    def positions(self):
        return self._positions
