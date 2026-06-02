"""Build data/app_catalog.json (2500+ apps) via Google Play search seeds."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.app_catalog import catalog_path, normalize_app_entry

TARGET_COUNT = 2500
OUTPUT_PATH = catalog_path()


def _seed_queries() -> list[str]:
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
        "careem",
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
    # Two-letter combos for broader coverage
    letters = "abcdefghijklmnopqrstuvwxyz"
    combos = [a + b for a in letters for b in letters[:8]]
    return bases + combos


def build_catalog() -> dict:
    from google_play_scraper import search

    queries = _seed_queries()
    by_pkg: dict[str, dict] = {}

    for i, q in enumerate(queries):
        if len(by_pkg) >= TARGET_COUNT:
            break
        try:
            hits = search(q, n_hits=30, lang="en", country="us")
        except Exception as exc:
            print(f"skip seed {q!r}: {exc}")
            time.sleep(0.3)
            continue

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
            if not prev or len(norm.get("app_name") or "") > len(prev.get("app_name") or ""):
                by_pkg[pkg] = norm

        if (i + 1) % 25 == 0:
            print(f"progress: {i + 1}/{len(queries)} seeds, {len(by_pkg)} apps")
        time.sleep(0.15)

    apps = sorted(by_pkg.values(), key=lambda x: x["app_name"].lower())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(apps),
        "apps": apps,
    }


def main():
    payload = build_catalog()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {payload['count']} apps to {OUTPUT_PATH}")
    if payload["count"] < TARGET_COUNT:
        print(f"Warning: target was {TARGET_COUNT}+ apps; re-run to grow catalog.")
        sys.exit(1)


if __name__ == "__main__":
    main()
