"""Abstract broker interface.

All brokers (paper, MT5, ...) implement this so strategy/risk code stays unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..strategy import Signal


@dataclass
class Position:
    pair: str
    side: int
    units: float
    entry: float
    stop_loss: float
    take_profit: float
    orig_stop: float
    opened_at: pd.Timestamp
    reason: str = ""
    atr: float = 0.0
    risk_pct: float = 0.0
    position_id: Optional[Any] = None  # broker ticket / id


@dataclass
class Order:
    ticket: Any
    pair: str
    side: int
    volume: float
    price: float
    sl: float
    tp: float


@dataclass
class OrderResult:
    success: bool
    ticket: Optional[Any] = None
    price: float = 0.0
    message: str = ""
    raw: Any = None


class BrokerInterface(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]: ...

    @abstractmethod
    def get_positions(self) -> List[Position]: ...

    @abstractmethod
    def get_open_orders(self) -> List[Order]: ...

    @abstractmethod
    def place_order(self, signal: Signal, size: float) -> OrderResult: ...

    @abstractmethod
    def modify_position(self, ticket: Any, sl: float, tp: float) -> bool: ...

    @abstractmethod
    def close_position(self, ticket: Any, volume: Optional[float] = None) -> bool: ...

    @abstractmethod
    def get_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame: ...

    @abstractmethod
    def is_trading_allowed(self) -> Tuple[bool, str]: ...