"""Storage diagnostics: reviews vs tickets and duplicate detection."""
from sqlalchemy import func

from . import db
from .models import Review, Ticket


def storage_health_report() -> dict:
    """Summarize review/ticket counts and common duplicate patterns."""
    total_reviews = Review.query.count()
    total_tickets = Ticket.query.count()

    per_app_rows = (
        db.session.query(
            Review.app_name,
            func.count(Review.id).label("reviews"),
            func.count(Ticket.id).label("tickets"),
        )
        .outerjoin(Ticket, Ticket.review_id == Review.id)
        .group_by(Review.app_name)
        .all()
    )
    per_app = [
        {
            "app_name": row.app_name or "Unknown App",
            "reviews": int(row.reviews or 0),
            "tickets": int(row.tickets or 0),
        }
        for row in per_app_rows
    ]

    multi_ticket_rows = (
        db.session.query(Ticket.review_id, func.count(Ticket.id).label("n"))
        .group_by(Ticket.review_id)
        .having(func.count(Ticket.id) > 1)
        .all()
    )
    reviews_with_multiple_tickets = len(multi_ticket_rows)

    duplicate_storage_ids = (
        db.session.query(Review.review_id, func.count(Review.id).label("n"))
        .group_by(Review.review_id)
        .having(func.count(Review.id) > 1)
        .all()
    )

    return {
        "ok": reviews_with_multiple_tickets == 0 and not duplicate_storage_ids,
        "total_reviews": total_reviews,
        "total_tickets": total_tickets,
        "expected_max_tickets": total_reviews,
        "reviews_with_multiple_tickets": reviews_with_multiple_tickets,
        "duplicate_review_storage_ids": len(duplicate_storage_ids),
        "per_app": per_app,
        "hints": [
            "Each review should have at most one ticket.",
            "If tickets > reviews, check for duplicate Review rows (hash vs play: id).",
            "Jira + Zendesk counts on Analysis are two buckets that sum to total tickets, not double-counting per review.",
        ],
    }
