"""Flask application factory, database bootstrap, and schema migrations.

Canonical DB path: instance/reviewbridge.db (absolute URI).
Legacy nested paths are merged on startup so existing user data is preserved.
"""

import os
import shutil
import sqlite3

from dotenv import load_dotenv
from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sqlite_uri(abs_path: str) -> str:
    return "sqlite:///" + os.path.abspath(abs_path).replace("\\", "/")


def _database_stats(path: str) -> tuple[int, int, int]:
    """Return (user_count, review_count, file_size) for ranking SQLite sources."""
    if not os.path.isfile(path):
        return (0, 0, 0)
    size = os.path.getsize(path)
    try:
        with sqlite3.connect(path) as con:
            tables = {
                row[0]
                for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            users = (
                con.execute("SELECT COUNT(*) FROM user").fetchone()[0] if "user" in tables else 0
            )
            reviews = (
                con.execute("SELECT COUNT(*) FROM review").fetchone()[0]
                if "review" in tables
                else 0
            )
    except sqlite3.Error:
        return (0, 0, size)
    return (users, reviews, size)


def _database_score(path: str) -> int:
    users, reviews, size = _database_stats(path)
    return users * 1000 + reviews * 10 + size // 1000


def _legacy_database_candidates(instance_dir: str) -> tuple[str, ...]:
    return (
        os.path.join(instance_dir, "instance", "reviewbridge.db"),
        os.path.join(instance_dir, "review_analyzer.db"),
        os.path.join(instance_dir, "instance", "review_analyzer.db"),
    )


def _copy_database_file(src: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)


def _migrate_database_files(instance_dir: str) -> None:
    """Copy or reconcile legacy/nested SQLite files into canonical instance/reviewbridge.db."""
    canonical = os.path.join(instance_dir, "reviewbridge.db")
    candidates = [p for p in _legacy_database_candidates(instance_dir) if os.path.isfile(p)]
    if not candidates and not os.path.isfile(canonical):
        return

    best = max(candidates, key=_database_score) if candidates else None
    if not os.path.isfile(canonical):
        if best:
            _copy_database_file(best, canonical)
        return

    if not best or best == canonical:
        return

    best_users, best_reviews, _ = _database_stats(best)
    canon_users, canon_reviews, _ = _database_stats(canonical)
    significantly_better = best_users > canon_users or (
        best_reviews >= canon_reviews * 2 and best_reviews > canon_reviews
    )
    if significantly_better and _database_score(best) > _database_score(canonical):
        backup = canonical + ".bak"
        shutil.copy2(canonical, backup)
        _copy_database_file(best, canonical)


def _resolve_database_uri() -> str:
    """Always resolve relative sqlite:/// paths to the canonical absolute DB file."""
    root = _project_root()
    instance_dir = os.path.join(root, "instance")
    os.makedirs(instance_dir, exist_ok=True)
    _migrate_database_files(instance_dir)
    canonical = os.path.join(instance_dir, "reviewbridge.db")

    explicit = (os.getenv("DATABASE_URL") or "").strip()
    if explicit:
        if explicit.startswith("sqlite:"):
            # Relative sqlite:///instance/... resolves under Flask instance_path and
            # creates instance/instance/*.db — always use canonical absolute path.
            if not explicit.startswith("sqlite:////"):
                return _sqlite_uri(canonical)
        return explicit

    if not os.path.isfile(canonical):
        legacy = os.path.join(instance_dir, "review_analyzer.db")
        if os.path.isfile(legacy):
            shutil.copy2(legacy, canonical)

    return _sqlite_uri(canonical)


def create_app(testing=None):
    """Build Flask app, wire auth, blueprints, and run lightweight SQLite migrations."""
    app = Flask(__name__)

    if testing is None:
        testing = os.getenv("TESTING", "").strip().lower() in ("1", "true", "yes", "on")

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    if testing:
        app.config["TESTING"] = True
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = _resolve_database_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app.config["UPLOAD_AVATAR_DIR"] = os.path.join(root, "instance", "uploads", "avatars")
    os.makedirs(app.config["UPLOAD_AVATAR_DIR"], exist_ok=True)

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

    app.config["SESSION_IDLE_TIMEOUT_MINUTES"] = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "30"))
    from .session_idle import init_idle_timeout

    init_idle_timeout(app)

    # Inject auth helpers into all Jinja templates (current_user, avatar flag).
    @app.context_processor
    def inject_auth_context():
        from flask_login import current_user

        from .avatar_utils import avatar_exists

        has_user_avatar = False
        if current_user.is_authenticated:
            has_user_avatar = avatar_exists(current_user.id)

        return {
            "current_user": current_user,
            "is_authenticated": current_user.is_authenticated,
            "has_user_avatar": has_user_avatar,
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

    # create_all + lightweight ALTER TABLE migrations for existing SQLite files.
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
