"""Config read/write endpoints."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends

from backend.auth import get_current_user
from backend.config_store import deep_merge, from_dict, to_dict
from backend.db import get_user_config, set_user_config
from backend.schemas import ConfigResponse

router = APIRouter()


@router.get("/config", response_model=ConfigResponse)
def get_config(current_user=Depends(get_current_user)):
    user_cfg = get_user_config(current_user["id"])
    if user_cfg is None:
        from backend.config_store import load as load_global

        user_cfg = to_dict(load_global())
        set_user_config(current_user["id"], user_cfg)
    return ConfigResponse(config=user_cfg)


@router.post("/config", response_model=ConfigResponse)
def post_config(payload: dict, current_user=Depends(get_current_user)):
    user_cfg = get_user_config(current_user["id"])
    if user_cfg is None:
        from backend.config_store import load as load_global

        user_cfg = to_dict(load_global())
    merged = deep_merge(user_cfg, payload)
    set_user_config(current_user["id"], merged)
    return ConfigResponse(config=merged)