"""Admin-only endpoints."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends

from backend.auth import get_current_user, require_admin
from backend.db import count_configs, count_saved_configs, count_users

router = APIRouter()


@router.get("/admin/stats")
def admin_stats(_admin=Depends(require_admin)):
    return {
        "users": count_users(),
        "active_configs": count_configs(),
        "saved_configs": count_saved_configs(),
    }