"""Dev (REFLEX) client. Mock when no API key."""

from __future__ import annotations

import json
import os
import random
from typing import Any

from .schemas import JevDecision


def ask_dev(prompt: str, schema=JevDecision) -> JevDecision:
    api_key = os.getenv("DEV_API_KEY")
    if not api_key:
        # mock: deterministic-ish random decision for offline dev
        rnd = random.Random(hash(prompt) % 10**6)
        return JevDecision(
            regime=rnd.choice(["trending", "mean_reverting", "high_vol", "crisis"]),
            direction=rnd.choice(["long", "short", "neutral"]),
            direction_confidence=round(rnd.uniform(0.5, 0.95), 2),
            toxic_flow=rnd.choice(["absent", "present", "uncertain"]),
            setup_quality=rnd.randint(0, 3),
            risk_state=rnd.choice(["safe", "near_limit", "reduce"]),
            calibrated_prob=round(rnd.uniform(0.4, 0.85), 2),
            rationale="mock decision (set DEV_API_KEY for real Dev)",
        )
    # real call placeholder: implement HTTP to console.typesafe.ai
    import urllib.request

    req = urllib.request.Request(
        "https://console.typesafe.ai/v1/decide",
        data=json.dumps({"prompt": prompt, "schema": schema.model_json_schema()}).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read())
    return schema.model_validate(data)