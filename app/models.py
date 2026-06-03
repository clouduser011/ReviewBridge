from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(120), nullable=False, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Orphan v2 columns — kept for existing SQLite DBs; v1 auth ignores these.
    email_verified = db.Column(db.Boolean, nullable=False, default=True)
    google_id = db.Column(db.String(64), nullable=True)
    auth_provider = db.Column(db.String(20), nullable=False, default="local")
    avatar_filename = db.Column(db.String(120), nullable=True)

    integration = db.relationship(
        "UserIntegrationSettings",
        backref="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def label(self) -> str:
        return (self.display_name or "").strip() or self.email.split("@")[0]

    @property
    def initials(self) -> str:
        label = self.label.strip()
        if not label:
            return "?"
        parts = label.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return label[:2].upper()


class UserIntegrationSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    jira_enabled = db.Column(db.Boolean, nullable=False, default=False)
    jira_base_url = db.Column(db.String(255), nullable=True)
    jira_email = db.Column(db.String(255), nullable=True)
    jira_api_token_encrypted = db.Column(db.Text, nullable=True)
    jira_project_key = db.Column(db.String(32), nullable=True)
    jira_issue_type = db.Column(db.String(64), nullable=True)

    zendesk_enabled = db.Column(db.Boolean, nullable=False, default=False)
    zendesk_subdomain = db.Column(db.String(120), nullable=True)
    zendesk_email = db.Column(db.String(255), nullable=True)
    zendesk_api_token_encrypted = db.Column(db.Text, nullable=True)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    owner_session_key = db.Column(db.String(64), nullable=True, index=True)
    source = db.Column(db.String(120), nullable=False, default="Google Play")
    app_name = db.Column(db.String(200), nullable=False)
    review_id = db.Column(db.String(200), unique=True, nullable=False)
    author = db.Column(db.String(150), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    sentiment = db.Column(db.String(32), nullable=False)
    category = db.Column(db.String(64), nullable=False)
    confidence = db.Column(db.Float, nullable=False, default=0.5)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    last_batch_at = db.Column(db.DateTime, nullable=True)
    play_rank = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("reviews", lazy=True))


class Ticket(db.Model):
    __table_args__ = (UniqueConstraint("review_id", name="uq_ticket_review_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    review_id = db.Column(db.Integer, db.ForeignKey("review.id"), nullable=False)
    platform = db.Column(db.String(32), nullable=False)
    external_ticket_id = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    review = db.relationship("Review", backref=db.backref("tickets", lazy=True))
    user = db.relationship("User", backref=db.backref("tickets", lazy=True))


class ProcessingLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    message = db.Column(db.Text, nullable=False)
    level = db.Column(db.String(20), nullable=False, default="info")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("processing_logs", lazy=True))
