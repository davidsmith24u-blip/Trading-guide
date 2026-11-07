import os
import tempfile

from crypto_agent.src.policy import gate, size
from crypto_agent.src.risk import RiskLimits, RiskManager
from crypto_agent.src.schemas import JevDecision
from crypto_agent.src.state_engine import build_snapshot, to_prompt


def test_state_snapshot():
    ob = {"bids": [[100.0, 1.0]], "asks": [[100.01, 1.0]]}
    snap = build_snapshot(ob, [{"price": 100.0}], 0.0, 10000.0, 10000.0, 0.0, 0.0)
    assert snap.mid > 0
    p = to_prompt(snap)
    assert "STATE" in p
    assert len(p) < 400 * 4  # rough token proxy


def test_risk_blocks():
    rm = RiskManager(RiskLimits(max_position_usd=100.0), 10000.0)
    ok, _ = rm.check(200.0, 0.0)
    assert ok is False


def test_gate():
    d = JevDecision(
        regime="trending",
        direction="long",
        direction_confidence=0.9,
        toxic_flow="absent",
        setup_quality=2,
        risk_state="safe",
        calibrated_prob=0.7,
    )
    assert gate(d, True) is True
    assert gate(d, False) is False


def test_size_positive():
    d = JevDecision(
        regime="trending",
        direction="long",
        direction_confidence=0.9,
        toxic_flow="absent",
        setup_quality=2,
        risk_state="safe",
        calibrated_prob=0.7,
    )
    s = size(d, 10000.0)
    assert s > 0