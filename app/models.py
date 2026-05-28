from datetime import datetime
from . import db


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
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


class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey("review.id"), nullable=False)
    platform = db.Column(db.String(32), nullable=False)
    external_ticket_id = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    review = db.relationship("Review", backref=db.backref("tickets", lazy=True))


class ProcessingLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    level = db.Column(db.String(20), nullable=False, default="info")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
