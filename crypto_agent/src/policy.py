"""Gate + sizing. Model proposes, code decides."""

from __future__ import annotations

from .schemas import Direction, JevDecision, RiskState


def gate(d: JevDecision, risk_ok: bool) -> bool:
    if not risk_ok:
        return False
    if d.setup_quality < 2:
        return False
    if d.direction_confidence <= 0.80:
        return False
    if d.risk_state != RiskState.safe:
        return False
    if d.direction == Direction.neutral:
        return False
    if d.calibrated_prob < 0.55:
        return False
    return True


def size(d: JevDecision, equity: float, payoff: float = 2.0) -> float:
    prob = d.calibrated_prob
    b = payoff
    f_star = (b * prob - (1 - prob)) / b
    f = max(0.0, min(f_star * 0.25, 0.25))
    return round(equity * f, 2)