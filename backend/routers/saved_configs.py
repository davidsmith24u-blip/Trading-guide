"""Saved (named) configurations per user."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.config_store import deep_merge, from_dict, to_dict
from backend.db import delete_saved_config, get_saved_config, get_user_config, list_saved_configs, save_saved_config, set_user_config

router = APIRouter()


class SaveConfigRequest(BaseModel):
    name: str
    config: dict | None = None  # if None, save current active config


@router.get("/configs/saved")
def list_saved(current_user=Depends(get_current_user)):
    return {"items": list_saved_configs(current_user["id"])}


@router.post("/configs/saved")
def save_saved(req: SaveConfigRequest, current_user=Depends(get_current_user)):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name required")
    if req.config is not None:
        cfg = req.config
    else:
        cfg = get_user_config(current_user["id"])
        if cfg is None:
            from backend.config_store import load as load_global

            cfg = to_dict(load_global())
    save_saved_config(current_user["id"], req.name.strip(), cfg)
    return {"name": req.name.strip(), "saved": True}


@router.get("/configs/saved/{name}")
def load_saved(name: str, current_user=Depends(get_current_user)):
    cfg = get_saved_config(current_user["id"], name)
    if cfg is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"name": name, "config": cfg}


@router.delete("/configs/saved/{name}")
def delete_saved(name: str, current_user=Depends(get_current_user)):
    ok = delete_saved_config(current_user["id"], name)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": True}


@router.post("/configs/saved/{name}/activate")
def activate_saved(name: str, current_user=Depends(get_current_user)):
    cfg = get_saved_config(current_user["id"], name)
    if cfg is None:
        raise HTTPException(status_code=404, detail="not found")
    set_user_config(current_user["id"], cfg)
    return {"activated": name, "config": cfg}