"""Minimal permission helpers for turn and cash handling."""
from __future__ import annotations

from pos_core import STATE


def can_open_turn(user: dict | None = None) -> bool:
    return True if not user else True


def can_close_turn(user: dict | None = None) -> bool:
    return True if not user else True


def can_make_cash_movement(user: dict | None = None) -> bool:
    return True if not user else True


def can_cancel_cash_movement(user: dict | None = None) -> bool:
    return (user or {}).get("role", STATE.role) == "admin"
