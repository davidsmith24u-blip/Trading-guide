"""Persisted paper positions endpoints."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user
from backend.db import delete_open_position, load_open_positions
from backend.position_store import PositionStore
from backend.schemas import RiskStatusResponse

router = APIRouter()


@router.get("/positions")
def list_positions(current_user=Depends(get_current_user)):
    rows = load_open_positions(current_user["id"])
    return {"items": rows, "count": len(rows)}


@router.delete("/positions/{position_id}")
def close_position(position_id: int, current_user=Depends(get_current_user)):
    rows = load_open_positions(current_user["id"])
    if not any(r["id"] == position_id for r in rows):
        raise HTTPException(status_code=404, detail="position not found")
    delete_open_position(position_id)
    return {"deleted": position_id}