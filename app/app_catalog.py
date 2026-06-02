"""Local app catalog for instant, name-first app search."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "app_catalog.json"
_catalog_cache: Optional[List[Dict[str, str]]] = None
_catalog_mtime: Optional[float] = None

_PACKAGE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", re.I)
_WORD_RE = re.compile(r"[a-z0-9]+", re.I)

# Minimum score to treat as a "strong" local match (exact / near-exact title).
STRONG_MATCH_SCORE = 700


def catalog_path() -> Path:
    return _CATALOG_PATH


def is_package_query(query: str) -> bool:
    q = (query or "").strip()
    return bool(q and "." in q and _PACKAGE_RE.match(q))


def normalize_app_entry(item: Dict[str, Any]) -> Optional[Dict[str, str]]:
    package_name = (item.get("package_name") or item.get("appId") or "").strip()
    app_name = (item.get("app_name") or item.get("title") or "").strip()
    if not package_name or not app_name:
        return None
    return {
        "app_name": app_name,
        "package_name": package_name,
        "icon": (item.get("icon") or "").strip(),
        "developer": (item.get("developer") or "").strip(),
    }


def _tokenize(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def score_app_match(query: str, app: Dict[str, str]) -> int:
    """Higher score = better match. Name-first; package-only matches rank low for name queries."""
    q = (query or "").strip().lower()
    if not q:
        return 0

    title = (app.get("app_name") or "").lower()
    developer = (app.get("developer") or "").lower()
    pkg = (app.get("package_name") or "").lower()
    pkg_query = is_package_query(query)

    if pkg_query:
        if pkg == q:
            return 1000
        if pkg.startswith(q) or q in pkg:
            return 850
        return 0

    score = 0

    if title == q:
        score = max(score, 950)
    if title.startswith(q):
        score = max(score, 900)
    if q in title:
        score = max(score, 750)

    q_tokens = _tokenize(q)
    title_tokens = _tokenize(title)
    if q_tokens and title_tokens:
        if all(any(tt.startswith(qt) for tt in title_tokens) for qt in q_tokens):
            score = max(score, 820)
        if all(qt in title_tokens for qt in q_tokens):
            score = max(score, 780)

    if q in developer:
        score = max(score, 400)

    # Package substring only as weak tie-breaker for name searches.
    if q in pkg and score < 500:
        score = max(score, 120)

    return score


def rank_apps(query: str, apps: List[Dict[str, str]], limit: int) -> List[Dict[str, str]]:
    requested = max(1, int(limit))
    scored: List[Tuple[int, str, Dict[str, str]]] = []
    for app in apps:
        norm = normalize_app_entry(app)
        if not norm:
            continue
        s = score_app_match(query, norm)
        if s <= 0:
            continue
        scored.append((s, norm["app_name"].lower(), norm))

    scored.sort(key=lambda x: (-x[0], len(x[2].get("package_name") or ""), x[1]))
    return [row[2] for row in scored[:requested]]


def load_catalog(force_reload: bool = False) -> List[Dict[str, str]]:
    global _catalog_cache, _catalog_mtime
    path = _CATALOG_PATH
    if not path.is_file():
        _catalog_cache = []
        _catalog_mtime = None
        return []

    mtime = path.stat().st_mtime
    if not force_reload and _catalog_cache is not None and _catalog_mtime == mtime:
        return _catalog_cache

    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items = raw.get("apps") or raw.get("items") or []
    else:
        items = raw

    out: List[Dict[str, str]] = []
    seen = set()
    for item in items:
        norm = normalize_app_entry(item)
        if not norm:
            continue
        pkg = norm["package_name"]
        if pkg in seen:
            continue
        seen.add(pkg)
        out.append(norm)

    _catalog_cache = out
    _catalog_mtime = mtime
    return out


def catalog_status() -> Dict[str, Any]:
    path = _CATALOG_PATH
    exists = path.is_file()
    count = len(load_catalog()) if exists else 0
    ready = exists and count >= 500
    return {
        "path_exists": exists,
        "count": count,
        "ready": ready,
        "path": str(path),
    }


def search_local_catalog(query: str, limit: int = 12) -> List[Dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    catalog = load_catalog()
    if not catalog:
        return []
    if is_package_query(q):
        pkg_l = q.lower()
        for app in catalog:
            if (app.get("package_name") or "").lower() == pkg_l:
                return [app]
        partial = [
            app
            for app in catalog
            if pkg_l in (app.get("package_name") or "").lower()
        ]
        return rank_apps(q, partial, limit)
    return rank_apps(q, catalog, limit)


def lookup_local_by_package(package_name: str) -> Optional[Dict[str, str]]:
    pkg = (package_name or "").strip().lower()
    if not pkg:
        return None
    for app in load_catalog():
        if (app.get("package_name") or "").lower() == pkg:
            return app
    return None


def has_strong_local_match(query: str, local_results: List[Dict[str, str]]) -> bool:
    if not local_results:
        return False
    top_score = score_app_match(query, local_results[0])
    return top_score >= STRONG_MATCH_SCORE
