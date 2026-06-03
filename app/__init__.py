import os
from dotenv import load_dotenv
from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()

DEFAULT_DATABASE_URI = "sqlite:///instance/reviewbridge.db"
LEGACY_DATABASE_URI = "sqlite:///instance/review_analyzer.db"


def _resolve_database_uri() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    instance_dir = os.path.join(root, "instance")
    new_path = os.path.join(instance_dir, "reviewbridge.db")
    legacy_path = os.path.join(instance_dir, "review_analyzer.db")

    if os.path.isfile(legacy_path) and not os.path.isfile(new_path):
        return LEGACY_DATABASE_URI
    return DEFAULT_DATABASE_URI


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = _resolve_database_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    migrate.init_app(app, db)

    from .datetime_utils import utc_naive_to_local
    from .routes import main_bp
    from .auth import auth_bp
    from .account import account_bp
    from flask_login import LoginManager

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id: str):
        from .models import User

        return db.session.get(User, int(user_id))

    login_manager.init_app(app)

    @app.context_processor
    def inject_auth_context():
        from flask_login import current_user

        return {
            "current_user": current_user,
            "is_authenticated": current_user.is_authenticated,
        }

    @app.template_filter("review_date_display")
    def review_date_display(dt):
        local = utc_naive_to_local(dt)
        if local is None:
            return "—"
        return local.strftime("%b %d, %Y")

    @app.template_filter("review_date_title")
    def review_date_title(dt):
        local = utc_naive_to_local(dt)
        if local is None:
            return ""
        return local.strftime("%Y-%m-%d %H:%M")

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(account_bp)

    with app.app_context():
        from . import models

        db.create_all()
        _ensure_review_columns()
        _ensure_auth_columns()
        _ensure_ticket_constraints()

    return app


def _ensure_review_columns():
    """Add optional Review columns on existing SQLite DBs created before these fields."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if "review" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("review")}
    statements = []
    if "reviewed_at" not in existing:
        statements.append("ALTER TABLE review ADD COLUMN reviewed_at DATETIME")
    if "last_batch_at" not in existing:
        statements.append("ALTER TABLE review ADD COLUMN last_batch_at DATETIME")
    if "play_rank" not in existing:
        statements.append("ALTER TABLE review ADD COLUMN play_rank INTEGER")
    if not statements:
        return
    with db.engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def _ensure_auth_columns():
    """Add auth / owner columns on existing SQLite DBs."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    if "review" in tables:
        existing = {col["name"] for col in inspector.get_columns("review")}
        statements = []
        if "user_id" not in existing:
            statements.append("ALTER TABLE review ADD COLUMN user_id INTEGER")
        if "owner_session_key" not in existing:
            statements.append("ALTER TABLE review ADD COLUMN owner_session_key VARCHAR(64)")
        with db.engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))

    if "ticket" in tables:
        existing = {col["name"] for col in inspector.get_columns("ticket")}
        if "user_id" not in existing:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE ticket ADD COLUMN user_id INTEGER"))

    if "processing_log" in tables:
        existing = {col["name"] for col in inspector.get_columns("processing_log")}
        if "user_id" not in existing:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE processing_log ADD COLUMN user_id INTEGER"))


def _ensure_ticket_constraints():
    """One ticket per review: dedupe existing rows and add unique index on SQLite."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if "ticket" not in inspector.get_table_names():
        return

    with db.engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM ticket WHERE id NOT IN ("
                "SELECT MIN(id) FROM ticket GROUP BY review_id)"
            )
        )
        try:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_ticket_review_id "
                    "ON ticket (review_id)"
                )
            )
        except Exception:
            pass
