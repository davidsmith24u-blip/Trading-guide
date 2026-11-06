"""Trade journal endpoints."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.db import list_trades, trade_stats, update_trade_journal

router = APIRouter()


class NoteRequest(BaseModel):
    notes: str | None = None
    tags: str | None = None


@router.get("/journal")
def get_journal(limit: int = 100, source: str | None = None, current_user=Depends(get_current_user)):
    items = list_trades(user_id=current_user["id"], limit=limit, source=source)
    stats = trade_stats(user_id=current_user["id"], source=source)
    return {"items": items, "stats": stats}


@router.post("/journal/{trade_id}/notes")
def set_notes(trade_id: int, req: NoteRequest, current_user=Depends(get_current_user)):
    items = list_trades(user_id=current_user["id"], limit=10000)
    if not any(t["id"] == trade_id for t in items):
        raise HTTPException(status_code=404, detail="trade not found")
    ok = update_trade_journal(trade_id, notes=req.notes, tags=req.tags)
    return {"updated": ok}