"""BrokerAdapter interface.

paper.py implements this for local paper trading; upstox_live.py implements
the same interface at go-live, so the paper<->live swap is one line.
"""
from abc import ABC, abstractmethod
from typing import Optional


class BrokerAdapter(ABC):
    @abstractmethod
    def place_order(self, instrument: str, side: str, qty: int, price: Optional[float] = None) -> str:
        """Returns order_id."""

    @abstractmethod
    def modify_order(self, order_id: str, **kwargs) -> None:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> None:
        ...

    @abstractmethod
    def positions(self) -> dict:
        ...
