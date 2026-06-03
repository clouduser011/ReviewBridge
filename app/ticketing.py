import os
import re
from datetime import datetime
from typing import Any, Dict

import requests

from .crypto_utils import decrypt_secret

_PLACEHOLDER_PATTERNS = (
    re.compile(r"^your[-_]", re.I),
    re.compile(r"your[-_]domain", re.I),
    re.compile(r"your[-_]subdomain", re.I),
    re.compile(r"^you@example\.com$", re.I),
    re.compile(r"^change[-_]me$", re.I),
    re.compile(r"^example$", re.I),
    re.compile(r"^placeholder$", re.I),
)


def _is_placeholder(value: str | None) -> bool:
    if not value or not str(value).strip():
        return True
    text = str(value).strip()
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _env_value(key: str) -> str | None:
    raw = os.getenv(key)
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    if _is_placeholder(text):
        return None
    return text


def _mock_external_id(prefix: str, idx: int) -> str:
    now = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{now}-{idx}"


def _jira_env_configured() -> bool:
    return bool(
        _env_value("JIRA_BASE_URL")
        and _env_value("JIRA_EMAIL")
        and _env_value("JIRA_API_TOKEN")
        and _env_value("JIRA_PROJECT_KEY")
    )


def _zendesk_env_configured() -> bool:
    return bool(
        _env_value("ZENDESK_SUBDOMAIN")
        and _env_value("ZENDESK_EMAIL")
        and _env_value("ZENDESK_API_TOKEN")
    )


def _jira_from_integration(integration) -> dict | None:
    if not integration or not integration.jira_enabled:
        return None
    token = decrypt_secret(integration.jira_api_token_encrypted)
    if not (integration.jira_base_url and integration.jira_email and token and integration.jira_project_key):
        return None
    return {
        "base_url": integration.jira_base_url.rstrip("/"),
        "email": integration.jira_email,
        "api_token": token,
        "project_key": integration.jira_project_key,
        "issue_type": integration.jira_issue_type or "Task",
    }


def _zendesk_from_integration(integration) -> dict | None:
    if not integration or not integration.zendesk_enabled:
        return None
    token = decrypt_secret(integration.zendesk_api_token_encrypted)
    if not (integration.zendesk_subdomain and integration.zendesk_email and token):
        return None
    return {
        "subdomain": integration.zendesk_subdomain.strip(),
        "email": integration.zendesk_email,
        "api_token": token,
    }


def _jira_mock_payload(review, idx: int, summary: str) -> Dict[str, Any]:
    return {
        "platform": "Jira",
        "external_ticket_id": _mock_external_id("JIRA", idx),
        "title": summary,
        "status": "open",
        "mode": "mock",
    }


def _zendesk_mock_payload(review, idx: int, subject: str) -> Dict[str, Any]:
    return {
        "platform": "Zendesk",
        "external_ticket_id": _mock_external_id("ZD", idx),
        "title": subject,
        "status": "open",
        "mode": "mock",
    }


def _plain_text_to_adf(text: str) -> dict:
    """Convert plain text to Atlassian Document Format for Jira Cloud API v3."""
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = []
    for line in normalized.split("\n"):
        clean = "".join(ch for ch in line if ch == "\t" or ord(ch) >= 32)
        if clean:
            paragraphs.append(
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": clean}],
                }
            )
        else:
            paragraphs.append({"type": "paragraph", "content": []})
    if not paragraphs:
        paragraphs.append({"type": "paragraph", "content": []})
    return {"type": "doc", "version": 1, "content": paragraphs}


def create_jira_ticket(review, idx: int = 1, integration=None) -> Dict[str, Any]:
    """Create a real Jira issue if configured; otherwise return mock."""

    summary = f"[{review.category}] {review.app_name} review by {review.author}"
    description = (
        f"Source: {review.source}\n"
        f"Rating: {review.rating}/5\n"
        f"Sentiment: {review.sentiment} (conf={review.confidence})\n\n"
        f"Review:\n{review.content}\n"
    )

    cfg = _jira_from_integration(integration)

    if integration is not None:
        if not integration.jira_enabled or cfg is None:
            return _jira_mock_payload(review, idx, summary)
    else:
        use_env = _jira_env_configured()
        if not cfg and not use_env:
            return _jira_mock_payload(review, idx, summary)

    if cfg:
        base_url = cfg["base_url"]
        auth = (cfg["email"], cfg["api_token"])
        project_key = cfg["project_key"]
        issue_type = cfg["issue_type"]
    else:
        base_url = _env_value("JIRA_BASE_URL") or ""
        base_url = base_url.rstrip("/")
        auth = (_env_value("JIRA_EMAIL"), _env_value("JIRA_API_TOKEN"))
        project_key = _env_value("JIRA_PROJECT_KEY") or "RA"
        issue_type = _env_value("JIRA_ISSUE_TYPE") or "Task"

    url = f"{base_url}/rest/api/3/issue"
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": _plain_text_to_adf(description),
            "issuetype": {"name": issue_type},
        }
    }

    resp = requests.post(url, json=payload, auth=auth, timeout=20)
    if resp.status_code >= 300:
        raise RuntimeError(f"Jira API error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    ticket_key = data.get("key") or data.get("id") or _mock_external_id("JIRA", idx)

    return {
        "platform": "Jira",
        "external_ticket_id": str(ticket_key),
        "title": summary,
        "status": "open",
        "mode": "real",
    }


def create_zendesk_ticket(review, idx: int = 1, integration=None) -> Dict[str, Any]:
    """Create a real Zendesk ticket if configured; otherwise return mock."""

    subject = f"Customer Support - {review.app_name} ({review.author})"
    comment = (
        f"Source: {review.source}\n"
        f"Rating: {review.rating}/5\n"
        f"Sentiment: {review.sentiment} (conf={review.confidence})\n\n"
        f"Review:\n{review.content}\n"
    )

    cfg = _zendesk_from_integration(integration)

    if integration is not None:
        if not integration.zendesk_enabled or cfg is None:
            return _zendesk_mock_payload(review, idx, subject)
    else:
        use_env = _zendesk_env_configured()
        if not cfg and not use_env:
            return _zendesk_mock_payload(review, idx, subject)

    if cfg:
        subdomain = cfg["subdomain"]
        auth = (f"{cfg['email']}/token", cfg["api_token"])
    else:
        subdomain = (_env_value("ZENDESK_SUBDOMAIN") or "").strip()
        auth = (f"{_env_value('ZENDESK_EMAIL')}/token", _env_value("ZENDESK_API_TOKEN"))

    url = f"https://{subdomain}.zendesk.com/api/v2/tickets.json"
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
