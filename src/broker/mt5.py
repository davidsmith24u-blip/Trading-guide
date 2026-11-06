"""MetaTrader 5 broker adapter.

Requires the `MetaTrader5` package and a running, logged-in MT5 terminal.
Implements the same BrokerInterface as PaperBroker so strategy/risk code is
unchanged. Safe defaults: demo-first, kill switch, hard risk checks.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .base import BrokerInterface, Order, OrderResult, Position
from ..config import AppConfig
from ..risk import RiskManager
from ..strategy import Signal

logger = logging.getLogger("trading_guardian.mt5")

try:
    import MetaTrader5 as mt5

    _MT5_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    mt5 = None
    _MT5_AVAILABLE = False

TF_MAP = {}


def _init_tf_map():
    if not _MT5_AVAILABLE:
        return
    TF_MAP.update(
        {
            "1m": mt5.TIMEFRAME_M1,
            "5m": mt5.TIMEFRAME_M5,
            "15m": mt5.TIMEFRAME_M15,
            "30m": mt5.TIMEFRAME_M30,
            "1h": mt5.TIMEFRAME_H1,
            "4h": mt5.TIMEFRAME_H4,
            "1d": mt5.TIMEFRAME_D1,
        }
    )


_init_tf_map()


class MT5Broker(BrokerInterface):
    def __init__(self, cfg: AppConfig, risk: RiskManager = None, store=None, user_id=None):
        self.cfg = cfg
        self.risk = risk
        self.store = store
        self.user_id = user_id
        self.mt5_cfg = cfg.mt5 or {}
        self.magic = int(self.mt5_cfg.get("magic_number", 202411))
        self.deviation = int(self.mt5_cfg.get("deviation", 20))
        self.timeout_ms = int(self.mt5_cfg.get("timeout_ms", 10000))
        self.symbol_suffix = self.mt5_cfg.get("symbol_suffix", "") or ""
        self.kill_switch_file = cfg.kill_switch_file
        # cfg is AppConfig; execution is nested in raw? AppConfig has mode only. Read from cfg? We'll store via cfg.mt5? kill switch from env/config optional.
        self._connected = False

    # ---- connection ----
    def connect(self) -> bool:
        if not _MT5_AVAILABLE:
            logger.error("MetaTrader5 package not available")
            return False
        path = self.mt5_cfg.get("path") or None
        login = self.mt5_cfg.get("login")
        password = self.mt5_cfg.get("password") or os.getenv("MT5_PASSWORD", "")
        server = self.mt5_cfg.get("server")
        kwargs = {}
        if path:
            kwargs["path"] = path
        if login:
            kwargs["login"] = int(login)
        if password:
            kwargs["password"] = password
        if server:
            kwargs["server"] = server
        kwargs["timeout"] = self.timeout_ms
        try:
            if not mt5.initialize(**kwargs):
                logger.error("mt5.initialize failed: %s", mt5.last_error())
                return False
            self._connected = True
            logger.info("MT5 connected: %s", mt5.terminal_info())
            return True
        except Exception as e:
            logger.exception("MT5 connect error: %s", e)
            return False

    def disconnect(self) -> None:
        if _MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False

    # ---- safety ----
    def _kill_switch_active(self) -> bool:
        return os.path.exists(self.kill_switch_file)

    def is_trading_allowed(self) -> Tuple[bool, str]:
        if not _MT5_AVAILABLE or not self._connected:
            return False, "mt5 not connected"
        if self._kill_switch_active():
            return False, "kill switch active"
        mode = self.cfg.mode
        if mode == "mt5_live":
            confirm = self.cfg.confirm_live or self.cfg.live_confirmed
            env_confirm = os.getenv("CONFIRM_LIVE", "").lower() == "true" or os.getenv("LIVE_CONFIRMED", "").lower() == "true"
            if not (env_confirm or confirm):
                return False, "live mode not confirmed (set live_confirmed + env)"
        ti = mt5.terminal_info()
        if ti is None or not getattr(ti, "connected", False):
            return False, "terminal disconnected"
        if not getattr(ti, "trade_allowed", False):
            return False, "algo trading disabled in terminal"
        if self.risk is not None:
            allowed, reason = self.risk.trading_allowed()
            if not allowed:
                return False, reason
        return True, "ok"

    # ---- symbol helpers ----
    def _symbol(self, pair: str) -> str:
        return f"{pair}{self.symbol_suffix}"

    def _normalize_volume(self, symbol: str, volume: float) -> float:
        info = mt5.symbol_info(symbol) if _MT5_AVAILABLE else None
        if info is None:
            return volume
        vmin = info.volume_min
        vmax = info.volume_max
        step = info.volume_step
        if step and step > 0:
            volume = round(round(volume / step) * step, 8)
        volume = max(vmin, min(vmax, volume))
        return volume

    # ---- account / positions ----
    def get_account_info(self) -> Dict[str, Any]:
        if not _MT5_AVAILABLE or not self._connected:
            return {}
        info = mt5.account_info()
        if info is None:
            return {}
        return info._asdict()

    def get_positions(self) -> List[Position]:
        if not _MT5_AVAILABLE or not self._connected:
            return []
        positions = mt5.positions_get() or []
        out = []
        for p in positions:
            if getattr(p, "magic", 0) != self.magic:
                continue
            side = 1 if p.type == mt5.POSITION_TYPE_BUY else -1
            out.append(
                Position(
                    pair=p.symbol.replace(self.symbol_suffix, ""),
                    side=side,
                    units=p.volume,
                    entry=p.price_open,
                    stop_loss=p.sl,
                    take_profit=p.tp,
                    orig_stop=p.sl,
                    opened_at=pd.Timestamp(p.time, unit="s"),
                    reason="",
                    atr=0.0,
                    risk_pct=0.0,
                    position_id=p.ticket,
                )
            )
        return out

    def get_open_orders(self) -> List[Order]:
        if not _MT5_AVAILABLE or not self._connected:
            return []
        orders = mt5.orders_get() or []
        out = []
        for o in orders:
            if getattr(o, "magic", 0) != self.magic:
                continue
            side = 1 if o.type in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP) else -1
            out.append(Order(ticket=o.ticket, pair=o.symbol, side=side, volume=o.volume_current, price=o.price_open, sl=o.sl, tp=o.tp))
        return out

    # ---- rates ----
    def get_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        if not _MT5_AVAILABLE or not self._connected:
            return pd.DataFrame()
        sym = self._symbol(symbol)
        tf = TF_MAP.get(timeframe.lower(), mt5.TIMEFRAME_M15)
        rates = mt5.copy_rates_from_pos(sym, tf, 0, count)
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(columns={"time": "index"}).set_index("index")
        df = df.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close", "tick_volume": "volume"})
        return df[["open", "high", "low", "close", "volume"]]

    # ---- order placement ----
    def place_order(self, signal: Signal, size: float) -> OrderResult:
        allowed, reason = self.is_trading_allowed()
        if not allowed:
            logger.warning("order blocked: %s", reason)
            return OrderResult(success=False, message=reason)

        symbol = self._symbol(signal.pair)
        if not mt5.symbol_select(symbol, True):
            return OrderResult(success=False, message=f"symbol not available: {symbol}")

        info = mt5.symbol_info(symbol)
        if info is None:
            return OrderResult(success=False, message=f"no symbol info: {symbol}")

        volume = self._normalize_volume(symbol, size)
        if volume <= 0:
            return OrderResult(success=False, message="invalid volume")

        price = mt5.symbol_info_tick(symbol)
        if price is None:
            return OrderResult(success=False, message="no tick")
        if signal.side == 1:
            order_type = mt5.ORDER_TYPE_BUY
            price_val = price.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price_val = price.bid

        sl = signal.stop_loss
        tp = signal.take_profit

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price_val,
            "sl": sl,
            "tp": tp,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "trading-guardian",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        logger.info("sending order: %s", request)
        result = mt5.order_send(request)
        if result is None:
            logger.error("order_send returned None: %s", mt5.last_error())
            return OrderResult(success=False, message=str(mt5.last_error()))

        logger.info("order result: retcode=%s comment=%s", result.retcode, result.comment)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(success=False, ticket=result.order, message=f"retcode {result.retcode}: {result.comment}", raw=result)

        # confirm
        pos = None
        for _ in range(5):
            positions = mt5.positions_get(ticket=result.order)
            if positions:
                pos = positions[0]
                break
            import time

            time.sleep(0.2)
        ticket = pos.ticket if pos else result.order
        fill_price = pos.price_open if pos else result.price
        return OrderResult(success=True, ticket=ticket, price=fill_price, message="done", raw=result)

    def modify_position(self, ticket: Any, sl: float, tp: float) -> bool:
        if not _MT5_AVAILABLE or not self._connected:
            return False
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": sl,
            "tp": tp,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("modify failed: %s", result)
            return False
        return True

    def close_position(self, ticket: Any, volume: Optional[float] = None) -> bool:
        if not _MT5_AVAILABLE or not self._connected:
            return False
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return False
        p = positions[0]
        symbol = p.symbol
        if volume is None:
            volume = p.volume
        volume = self._normalize_volume(symbol, volume)
        if p.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(symbol).bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(symbol).ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("close failed: %s", result)
            return False
        return True

    # ---- kill switch ----
    def activate_kill_switch(self) -> int:
        """Close all positions for this magic number. Returns count closed."""
        closed = 0
        for p in list(self.get_positions()):
            if self.close_position(p.position_id):
                closed += 1
        # create kill-switch file
        try:
            with open(self.kill_switch_file, "w") as f:
                f.write("activated")
        except Exception:
            pass
        logger.critical("kill switch activated, closed %d positions", closed)
        return closed

    def watchdog(self) -> Tuple[bool, str]:
        if not _MT5_AVAILABLE or not self._connected:
            return False, "not connected"
        ti = mt5.terminal_info()
        if ti is None:
            return False, "terminal info unavailable"
        if not getattr(ti, "connected", False):
            return False, "terminal disconnected"
        return True, "ok"

    def reconcile(self, expected_tickets: List[Any]) -> Dict[str, Any]:
        """Compare expected tickets vs actual broker positions."""
        actual = [p.position_id for p in self.get_positions()]
        missing = [t for t in expected_tickets if t not in actual]
        unexpected = [t for t in actual if t not in expected_tickets]
        return {"expected": expected_tickets, "actual": actual, "missing": missing, "unexpected": unexpected}

    def status(self) -> Dict[str, Any]:
        allowed, reason = self.is_trading_allowed()
        info = self.get_account_info()
        return {
            "mode": self.cfg.mode,
            "connected": self._connected,
            "trading_allowed": allowed,
            "reason": reason,
            "account": info,
            "positions": len(self.get_positions()),
            "kill_switch": self._kill_switch_active(),
        }