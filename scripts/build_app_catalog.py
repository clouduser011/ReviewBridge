"""Build data/app_catalog.json (6200+ apps, Pakistan-focused) via Google Play search seeds."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.app_catalog import catalog_path, normalize_app_entry

DEFAULT_TARGET = 6200
BOOTSTRAP_SEARCH_SKIP_THRESHOLD = 3000
OUTPUT_PATH = catalog_path()
BUILD_STATE_PATH = OUTPUT_PATH.parent / "app_catalog.build_state.json"
PROGRESS_PATH = OUTPUT_PATH.parent / "catalog_build.progress.json"
PK_PRIORITY_PATH = OUTPUT_PATH.parent / "pk_priority_apps.json"
BUILD_COUNTRIES = ("pk", "in", "us")
N_HITS = 50
SEARCH_TIMEOUT = 30.0


def _log(message: str) -> None:
    line = f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {message}"
    print(line, flush=True)


def _pk_seed_queries() -> list[str]:
    return [
        "sadapay",
        "nayapay",
        "jazzcash",
        "easypaisa",
        "finja",
        "sada pay",
        "naya pay",
        "microfinance",
        "jazz",
        "zong",
        "ufone",
        "telenor",
        "ptcl",
        "nayatel",
        "jazz world",
        "bykea",
        "indrive",
        "careem",
        "foodpanda",
        "cheetay",
        "kravemart",
        "go ride",
        "daraz",
        "telemart",
        "olx",
        "pakwheels",
        "priceoye",
        "homeshopping",
        "tapmad",
        "tamasha",
        "ary zapp",
        "geo news",
        "dunya news",
        "express news",
        "jazz tv",
        "nearpeer",
        "tabir",
        "maqsad",
        "sabaq",
        "ilm ki dunya",
        "epay punjab",
        "kpk",
        "sindh",
        "lesco",
        "ssgc",
        "sngpl",
        "fbr",
        "nadra",
        "ubl",
        "hbl",
        "meezan",
        "mcb",
        "alfalah",
        "faysal",
        "askari",
        "standard chartered",
        "bank islami",
        "ludo star",
        "pubg",
        "free fire",
        "cricket game",
        "cricket league",
        "pizza hut pakistan",
        "kfc pakistan",
        "mcdonalds pakistan",
        "dominos pakistan",
        "airlift",
        "panda mart",
        "metro online",
        "imtiaz",
        "al fatah",
        "hyperstar",
        "utility store",
        "pakistan",
        "pakistani",
        "lahore",
        "karachi",
        "islamabad",
        "rawalpindi",
        "faisalabad",
        "multan",
        "peshawar",
        "quetta",
        "sialkot",
        "gujranwala",
        "hyderabad pakistan",
        "islamic banking",
        "mobile account",
        "digital wallet",
        "bill payment",
        "electricity bill",
        "gas bill",
        "water bill",
        "traffic challan",
        "driving license",
        "vehicle verification",
        "property tax",
        "school app",
        "university pakistan",
        "lms pakistan",
        "matric",
        "fsc",
        "mdcat",
        "ecat",
        "css pakistan",
        "pms pakistan",
        "typing tutor urdu",
        "quran pakistan",
        "prayer times pakistan",
        "ramadan pakistan",
        "eid",
        "bazaar",
        "sasta",
        "discount pakistan",
    ]


def _global_seed_queries() -> list[str]:
    bases = [
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "i",
        "j",
        "k",
        "l",
        "m",
        "n",
        "o",
        "p",
        "q",
        "r",
        "s",
        "t",
        "u",
        "v",
        "w",
        "x",
        "y",
        "z",
        "game",
        "games",
        "photo",
        "video",
        "music",
        "chat",
        "messenger",
        "social",
        "bank",
        "pay",
        "wallet",
        "shop",
        "store",
        "food",
        "delivery",
        "travel",
        "map",
        "taxi",
        "ride",
        "fitness",
        "health",
        "news",
        "weather",
        "browser",
        "vpn",
        "camera",
        "editor",
        "pdf",
        "office",
        "email",
        "calendar",
        "notes",
        "learn",
        "education",
        "kids",
        "dating",
        "sports",
        "football",
        "cricket",
        "puzzle",
        "racing",
        "simulator",
        "strategy",
        "action",
        "adventure",
        "arcade",
        "casual",
        "board",
        "card",
        "whatsapp",
        "instagram",
        "facebook",
        "youtube",
        "tiktok",
        "snapchat",
        "twitter",
        "telegram",
        "spotify",
        "netflix",
        "amazon",
        "flipkart",
        "uber",
        "ola",
        "paypal",
        "google",
        "microsoft",
        "samsung",
        "huawei",
        "xiaomi",
        "oppo",
        "vivo",
        "realme",
        "paytm",
        "phonepe",
        "gpay",
        "zoom",
        "teams",
        "slack",
        "discord",
        "reddit",
        "pinterest",
        "linkedin",
        "booking",
        "airbnb",
        "swiggy",
        "zomato",
        "dominos",
        "mcdonalds",
        "starbucks",
        "walmart",
        "ebay",
        "aliexpress",
        "shein",
        "temu",
        "shopee",
        "lazada",
        "mercado",
        "rappi",
        "grab",
        "gojek",
        "bolt",
        "lyft",
        "duolingo",
        "canva",
        "capcut",
        "picsart",
        "lightroom",
        "shazam",
        "soundcloud",
        "deezer",
        "twitch",
        "roblox",
        "minecraft",
        "pubg",
        "free fire",
        "call of duty",
        "clash",
        "candy crush",
        "subway surfers",
        "temple run",
        "among us",
        "brawl stars",
    ]
    letters = "abcdefghijklmnopqrstuvwxyz"
    combos = [a + b for a in letters for b in letters]
    return bases + combos


def seed_queries() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in _pk_seed_queries() + _global_seed_queries():
        key = q.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _seed_key(query: str, country: str) -> str:
    return f"{country}:{query}"


def _load_existing_apps() -> dict[str, dict]:
    if not OUTPUT_PATH.is_file():
        return {}
    try:
        raw = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _log(f"Warning: could not read existing catalog: {exc}")
        return {}
    items = raw.get("apps") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return {}
    by_pkg: dict[str, dict] = {}
    for item in items:
        norm = normalize_app_entry(item)
        if not norm:
            continue
        pkg = norm["package_name"]
        prev = by_pkg.get(pkg)
        if not prev or len(norm.get("app_name") or "") > len(prev.get("app_name") or ""):
            by_pkg[pkg] = norm
    return by_pkg


def _load_build_state() -> dict[str, Any]:
    if not BUILD_STATE_PATH.is_file():
        return {}
    try:
        return json.loads(BUILD_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_build_state(state: dict[str, Any]) -> None:
    BUILD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = BUILD_STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(BUILD_STATE_PATH)


def _write_progress(*, seed_index: int, seeds_total: int, apps: int, target_count: int, seeds_completed: int) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "seed_index": seed_index,
        "seeds_total": seeds_total,
        "seeds_completed": seeds_completed,
        "apps": apps,
        "target_count": target_count,
        "apps_remaining": max(0, target_count - apps),
    }
    try:
        tmp = PROGRESS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(PROGRESS_PATH)
    except OSError:
        pass


def _payload(
    apps: list[dict],
    target_count: int,
    seeds_completed: int,
    seeds_total: int,
) -> dict[str, Any]:
    sorted_apps = sorted(apps, key=lambda x: x["app_name"].lower())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_count": target_count,
        "count": len(sorted_apps),
        "build": {
            "seeds_completed": seeds_completed,
            "seeds_total": seeds_total,
            "countries": list(BUILD_COUNTRIES),
            "pk_focus": True,
        },
        "apps": sorted_apps,
    }


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def _merge_hits(by_pkg: dict[str, dict], hits: list) -> int:
    added = 0
    for item in hits:
        norm = normalize_app_entry(
            {
                "appId": item.get("appId"),
                "title": item.get("title"),
                "icon": item.get("icon"),
                "developer": item.get("developer"),
            }
        )
        if not norm:
            continue
        pkg = norm["package_name"]
        prev = by_pkg.get(pkg)
        if prev:
            if len(norm.get("app_name") or "") > len(prev.get("app_name") or ""):
                by_pkg[pkg] = norm
            continue
        by_pkg[pkg] = norm
        added += 1
    return added


def _play_search(query: str, country: str, n_hits: int = N_HITS, timeout: float = SEARCH_TIMEOUT) -> list:
    from google_play_scraper import search

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(search, query, n_hits=n_hits, lang="en", country=country)
        try:
            return future.result(timeout=timeout) or []
        except FuturesTimeout:
            _log(f"timeout seed {query!r} ({country})")
            return []
        except Exception as exc:
            _log(f"skip seed {query!r} ({country}): {exc}")
            return []


def _lookup_package(pkg: str, timeout: float = 15.0) -> dict | None:
    from app.google_play import lookup_app_by_package

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lookup_app_by_package, pkg, lang="en", country="pk")
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout:
            _log(f"timeout package lookup {pkg!r}")
            return None
        except Exception as exc:
            _log(f"skip package lookup {pkg!r}: {exc}")
            return None


def _bootstrap_pk_priority(by_pkg: dict[str, dict], *, skip_search_terms: bool = False) -> int:
    if not PK_PRIORITY_PATH.is_file():
        _log("No pk_priority_apps.json found; skipping priority bootstrap")
        return 0

    try:
        raw = json.loads(PK_PRIORITY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _log(f"Warning: could not read pk_priority_apps.json: {exc}")
        return 0

    if skip_search_terms:
        _log(f"PK priority bootstrap skipped (catalog already {len(by_pkg)} apps)")
        return 0

    added = 0
    packages = raw.get("packages") or []
    for pkg in packages:
        pkg = (pkg or "").strip()
        if not pkg or pkg in by_pkg:
            continue
        norm = _lookup_package(pkg)
        if not norm:
            continue
        by_pkg[norm["package_name"]] = norm
        added += 1
        _log(f"priority package: {norm.get('app_name')} ({norm.get('package_name')})")
        time.sleep(0.05)

    for term in raw.get("search_terms") or []:
        term = (term or "").strip().lower()
        if not term:
            continue
        hits = _play_search(term, "pk")
        added += _merge_hits(by_pkg, hits)
        time.sleep(0.05)

    _log(f"PK priority bootstrap added {added} apps (total {len(by_pkg)})")
    return added


def _maybe_checkpoint(
    by_pkg: dict[str, dict],
    *,
    target_count: int,
    seeds_completed: int,
    seeds_total: int,
    seeds_done: Set[str],
    last_checkpoint_bucket: int,
    checkpoint_every: int,
    force: bool = False,
) -> int:
    if checkpoint_every <= 0:
        return last_checkpoint_bucket
    bucket = seeds_completed // checkpoint_every
    if not force and bucket <= last_checkpoint_bucket:
        return last_checkpoint_bucket

    payload = _payload(list(by_pkg.values()), target_count, seeds_completed, seeds_total)
    _atomic_write(OUTPUT_PATH, payload)
    _save_build_state(
        {
            "target_count": target_count,
            "seeds_done": sorted(seeds_done),
            "last_checkpoint": datetime.now(timezone.utc).isoformat(),
            "count": len(by_pkg),
        }
    )
    _log(f"checkpoint: saved {len(by_pkg)} apps to disk")
    return bucket if bucket > last_checkpoint_bucket else last_checkpoint_bucket


def build_catalog(
    target_count: int = DEFAULT_TARGET,
    resume: bool = True,
    checkpoint_every: int = 25,
    sleep_seconds: float = 0.15,
) -> tuple[dict[str, Any], bool, list[str]]:
    queries = seed_queries()
    seeds_total = len(queries)
    by_pkg = _load_existing_apps() if resume else {}
    build_state = _load_build_state() if resume else {}
    seeds_done: Set[str] = set(build_state.get("seeds_done") or [])

    _log(f"Starting with {len(by_pkg)} apps on disk")
    skip_bootstrap_search = resume and len(by_pkg) >= BOOTSTRAP_SEARCH_SKIP_THRESHOLD
    _bootstrap_pk_priority(by_pkg, skip_search_terms=skip_bootstrap_search)
    if len(by_pkg) > len(_load_existing_apps() if resume else {}):
        payload = _payload(list(by_pkg.values()), target_count, len(seeds_done), seeds_total)
        _atomic_write(OUTPUT_PATH, payload)
        _log(f"Saved after PK bootstrap: {len(by_pkg)} apps")

    if resume and seeds_done:
        _log(f"Resuming with {len(seeds_done)} seed-country pairs already done")

    seeds_completed = len(seeds_done)
    last_checkpoint_bucket = seeds_completed // checkpoint_every if checkpoint_every > 0 else 0
    _write_progress(
        seed_index=seeds_completed,
        seeds_total=seeds_total,
        apps=len(by_pkg),
        target_count=target_count,
        seeds_completed=seeds_completed,
    )

    for i, q in enumerate(queries):
        if len(by_pkg) >= target_count:
            break

        added_total = 0
        for country in BUILD_COUNTRIES:
            if len(by_pkg) >= target_count:
                break

            key = _seed_key(q, country)
            if resume and key in seeds_done:
                continue

            hits = _play_search(q, country)
            added = _merge_hits(by_pkg, hits)
            added_total += added
            seeds_done.add(key)
            seeds_completed = len(seeds_done)
            time.sleep(sleep_seconds)

            if added_total >= 12:
                break

        _write_progress(
            seed_index=i + 1,
            seeds_total=seeds_total,
            apps=len(by_pkg),
            target_count=target_count,
            seeds_completed=seeds_completed,
        )

        if (i + 1) % 10 == 0 or added_total >= 10:
            _log(
                f"progress: seed {i + 1}/{seeds_total}, "
                f"{len(by_pkg)} apps (+{added_total} this seed), "
                f"{seeds_completed} pairs done"
            )

        last_checkpoint_bucket = _maybe_checkpoint(
            by_pkg,
            target_count=target_count,
            seeds_completed=seeds_completed,
            seeds_total=seeds_total,
            seeds_done=seeds_done,
            last_checkpoint_bucket=last_checkpoint_bucket,
            checkpoint_every=checkpoint_every,
            force=(i + 1) % 5 == 0,
        )

    apps = list(by_pkg.values())
    payload = _payload(apps, target_count, seeds_completed, seeds_total)
    reached = len(apps) >= target_count
    return payload, reached, sorted(seeds_done)


def show_build_status() -> int:
    disk_count = 0
    target_count = DEFAULT_TARGET
    if OUTPUT_PATH.is_file():
        try:
            raw = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            disk_count = int(raw.get("count") or len(raw.get("apps") or []))
            target_count = int(raw.get("target_count") or DEFAULT_TARGET)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    state = _load_build_state()
    progress = {}
    if PROGRESS_PATH.is_file():
        try:
            progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            progress = {}

    _log("--- Catalog build status ---")
    _log(f"On disk: {disk_count} apps (target {target_count})")
    _log(f"Resume state: {len(state.get('seeds_done') or [])} seed-country pairs completed")
    if progress:
        _log(
            f"Last progress: seed {progress.get('seed_index')}/{progress.get('seeds_total')}, "
            f"{progress.get('apps')} apps at {str(progress.get('updated_at', ''))[:19]}"
        )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Pakistan-focused local app catalog.")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET, help="Target unique app count")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--fresh", action="store_true", help="Ignore existing catalog and build state")
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--status", action="store_true", help="Show build progress and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.status:
        return show_build_status()

    resume = args.resume and not args.fresh
    if args.fresh:
        BUILD_STATE_PATH.unlink(missing_ok=True)
        PROGRESS_PATH.unlink(missing_ok=True)
        _log("Fresh build: ignoring existing catalog state")

    _log(f"Target: {args.target}+ apps ({len(seed_queries())} seeds, countries={BUILD_COUNTRIES})")
    payload, reached, seeds_done = build_catalog(
        target_count=args.target,
        resume=resume,
        checkpoint_every=args.checkpoint_every,
        sleep_seconds=args.sleep,
    )

    _atomic_write(OUTPUT_PATH, payload)
    _save_build_state(
        {
            "target_count": args.target,
            "seeds_done": seeds_done,
            "last_checkpoint": datetime.now(timezone.utc).isoformat(),
            "count": payload["count"],
            "complete": reached,
        }
    )

    _log(f"Wrote {payload['count']} apps to {OUTPUT_PATH}")
    if not reached:
        _log(f"Warning: target was {args.target}+ (got {payload['count']}). Re-run with --resume.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
