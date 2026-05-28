import os
from dotenv import load_dotenv
from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///instance/review_analyzer.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    migrate.init_app(app, db)

    from .datetime_utils import utc_naive_to_local
    from .routes import main_bp

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

    with app.app_context():
        from . import models

        db.create_all()
        _ensure_review_columns()

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
