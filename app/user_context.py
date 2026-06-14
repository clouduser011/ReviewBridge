"""Auth helpers: owner scoping, session keys, integration lookup."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from flask import session
from flask_login import current_user

from . import db
from .models import UserIntegrationSettings


@dataclass
class OwnerContext:
    user_id: int | None
    owner_session_key: str | None
    allow_tickets: bool
    integration: UserIntegrationSettings | None = None


def get_owner_session_key() -> str:
    """Stable anonymous owner id stored in Flask session for unauthenticated analysis batches."""
    key = session.get("owner_session_key")
    if not key:
        key = uuid.uuid4().hex
        session["owner_session_key"] = key
    return str(key)


def capture_owner_context() -> OwnerContext:
    """Snapshot who owns the current request: logged-in user or anonymous session."""
    if current_user.is_authenticated:
        integration = UserIntegrationSettings.query.filter_by(user_id=current_user.id).first()
        allow_tickets = True
        return OwnerContext(
            user_id=current_user.id,
            owner_session_key=None,
            allow_tickets=allow_tickets,
            integration=integration,
        )
    return OwnerContext(
        user_id=None,
        owner_session_key=get_owner_session_key(),
        allow_tickets=False,
        integration=None,
    )


def get_user_integration(user_id: int) -> UserIntegrationSettings | None:
    return UserIntegrationSettings.query.filter_by(user_id=user_id).first()


def owner_context_for_worker(
    user_id: int | None,
    owner_session_key: str | None,
    allow_tickets: bool,
) -> OwnerContext:
    """Rebuild OwnerContext inside background fetch/upload threads."""
    integration = None
    if user_id:
        integration = UserIntegrationSettings.query.filter_by(user_id=user_id).first()
    return OwnerContext(user_id, owner_session_key, allow_tickets, integration)


def get_or_create_integration(user_id: int) -> UserIntegrationSettings:
    row = UserIntegrationSettings.query.filter_by(user_id=user_id).first()
    if row is None:
        row = UserIntegrationSettings(user_id=user_id)
        db.session.add(row)
        db.session.commit()
    return row
