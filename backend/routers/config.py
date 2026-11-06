"""Config read/write endpoints."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter

from backend.config_store import load, save_dict, to_dict
from backend.schemas import ConfigResponse

router = APIRouter()


@router.get("/config", response_model=ConfigResponse)
def get_config():
    return ConfigResponse(config=to_dict(load()))


@router.post("/config", response_model=ConfigResponse)
def post_config(payload: dict):
    cfg = save_dict(payload)
    return ConfigResponse(config=to_dict(cfg))