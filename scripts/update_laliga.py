#!/usr/bin/env python3
"""Refresh the current LaLiga season and rebuild the standalone dashboard.

Live mode uses football-data.org v4 and expects FOOTBALL_DATA_TOKEN.
Offline mode rebuilds from data/current_snapshot.json without network access.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MATCHES_CSV = DATA_DIR / "laliga_matches.csv"
STATIC_JSON = DATA_DIR / "static_data.json"
PLAYER_JSON = DATA_DIR / "player_data.json"
SNAPSHOT_JSON = DATA_DIR / "current_snapshot.json"
SEASON_STATS_JSON = DATA_DIR / "season_stats.json"
TEMPLATE_DIR = ROOT / "template_parts"
OUTPUT_HTML = ROOT / "index.html"
CONFIG_JSON = ROOT / "config.json"

# Canonical club identities used across historical archives, recent CSV sources,
# the live API, selectors and H2H. Only genuine naming variants of the same club
# are merged here; predecessor clubs remain distinct.
ALIASES = {
    # Historical engsoccerdata names
    "Athletic Bilbao": "Athletic Club",
    "Athletic": "Athletic Club",
    "Atletico Madrid": "Atlético Madrid",
    "CD Alaves": "Deportivo Alavés",
    "CD Leganes": "CD Leganés",
    "Cadiz CF": "Cádiz CF",
    "Espanyol Barcelona": "RCD Espanyol",
    "Girona": "Girona FC",
    "UD Almeria": "UD Almería",
    "Sporting Gijon": "Sporting Gijón",
    "Malaga CF": "Málaga CF",
    "Deportivo La Coruna": "RC Deportivo",
    # football-data.co.uk / common short names
    "Alaves": "Deportivo Alavés",
    "Ath Bilbao": "Athletic Club",
    "Ath Madrid": "Atlético Madrid",
    "Barcelona": "FC Barcelona",
    "Barça": "FC Barcelona",
    "Barca": "FC Barcelona",
    "Betis": "Real Betis",
    "Celta": "Celta Vigo",
    "Elche": "Elche CF",
    "Espanol": "RCD Espanyol",
    "Getafe": "Getafe CF",
    "Levante": "Levante UD",
    "Mallorca": "RCD Mallorca",
    "Osasuna": "CA Osasuna",
    "Oviedo": "Real Oviedo",
    "Vallecano": "Rayo Vallecano",
    "Sociedad": "Real Sociedad",
    "Sevilla": "Sevilla FC",
    "Valencia": "Valencia CF",
    "Villarreal": "Villarreal CF",
    # football-data.org names
    "Real Madrid CF": "Real Madrid",
    "Club Atlético de Madrid": "Atlético Madrid",
    "Atlético de Madrid": "Atlético Madrid",
    "Real Sociedad de Fútbol": "Real Sociedad",
    "Real Betis Balompié": "Real Betis",
    "RC Celta de Vigo": "Celta Vigo",
    "Celta de Vigo": "Celta Vigo",
    "Rayo Vallecano de Madrid": "Rayo Vallecano",
    "RCD Espanyol de Barcelona": "RCD Espanyol",
    "Reial Club Deportiu Espanyol": "RCD Espanyol",
    "Deportivo Alavés": "Deportivo Alavés",
    "Deportivo Alavés SAD": "Deportivo Alavés",
    "Real Racing Club de Santander": "Racing Santander",
    "Racing Club de Santander": "Racing Santander",
    "RC Deportivo La Coruña": "RC Deportivo",
    "RC Deportivo de La Coruña": "RC Deportivo",
    "Deportivo de La Coruña": "RC Deportivo",
    "Málaga CF": "Málaga CF",
}

CSV_FIELDS = [
    "season", "date", "home", "away", "home_goals", "away_goals",
    "ht_home_goals", "ht_away_goals", "home_shots", "away_shots",
    "home_sot", "away_sot", "home_fouls", "away_fouls",
    "home_corners", "away_corners", "home_yellow", "away_yellow",
    "home_red", "away_red",
]

COMPACT = {
    "date": "d", "home": "h", "away": "a", "home_goals": "hg", "away_goals": "ag",
    "ht_home_goals": "hhg", "ht_away_goals": "hag", "home_shots": "hs", "away_shots": "as",
    "home_sot": "hst", "away_sot": "ast", "home_fouls": "hf", "away_fouls": "af",
    "home_corners": "hc", "away_corners": "ac", "home_yellow": "hy", "away_yellow": "ay",
    "home_red": "hr", "away_red": "ar",
}

INT_FIELDS = set(COMPACT) - {"date", "home", "away"}


def load_config() -> dict:
    return json.loads(CONFIG_JSON.read_text(encoding="utf-8"))


def canonical_team(name: str, short_name: str | None = None) -> str:
    name = (name or "").strip()
    short_name = (short_name or "").strip() or None
    # Prefer the API's full club name. Falling back to shortName caused
    # display values such as "Barça" and "Athletic" to leak into fixtures.
    if name:
        return ALIASES.get(name, name)
    if short_name:
        return ALIASES.get(short_name, short_name)
    return ""


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Madrid"))


def fetch_live(config: dict) -> dict:
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        raise RuntimeError("FOOTBALL_DATA_TOKEN is required for live refresh")
    season_start = config["apiSeasonStartYear"]
    url = f"https://api.football-data.org/v4/competitions/PD/matches?season={season_start}"
    req = urllib.request.Request(url, headers={"X-Auth-Token": token, "User-Agent": "laliga-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)

    finished = []
    upcoming = []
    teams = set()
    for item in payload.get("matches", []):
        home_obj, away_obj = item.get("homeTeam", {}), item.get("awayTeam", {})
        home = canonical_team(home_obj.get("name", ""), home_obj.get("shortName"))
        away = canonical_team(away_obj.get("name", ""), away_obj.get("shortName"))
        if not home or not away:
            continue
        teams.update((home, away))
        dt = parse_utc(item["utcDate"])
        score = item.get("score") or {}
        status = item.get("status", "SCHEDULED")
        refs = item.get("referees") or []
        referee = refs[0].get("name", "") if refs else ""
        if status == "FINISHED" and score.get("fullTime", {}).get("home") is not None:
            ft = score["fullTime"]
            ht = score.get("halfTime") or {}
            finished.append({
                "id": item.get("id"), "date": dt.date().isoformat(), "home": home, "away": away,
                "home_goals": ft.get("home"), "away_goals": ft.get("away"),
                "ht_home_goals": ht.get("home"), "ht_away_goals": ht.get("away"),
            })
        elif status not in {"CANCELLED"}:
            upcoming.append({
                "id": item.get("id"), "date": dt.date().isoformat(), "time": dt.strftime("%H:%M"),
                "home": home, "away": away, "referee": referee, "status": status,
                "matchday": item.get("matchday"),
            })

    upcoming.sort(key=lambda x: (x["date"], x["time"], x["home"]))
    finished.sort(key=lambda x: (x["date"], x["home"]))
    return {
        "season": config["currentSeason"], "apiSeason": season_start,
        "teams": sorted(teams), "fixtures": upcoming, "finished": finished,
        "source": "football-data.org v4 / competitions/PD/matches",
        "updatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def normalize_snapshot(snapshot: dict) -> dict:
    out = dict(snapshot)
    out["teams"] = sorted({canonical_team(t) for t in snapshot.get("teams", []) if canonical_team(t)})
    for key in ("fixtures", "finished"):
        cooked = []
        for item in snapshot.get(key, []):
            row = dict(item)
            row["home"] = canonical_team(row.get("home", ""))
            row["away"] = canonical_team(row.get("away", ""))
            cooked.append(row)
        out[key] = cooked
    return out


def read_rows() -> list[dict]:
    # Normalize the full archive every time it is read. This repairs legacy rows
    # already committed under old club names and keeps H2H/team selectors unified.
    with MATCHES_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["home"] = canonical_team(row.get("home", ""))
        row["away"] = canonical_team(row.get("away", ""))
    return rows


def write_rows(rows: list[dict]) -> None:
    with MATCHES_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in CSV_FIELDS})


def result_pair(row: dict) -> tuple[str, str]:
    return (canonical_team(row.get("home", "")), canonical_team(row.get("away", "")))


def reconcile_finished(snapshot: dict, rows: list[dict], season: str) -> dict:
    """Make FINISHED monotonic across refreshes.

    football-data.org can occasionally regress an already-finished match to
    TIMED/IN_PLAY on a later bulk response. Once we have persisted a completed
    league match, keep it completed unless a later FINISHED payload supplies a
    correction. A live FINISHED payload always wins over the archived score.
    """
    finished_by_pair: dict[tuple[str, str], dict] = {}
    for row in rows:
        if row.get("season") != season:
            continue
        if row.get("home_goals") in (None, "") or row.get("away_goals") in (None, ""):
            continue
        key = result_pair(row)
        if not all(key):
            continue
        finished_by_pair[key] = {
            "id": None,
            "date": row.get("date", ""),
            "home": key[0],
            "away": key[1],
            "home_goals": int(float(row["home_goals"])),
            "away_goals": int(float(row["away_goals"])),
            "ht_home_goals": None if row.get("ht_home_goals") in (None, "") else int(float(row["ht_home_goals"])),
            "ht_away_goals": None if row.get("ht_away_goals") in (None, "") else int(float(row["ht_away_goals"])),
        }

    # Fresh FINISHED data is authoritative for corrections.
    for match in snapshot.get("finished", []):
        key = result_pair(match)
        if all(key):
            finished_by_pair[key] = dict(match)

    completed_pairs = set(finished_by_pair)
    fixtures = [f for f in snapshot.get("fixtures", []) if result_pair(f) not in completed_pairs]
    fixtures.sort(key=lambda x: (x.get("date", ""), x.get("time", ""), x.get("home", "")))
    finished = list(finished_by_pair.values())
    finished.sort(key=lambda x: (x.get("date", ""), x.get("home", ""), x.get("away", "")))

    out = dict(snapshot)
    out["fixtures"] = fixtures
    out["finished"] = finished
    return out


def merge_current(rows: list[dict], snapshot: dict, season: str) -> list[dict]:
    # Preserve previously confirmed current-season results. Fresh FINISHED rows
    # overwrite the same home/away pairing, allowing score corrections without
    # allowing an API status regression to delete a completed match.
    base = [r for r in rows if r.get("season") != season]
    current_by_pair = {
        result_pair(r): dict(r)
        for r in rows
        if r.get("season") == season and all(result_pair(r))
    }
    for m in snapshot.get("finished", []):
        row = {k: "" for k in CSV_FIELDS}
        row.update({
            "season": season, "date": m["date"], "home": m["home"], "away": m["away"],
            "home_goals": m["home_goals"], "away_goals": m["away_goals"],
            "ht_home_goals": "" if m.get("ht_home_goals") is None else m["ht_home_goals"],
            "ht_away_goals": "" if m.get("ht_away_goals") is None else m["ht_away_goals"],
        })
        current_by_pair[result_pair(row)] = row
    current = list(current_by_pair.values())
    current.sort(key=lambda r: (r["date"], r["home"], r["away"]))
    return base + current


def number(value: str):
    if value in (None, ""):
        return None
    return int(float(value))


def compact_row(row: dict) -> dict:
    out = {}
    for src, dst in COMPACT.items():
        value = row.get(src, "")
        if value in (None, ""):
            continue
        out[dst] = number(value) if src in INT_FIELDS else value
    hg, ag = out["hg"], out["ag"]
    out["r"] = "H" if hg > ag else "A" if ag > hg else "D"
    # Keep result near the score fields for readability/stability.
    ordered = {}
    for key in ("d", "h", "a", "hg", "ag", "r", "hhg", "hag", "hs", "as", "hst", "ast", "hf", "af", "hc", "ac", "hy", "ay", "hr", "ar"):
        if key in out:
            ordered[key] = out[key]
    return ordered


def load_player_payload() -> dict:
    if not PLAYER_JSON.exists():
        return {}
    try:
        return json.loads(PLAYER_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"WARNING: player_data.json could not be loaded: {exc}", file=sys.stderr)
        return {}


def load_season_stats() -> dict:
    if not SEASON_STATS_JSON.exists():
        return {"seasons": {}}
    try:
        payload = json.loads(SEASON_STATS_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"WARNING: season_stats.json could not be loaded: {exc}", file=sys.stderr)
        return {"seasons": {}}
    payload.setdefault("seasons", {})
    return payload


def build_data(rows: list[dict], snapshot: dict, static: dict, config: dict) -> dict:
    seasons = defaultdict(list)
    for row in rows:
        seasons[row["season"]].append(compact_row(row))
    for matches in seasons.values():
        matches.sort(key=lambda m: (m["d"], m["h"], m["a"]))

    current_season = config["currentSeason"]
    seasons.setdefault(current_season, [])
    meta = dict(static["meta"])
    meta["historicalMatches"] = len(rows)
    meta["updatedAt"] = snapshot.get("updatedAt")
    meta["currentSeason"] = current_season
    meta["currentFinishedMatches"] = len(seasons[current_season])
    current_teams = snapshot.get("teams") or static["currentTeams"]
    player_payload = load_player_payload()
    season_stats = load_season_stats()
    return {
        "seasons": dict(seasons),
        "currentTeams": current_teams,
        "fixtures": snapshot.get("fixtures", []),
        "seasonStats": season_stats,
        # Keep the legacy two-season object for backwards compatibility, while
        # the redesigned Players view consumes the richer profile catalogue.
        "players": static["players"],
        "playerProfiles": player_payload.get("players", {}),
        "playerMeta": {
            "source": player_payload.get("source"),
            "coverage": player_payload.get("coverage"),
            "updatedAt": player_payload.get("updatedAt"),
        },
        "champions": static["champions"],
        "meta": meta,
    }


def render_dashboard(data: dict, updated_at: str) -> None:
    parts = sorted(TEMPLATE_DIR.glob("part*.html"))
    if not parts:
        raise RuntimeError("template_parts are missing")
    template = "".join(p.read_text(encoding="utf-8") for p in parts)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if "__DATA_JSON__" not in template:
        raise RuntimeError("dashboard_template.html is missing __DATA_JSON__ placeholder")
    html = template.replace("__DATA_JSON__", payload).replace("__LAST_UPDATED__", updated_at)
    OUTPUT_HTML.write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Use data/current_snapshot.json instead of the API")
    args = parser.parse_args()
    config = load_config()
    static = json.loads(STATIC_JSON.read_text(encoding="utf-8"))
    if args.offline:
        snapshot = json.loads(SNAPSHOT_JSON.read_text(encoding="utf-8"))
    else:
        snapshot = fetch_live(config)
    snapshot = normalize_snapshot(snapshot)
    existing_rows = read_rows()
    snapshot = reconcile_finished(snapshot, existing_rows, config["currentSeason"])
    # Persist canonical names and monotonic FINISHED state so downstream
    # prediction training sees the same authoritative results as the dashboard.
    SNAPSHOT_JSON.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = merge_current(existing_rows, snapshot, config["currentSeason"])
    write_rows(rows)
    data = build_data(rows, snapshot, static, config)
    render_dashboard(data, snapshot.get("updatedAt", "unknown"))
    print(f"Built {OUTPUT_HTML.name}: {len(rows):,} results, {len(snapshot.get('fixtures', []))} upcoming fixtures, {len(data.get('playerProfiles', {}))} player profiles")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
