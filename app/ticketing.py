import os
from datetime import datetime
from typing import Any, Dict

import requests


def _mock_external_id(prefix: str, idx: int) -> str:
    now = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{now}-{idx}"


def _jira_is_configured() -> bool:
    return bool(
        os.getenv("JIRA_BASE_URL")
        and os.getenv("JIRA_EMAIL")
        and os.getenv("JIRA_API_TOKEN")
        and os.getenv("JIRA_PROJECT_KEY")
    )


def _zendesk_is_configured() -> bool:
    return bool(
        os.getenv("ZENDESK_SUBDOMAIN")
        and os.getenv("ZENDESK_EMAIL")
        and os.getenv("ZENDESK_API_TOKEN")
    )


def create_jira_ticket(review, idx: int = 1) -> Dict[str, Any]:
    """Create a real Jira issue if configured; otherwise return mock."""

    project_key = os.getenv("JIRA_PROJECT_KEY", "RA")
    issue_type = os.getenv("JIRA_ISSUE_TYPE", "Task")

    summary = f"[{review.category}] {review.app_name} review by {review.author}"
    description = (
        f"Source: {review.source}\n"
        f"Rating: {review.rating}/5\n"
        f"Sentiment: {review.sentiment} (conf={review.confidence})\n\n"
        f"Review:\n{review.content}\n"
    )

    if not _jira_is_configured():
        return {
            "platform": "Jira",
            "external_ticket_id": _mock_external_id(project_key, idx),
            "title": summary,
            "status": "open",
            "mode": "mock",
        }

    base_url = os.getenv("JIRA_BASE_URL").rstrip("/")
    url = f"{base_url}/rest/api/3/issue"

    auth = (os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
        }
    }

    resp = requests.post(url, json=payload, auth=auth, timeout=20)
    if resp.status_code >= 300:
        raise RuntimeError(f"Jira API error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    ticket_key = data.get("key") or data.get("id") or _mock_external_id(project_key, idx)

    return {
        "platform": "Jira",
        "external_ticket_id": str(ticket_key),
        "title": summary,
        "status": "open",
        "mode": "real",
    }


def create_zendesk_ticket(review, idx: int = 1) -> Dict[str, Any]:
    """Create a real Zendesk ticket if configured; otherwise return mock."""

    subject = f"Customer Support - {review.app_name} ({review.author})"
    comment = (
        f"Source: {review.source}\n"
        f"Rating: {review.rating}/5\n"
        f"Sentiment: {review.sentiment} (conf={review.confidence})\n\n"
        f"Review:\n{review.content}\n"
    )

    if not _zendesk_is_configured():
        return {
            "platform": "Zendesk",
            "external_ticket_id": _mock_external_id("ZD", idx),
            "title": subject,
            "status": "open",
            "mode": "mock",
        }

    subdomain = os.getenv("ZENDESK_SUBDOMAIN").strip()
    url = f"https://{subdomain}.zendesk.com/api/v2/tickets.json"

    # Zendesk API token auth: user email + "/token" as username
    auth = (f"{os.getenv('ZENDESK_EMAIL')}/token", os.getenv("ZENDESK_API_TOKEN"))
    payload = {"ticket": {"subject": subject, "comment": {"body": comment}}}

    resp = requests.post(url, json=payload, auth=auth, timeout=20)
    if resp.status_code >= 300:
        raise RuntimeError(f"Zendesk API error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    ticket_id = (
        (data.get("ticket") or {}).get("id")
        or data.get("id")
        or _mock_external_id("ZD", idx)
    )

    return {
        "platform": "Zendesk",
        "external_ticket_id": str(ticket_id),
        "title": subject,
        "status": "open",
        "mode": "real",
    }


def choose_ticket_platform(category: str) -> str:
    if category in {"bug", "feature_request"}:
        return "Jira"
    return "Zendesk"
