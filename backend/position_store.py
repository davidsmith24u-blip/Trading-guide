"""DB-backed store for persisted paper positions."""

from __future__ import annotations

from backend.db import delete_open_position, load_open_positions, save_open_position


class PositionStore:
    def save_open_position(self, user_id, pos):
        return save_open_position(user_id, pos)

    def load_open_positions(self, user_id):
        return load_open_positions(user_id)

    def delete_open_position(self, position_id):
        delete_open_position(position_id)