import hashlib
from textblob import TextBlob

CATEGORY_RULES = {
    "bug": ["bug", "crash", "error", "stuck", "freeze", "lag", "issue", "failed"],
    "feature_request": ["add", "feature", "please include", "need", "wish", "would be great"],
    "support": ["help", "support", "account", "login", "payment", "subscription", "refund"],
    "complaint": ["bad", "worst", "hate", "terrible", "poor", "disappointed", "slow"],
}


def stable_review_id(author: str, content: str, rating: int) -> str:
    key = f"{author.strip().lower()}|{content.strip().lower()}|{rating}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def content_hash_storage_id(app_name: str, author: str, content: str, rating: int) -> str:
    app_key = (app_name or "").strip().lower()
    return f"{app_key}:{stable_review_id(author, content, rating)}"


def play_storage_id(play_review_id: str) -> str:
    return f"play:{str(play_review_id).strip()}"


def review_storage_id(
    app_name: str,
    play_review_id: str | None,
    author: str,
    content: str,
    rating: int,
) -> str:
    if play_review_id and str(play_review_id).strip():
        return play_storage_id(str(play_review_id).strip())
    return content_hash_storage_id(app_name, author, content, rating)


def find_existing_review(
    app_name: str,
    play_review_id: str | None,
    author: str,
    content: str,
    rating: int,
):
    """Find a stored review by canonical id, Play reviewId, or content hash."""
    from .models import Review

    canonical_id = review_storage_id(app_name, play_review_id, author, content, rating)
    existing = Review.query.filter_by(review_id=canonical_id).first()
    if existing:
        return existing

    play_id = (play_review_id or "").strip()
    if play_id:
        existing = Review.query.filter_by(review_id=play_storage_id(play_id)).first()
        if existing:
            return existing

    hash_id = content_hash_storage_id(app_name, author, content, rating)
    if hash_id != canonical_id:
        existing = Review.query.filter_by(review_id=hash_id).first()
        if existing:
            return existing

    return None


def analyze_sentiment(text: str) -> tuple[str, float]:
    polarity = TextBlob(text).sentiment.polarity
    if polarity > 0.15:
        return "positive", min(1.0, 0.5 + polarity)
    if polarity < -0.15:
        return "negative", min(1.0, 0.5 + abs(polarity))
    return "neutral", 0.55


def classify_category(text: str, rating: int, sentiment: str) -> str:
    lowered = text.lower()
    for category, words in CATEGORY_RULES.items():
        if any(word in lowered for word in words):
            return category

    if rating <= 2 and sentiment == "negative":
        return "complaint"
    if rating >= 4 and "feature" in lowered:
        return "feature_request"
    if sentiment == "negative":
        return "support"
    return "feature_request" if "could" in lowered or "should" in lowered else "support"
