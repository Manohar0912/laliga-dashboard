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
SNAPSHOT_JSON = DATA_DIR / "current_snapshot.json"
TEMPLATE_DIR = ROOT / "template_parts"
OUTPUT_HTML = ROOT / "index.html"
CONFIG_JSON = ROOT / "config.json"

ALIASES = {
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
    if name in ALIASES:
        return ALIASES[name]
    if short_name and short_name in ALIASES:
        return ALIASES[short_name]
    return short_name or name


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


def read_rows() -> list[dict]:
    with MATCHES_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(rows: list[dict]) -> None:
    with MATCHES_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in CSV_FIELDS})


def merge_current(rows: list[dict], snapshot: dict, season: str) -> list[dict]:
    # Replace current-season rows wholesale. This makes refreshes idempotent and
    # reconciles postponed/corrected matches instead of duplicating them.
    base = [r for r in rows if r.get("season") != season]
    current = []
    for m in snapshot.get("finished", []):
        row = {k: "" for k in CSV_FIELDS}
        row.update({
            "season": season, "date": m["date"], "home": m["home"], "away": m["away"],
            "home_goals": m["home_goals"], "away_goals": m["away_goals"],
            "ht_home_goals": "" if m.get("ht_home_goals") is None else m["ht_home_goals"],
            "ht_away_goals": "" if m.get("ht_away_goals") is None else m["ht_away_goals"],
        })
        current.append(row)
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
    return {
        "seasons": dict(seasons),
        "currentTeams": current_teams,
        "fixtures": snapshot.get("fixtures", []),
        "players": static["players"],
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
        SNAPSHOT_JSON.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = merge_current(read_rows(), snapshot, config["currentSeason"])
    write_rows(rows)
    data = build_data(rows, snapshot, static, config)
    render_dashboard(data, snapshot.get("updatedAt", "unknown"))
    print(f"Built {OUTPUT_HTML.name}: {len(rows):,} results, {len(snapshot.get('fixtures', []))} upcoming fixtures")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
