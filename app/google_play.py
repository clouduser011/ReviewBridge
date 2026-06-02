import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .app_catalog import normalize_app_entry, rank_apps, score_app_match
from .datetime_utils import normalize_play_review_at

log = logging.getLogger(__name__)

_CACHE_TTL_SEC = 900
_CACHE_MAX = 200
_SEARCH_CACHE: Dict[str, tuple] = {}
_PACKAGE_CACHE: Dict[str, tuple] = {}


def _cache_get(store: Dict[str, tuple], key: str):
    row = store.get(key)
    if not row:
        return None
    expires_at, value = row
    if time.time() > expires_at:
        store.pop(key, None)
        return None
    return value


def _cache_set(store: Dict[str, tuple], key: str, value, max_size: int):
    if len(store) >= max_size:
        oldest = next(iter(store))
        store.pop(oldest, None)
    store[key] = (time.time() + _CACHE_TTL_SEC, value)

# Play scraping: smaller pages + backoff tend to return steadier continuation tokens.
_PAGE_BATCH_LIMITED = 120
_PAGE_BATCH_UNLIMITED = 200
_SLEEP_AFTER_PAGE = 0.45
_MAX_RETRIES_EMPTY = 4
_RETRY_BASE_SLEEP = 0.6
# Safety valves (per storefront)
_MAX_PAGES_LIMITED_MODE = 800
_MAX_PAGES_UNLIMITED_MODE = 25_000


def _import_scraper():
    try:
        from google_play_scraper import Sort, reviews, reviews_all, search
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "google-play-scraper is not installed. Run: pip install -r requirements.txt"
        ) from e
    return Sort, reviews, reviews_all, search


def _resolve_fetch_countries(country: str, *, limited: bool = False) -> List[str]:
    c = (country or "").lower()
    if c in ("", "ww", "global", "all", "world"):
        if limited:
            return ["us"]
        return [
            "us",
            "gb",
            "in",
            "de",
            "br",
            "id",
            "jp",
            "fr",
            "ca",
            "au",
            "mx",
            "es",
            "it",
            "kr",
            "tr",
            "ae",
            "pk",
            "nl",
            "pl",
            "sg",
            "my",
            "ph",
            "vn",
        ]
    return [country]


def _sort_rows_by_date(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def _sort_key(row: Dict[str, Any]) -> float:
        at = row.get("at")
        if at is None:
            return 0.0
        try:
            return float(at.timestamp())
        except AttributeError:
            return 0.0

    return sorted(rows, key=_sort_key, reverse=True)


def _review_entry_from_play_row(r: Dict[str, Any]) -> Dict[str, Any]:
    play_review_id = r.get("reviewId")
    return {
        "author": r.get("userName") or "anonymous",
        "rating": int(r.get("score") or 3),
        "content": (r.get("content") or "").strip(),
        "at": normalize_play_review_at(r.get("at")),
        "play_review_id": str(play_review_id).strip() if play_review_id is not None else "",
    }


def _dedupe_key_for_row(r: Dict[str, Any], entry: Dict[str, Any]) -> tuple:
    rid = r.get("reviewId")
    if rid is not None and str(rid).strip():
        return ("id", str(rid))
    return ("body", entry["author"], entry["rating"], entry["content"])


def _continuation_has_more(ct: Any) -> bool:
    if ct is None:
        return False
    tok = getattr(ct, "token", None)
    return tok is not None


def _notify_progress(
    callback: Optional[Callable[..., None]],
    collected: int,
    goal: Optional[int],
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    if not callback:
        return
    try:
        callback(collected, goal, meta or {})
    except TypeError:
        try:
            callback(collected, goal)
        except Exception:
            pass
    except Exception:
        pass


def _merge_rows(
    play_rows: List[Dict[str, Any]],
    out: List[Dict[str, Any]],
    seen: set,
    target: Optional[int],
) -> None:
    for r in play_rows:
        entry = _review_entry_from_play_row(r)
        if not entry["content"]:
            continue
        key = _dedupe_key_for_row(r, entry)
        if key in seen:
            continue
        seen.add(key)
        entry["play_rank"] = len(out)
        out.append(entry)
        if target is not None and len(out) >= target:
            return


def _sort_enum(sort: str, Sort: Any) -> Any:
    sort_map = {
        "newest": Sort.NEWEST,
        "rating": Sort.RATING,
        "helpfulness": (
            getattr(Sort, "HELPFULNESS", None)
            or getattr(Sort, "MOST_RELEVANT", None)
            or getattr(Sort, "RELEVANCE", None)
            or Sort.NEWEST
        ),
    }
    return sort_map.get((sort or "newest").lower(), Sort.NEWEST)


def _finalize_fetch_rows(
    rows: List[Dict[str, Any]],
    sort: str,
    *,
    target: Optional[int] = None,
    multi_country: bool = False,
) -> List[Dict[str, Any]]:
    """Keep Play API order for single-storefront fetches; date-sort only when mixed."""
    sort_key = (sort or "newest").lower()
    if multi_country and sort_key == "newest":
        rows = _sort_rows_by_date(rows)
    if target is not None:
        return rows[:target]
    return rows


def _reviews_single_request(
    reviews_fn: Any,
    package_name: str,
    lang: str,
    country_code: str,
    sort_enum: Any,
    batch: int,
    continuation: Any,
) -> Tuple[List[Dict[str, Any]], Any]:
    try:
        kwargs = {
            "country": country_code,
            "sort": sort_enum,
            "count": max(1, min(batch, 200)),
            "continuation_token": continuation,
        }
        if lang and str(lang).strip():
            kwargs["lang"] = str(lang).strip()
        return reviews_fn(package_name, **kwargs)
    except Exception as exc:
        log.warning("google_play reviews() failed for %s (%s): %s", package_name, country_code, exc)
        return [], continuation


def _paginate_storefront(
    *,
    package_name: str,
    lang: str,
    country_code: str,
    sort_enum: Any,
    reviews_fn: Any,
    target: Optional[int],
    out: List[Dict[str, Any]],
    seen: set,
    page_batch: int,
    max_pages: int,
    progress_callback: Optional[Callable[..., None]],
    should_continue: Optional[Callable[[], bool]],
    progress_total_for_ui: int,
) -> None:
    """
    Walk Play pagination for one storefront until target unique rows (if set),
    continuation ends, or safety page cap.
    """
    continuation: Any = None
    pages = 0

    while pages < max_pages:
        if should_continue and not should_continue():
            return
        if target is not None and len(out) >= target:
            return

        if target is not None:
            batch = min(page_batch, target - len(out))
        else:
            batch = page_batch
        if batch <= 0:
            return

        rows: List[Dict[str, Any]] = []
        last_ct: Any = continuation

        for attempt in range(_MAX_RETRIES_EMPTY):
            if should_continue and not should_continue():
                return
            rows, last_ct = _reviews_single_request(
                reviews_fn,
                package_name,
                lang,
                country_code,
                sort_enum,
                batch,
                continuation,
            )
            if rows:
                break
            if not _continuation_has_more(last_ct):
                return
            time.sleep(_RETRY_BASE_SLEEP * (attempt + 1))

        if not rows:
            return

        _merge_rows(rows, out, seen, target)
        pages += 1

        _notify_progress(
            progress_callback,
            len(out),
            progress_total_for_ui if target is not None else None,
            {"country": country_code, "page": pages, "phase": "download"},
        )

        if target is not None and len(out) >= target:
            return

        if not _continuation_has_more(last_ct):
            return

        continuation = last_ct
        time.sleep(_SLEEP_AFTER_PAGE)


def fetch_google_play_reviews(
    package_name: str,
    count: int = 100,
    lang: str = "en",
    country: str = "us",
    sort: str = "newest",
    progress_callback=None,
    should_continue=None,
) -> List[Dict[str, Any]]:
    """
    Collect up to `count` unique text reviews by paginating Play, rotating storefronts when needed.
    """
    Sort, reviews_fn, _, _ = _import_scraper()
    sort_enum = _sort_enum(sort, Sort)
    target = max(1, int(count))
    out: List[Dict[str, Any]] = []
    seen: set = set()

    for cc in _resolve_fetch_countries(country, limited=True):
        if len(out) >= target:
            break
        if should_continue and not should_continue():
            return _finalize_fetch_rows(out, sort, target=target, multi_country=False)

        _paginate_storefront(
            package_name=package_name,
            lang=lang,
            country_code=cc,
            sort_enum=sort_enum,
            reviews_fn=reviews_fn,
            target=target,
            out=out,
            seen=seen,
            page_batch=_PAGE_BATCH_LIMITED,
            max_pages=_MAX_PAGES_LIMITED_MODE,
            progress_callback=progress_callback,
            should_continue=should_continue,
            progress_total_for_ui=target,
        )

    countries = _resolve_fetch_countries(country, limited=True)
    return _finalize_fetch_rows(
        out,
        sort,
        target=target,
        multi_country=len(countries) > 1,
    )


def fetch_google_play_reviews_all(
    package_name: str,
    lang: str = "en",
    country: str = "us",
    sort: str = "newest",
    progress_callback=None,
    should_continue=None,
) -> List[Dict[str, Any]]:
    """
    Paginate every resolved storefront until Play reports no more pages.
    Avoids `reviews_all` (full-catalog pull) to prevent hangs and memory blowups.
    """
    Sort, reviews_fn, _, _ = _import_scraper()
    sort_enum = _sort_enum(sort, Sort)
    out: List[Dict[str, Any]] = []
    seen: set = set()

    countries = _resolve_fetch_countries(country, limited=False)
    for cc in countries:
        if should_continue and not should_continue():
            return _finalize_fetch_rows(out, sort, multi_country=len(countries) > 1)

        _paginate_storefront(
            package_name=package_name,
            lang=lang,
            country_code=cc,
            sort_enum=sort_enum,
            reviews_fn=reviews_fn,
            target=None,
            out=out,
            seen=seen,
            page_batch=_PAGE_BATCH_UNLIMITED,
            max_pages=_MAX_PAGES_UNLIMITED_MODE,
            progress_callback=progress_callback,
            should_continue=should_continue,
            progress_total_for_ui=0,
        )

    return _finalize_fetch_rows(out, sort, multi_country=len(countries) > 1)


def _play_item_to_app(item: Dict[str, Any]) -> Optional[Dict[str, str]]:
    return normalize_app_entry(
        {
            "appId": item.get("appId"),
            "title": item.get("title"),
            "icon": item.get("icon"),
            "developer": item.get("developer"),
        }
    )


def lookup_app_by_package(
    package_name: str, lang: str = "en", country: str = "us"
) -> Optional[Dict[str, str]]:
    pkg = (package_name or "").strip()
    if not pkg:
        return None

    cache_key = f"{pkg}|{lang}|{country}"
    cached = _cache_get(_PACKAGE_CACHE, cache_key)
    if cached is not None:
        return cached

    try:
        from google_play_scraper import app as play_app
    except Exception:
        return None

    try:
        detail = play_app(pkg, lang=lang, country=country)
    except Exception:
        _cache_set(_PACKAGE_CACHE, cache_key, None, _CACHE_MAX)
        return None

    norm = normalize_app_entry(
        {
            "appId": detail.get("appId") or pkg,
            "title": detail.get("title"),
            "icon": detail.get("icon"),
            "developer": detail.get("developer"),
        }
    )
    _cache_set(_PACKAGE_CACHE, cache_key, norm, _CACHE_MAX)
    return norm


def search_apps_play(query: str, limit: int = 12, lang: str = "en", country: str = "us") -> List[Dict[str, str]]:
    """Search Google Play and return normalized app rows."""
    if not query.strip():
        return []

    cache_key = f"{query.strip().lower()}|{limit}|{lang}|{country}"
    cached = _cache_get(_SEARCH_CACHE, cache_key)
    if cached is not None:
        return cached

    _, _, _, search = _import_scraper()
    requested = max(1, int(limit))

    countries = (
        ["us", "in", "gb", "pk", "de", "br"]
        if (country or "").lower() in ("", "ww", "global", "all", "world")
        else [country]
    )

    merged: List[Dict[str, Any]] = []
    seen_pkg = set()
    for cc in countries:
        try:
            pool = search(query, n_hits=max(20, requested * 3), lang=lang, country=cc)
        except Exception:
            continue
        for item in pool:
            pid = item.get("appId") or ""
            if not pid or pid in seen_pkg:
                continue
            seen_pkg.add(pid)
            merged.append(item)
        if len(merged) >= requested * 3:
            break

    apps: List[Dict[str, str]] = []
    seen_packages = set()
    for item in merged:
        norm = _play_item_to_app(item)
        if not norm:
            continue
        pkg = norm["package_name"]
        if pkg in seen_packages:
            continue
        seen_packages.add(pkg)
        apps.append(norm)

    ranked = rank_apps(query, apps, requested)
    _cache_set(_SEARCH_CACHE, cache_key, ranked, _CACHE_MAX)
    return ranked


def merge_and_rank_suggestions(
    local_results: List[Dict[str, str]],
    play_results: List[Dict[str, str]],
    query: str,
    limit: int,
) -> List[Dict[str, str]]:
    requested = max(1, int(limit))
    combined: List[Dict[str, str]] = []
    seen = set()

    for app in local_results + play_results:
        norm = normalize_app_entry(app)
        if not norm:
            continue
        pkg = norm["package_name"]
        if pkg in seen:
            continue
        seen.add(pkg)
        combined.append(norm)

    return rank_apps(query, combined, requested)


def search_apps(query: str, limit: int = 12, lang: str = "en", country: str = "us") -> List[Dict[str, str]]:
    """Play-only search (used by merge path and tests)."""
    return search_apps_play(query, limit=limit, lang=lang, country=country)
