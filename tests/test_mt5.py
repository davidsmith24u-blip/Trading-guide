"""MT5 broker tests (skip if MetaTrader5 not installed)."""

import pytest

try:
    import MetaTrader5  # noqa: F401

    HAS_MT5 = True
except Exception:
    HAS_MT5 = False

pytestmark = pytest.mark.skipif(not HAS_MT5, reason="MetaTrader5 not installed")


def test_mt5_import():
    from src.broker.mt5 import MT5Broker

    assert MT5Broker is not None