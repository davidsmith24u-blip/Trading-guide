"""Apply lightweight DB migrations (idempotent)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db import init_db

if __name__ == "__main__":
    init_db()
    print("migrations applied")