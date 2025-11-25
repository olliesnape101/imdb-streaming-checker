import os
import json
import sqlite3
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TMDB_API_KEY")

DB_PATH = "cache.db"


# ============================================================
# 1. Initialize SQLite Database
# ============================================================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS film_cache (
            imdb_id TEXT PRIMARY KEY,
            tmdb_id INTEGER,
            providers_json TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()


# ============================================================
# 2. SQL Cache Helpers (replace JSON file cache)
# ============================================================

def sql_load(imdb_id):
    """Load TMDb ID + providers info for a film from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT tmdb_id, providers_json FROM film_cache WHERE imdb_id = ?",
        (imdb_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    tmdb_id, providers_json = row
    providers_block = json.loads(providers_json) if providers_json else {}

    return {
        "tmdb_id": tmdb_id,
        "providers": providers_block
    }


def sql_save(imdb_id, data):
    """Insert or update film cache entry in SQLite."""
    tmdb_id = data.get("tmdb_id")
    providers_block = data.get("providers", {})

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO film_cache (imdb_id, tmdb_id, providers_json) "
        "VALUES (?, ?, ?)",
        (imdb_id, tmdb_id, json.dumps(providers_block))
    )
    conn.commit()
    conn.close()


def sql_delete(imdb_id):
    """Delete a single film's cache entry (used by app.py)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM film_cache WHERE imdb_id = ?", (imdb_id,))
    conn.commit()
    conn.close()


# ============================================================
# IMDb Title Type → TMDb media type mapping
# ============================================================

def imdb_type_to_tmdb_type(imdb_type):
    imdb_type = imdb_type.lower().strip()

    movie_types = {"movie", "short", "video", "tvmovie"}
    tv_types = {"tvseries", "tvminiseries", "tvepisode", "tvspecial"}

    if imdb_type in movie_types:
        return "movie"
    if imdb_type in tv_types:
        return "tv"

    if "tv" in imdb_type:
        return "tv"
    return "movie"


# ============================================================
# TMDb Find Endpoint → Get TMDb ID
# ============================================================

def get_tmdb_id(imdb_id):
    url = (
        f"https://api.themoviedb.org/3/find/{imdb_id}"
        f"?api_key={API_KEY}&external_source=imdb_id"
    )
    r = requests.get(url).json()

    movie_results = r.get("movie_results", [])
    tv_results = r.get("tv_results", [])

    if movie_results:
        return movie_results[0]["id"]
    if tv_results:
        return tv_results[0]["id"]

    return None


# ============================================================
# TMDb Provider Lookup
# ============================================================

def get_watch_providers(tmdb_id, media_type, region):
    if tmdb_id is None:
        return []

    url = (
        f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/watch/providers"
        f"?api_key={API_KEY}"
    )
    r = requests.get(url).json()

    try:
        providers = r["results"][region]["flatrate"]
        return [p["provider_name"] for p in providers]
    except Exception:
        return []


# ============================================================
# Helpers for New/Old Cache Schemas
# ============================================================

def _extract_entry(entry):
    """
    Accepts either:

    Old format:
        ["Netflix", "MUBI"]

    New format:
        {
            "last_updated": "2025-01-12",
            "names": ["Netflix", "MUBI"]
        }
    """
    if entry is None:
        return None, []

    if isinstance(entry, list):
        return None, entry

    if isinstance(entry, dict):
        return entry.get("last_updated"), entry.get("names", [])

    return None, []


# ============================================================
# Public API — Cached Providers
# ============================================================

def get_providers_cached(imdb_id, regions):
    cached = sql_load(imdb_id)

    if not cached:
        return {
            "tmdb_id": None,
            "providers": {region: [] for region in regions}
        }

    providers_block = cached.get("providers", {})
    out = {}

    for region in regions:
        entry = providers_block.get(region)
        _, names = _extract_entry(entry)
        out[region] = names

    return {
        "tmdb_id": cached.get("tmdb_id"),
        "providers": out
    }


# ============================================================
# Public API — Fresh Providers
# ============================================================

def get_providers_fresh(imdb_id, imdb_type, regions, today_str):
    cached = sql_load(imdb_id) or {}
    tmdb_id = cached.get("tmdb_id")
    providers_block = cached.get("providers", {})

    # Determine if we need the TMDb ID at all
    need_any_fetch = False
    for region in regions:
        entry = providers_block.get(region)
        last_updated, _ = _extract_entry(entry)
        if last_updated != today_str:
            need_any_fetch = True
            break

    if need_any_fetch and tmdb_id is None:
        tmdb_id = get_tmdb_id(imdb_id)
        cached["tmdb_id"] = tmdb_id

    media_type = imdb_type_to_tmdb_type(imdb_type)
    results = {}

    for region in regions:
        entry = providers_block.get(region)
        last_updated, names = _extract_entry(entry)

        if last_updated == today_str:
            results[region] = names
            continue

        if tmdb_id is None:
            names = []
        else:
            names = get_watch_providers(tmdb_id, media_type, region)

        providers_block[region] = {
            "last_updated": today_str,
            "names": names
        }
        results[region] = names

    cached["providers"] = providers_block
    sql_save(imdb_id, cached)

    return {
        "tmdb_id": tmdb_id,
        "providers": results
    }

