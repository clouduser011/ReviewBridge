"""Idle session timeout — auto logout after inactivity."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import flash, jsonify, redirect, request, session, url_for
from flask_login import current_user, logout_user

LAST_ACTIVITY_KEY = "_last_activity"


def touch_session() -> None:
    session[LAST_ACTIVITY_KEY] = datetime.now(timezone.utc).timestamp()


def _idle_timeout_seconds(app) -> int:
    minutes = app.config.get("SESSION_IDLE_TIMEOUT_MINUTES", 30)
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        minutes = 30
    return max(1, minutes) * 60


def _wants_json_response() -> bool:
    if request.path.startswith("/fetch/"):
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def init_idle_timeout(app) -> None:
    @app.before_request
    def _enforce_idle_session_timeout():
        if not current_user.is_authenticated:
            return None
        if request.endpoint and str(request.endpoint).startswith("static"):
            return None

        now = datetime.now(timezone.utc).timestamp()
        last = session.get(LAST_ACTIVITY_KEY)

        if last is None:
            touch_session()
            return None

        elapsed = now - float(last)
        if elapsed <= _idle_timeout_seconds(app):
            touch_session()
            return None

        logout_user()
        session.pop(LAST_ACTIVITY_KEY, None)
        flash("Your session expired due to inactivity. Please sign in again.", "info")

        if _wants_json_response():
            return jsonify(
                {"ok": False, "error": "Session expired", "login_required": True}
            ), 401

        return redirect(url_for("auth.login", next=request.path))
