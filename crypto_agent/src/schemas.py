"""Jev decision schema (typed)."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Regime(str, Enum):
    trending = "trending"
    mean_reverting = "mean_reverting"
    high_vol = "high_vol"
    crisis = "crisis"


class Direction(str, Enum):
    long = "long"
    short = "short"
    neutral = "neutral"


class RiskState(str, Enum):
    safe = "safe"
    near_limit = "near_limit"
    reduce = "reduce"


class JevDecision(BaseModel):
    regime: Regime
    direction: Direction
    direction_confidence: float = Field(ge=0.0, le=1.0)
    toxic_flow: str
    setup_quality: int = Field(ge=0, le=3)
    risk_state: RiskState
    calibrated_prob: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=300)