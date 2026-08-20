#!/usr/bin/env python3
"""Refresh reliable LaLiga player leaderboards for the Season Stats tab.

Uses football-data.org's competition scorers endpoint. Historical seasons are
seeded once and then cached; the current season is refreshed whenever this
script runs. Team-level season stats are derived directly in the dashboard from
the canonical match archive.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from update_laliga import canonical_team, load_config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "season_stats.json"


def label_for(start_year: int) -> str:
    return f"{start_year}/{str(start_year + 1)[-2:]}"


def load_existing() -> dict:
    if not OUT.exists():
        return {"source": "football-data.org v4 / competitions/PD/scorers", "seasons": {}}
    try:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    payload.setdefault("source", "football-data.org v4 / competitions/PD/scorers")
    payload.setdefault("seasons", {})
    return payload


def fetch_scorers(start_year: int, token: str) -> list[dict]:
    url = f"https://api.football-data.org/v4/competitions/PD/scorers?season={start_year}&limit=100"
    req = urllib.request.Request(
        url,
        headers={"X-Auth-Token": token, "User-Agent": "laliga-dashboard/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)

    rows = []
    for item in payload.get("scorers", []):
        player = item.get("player") or {}
        team = item.get("team") or {}
        name = (player.get("name") or "").strip()
        club = canonical_team(team.get("name", ""), team.get("shortName"))
        if not name or not club:
            continue
        rows.append(
            {
                "name": name,
                "team": club,
                "matches": int(item.get("playedMatches") or 0),
                "goals": int(item.get("goals") or 0),
                "assists": int(item.get("assists") or 0),
                "penalties": int(item.get("penalties") or 0),
            }
        )
    return rows


def main() -> int:
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        raise RuntimeError("FOOTBALL_DATA_TOKEN is required for season stats refresh")

    config = load_config()
    current_year = int(config["apiSeasonStartYear"])
    payload = load_existing()
    seasons = payload["seasons"]

    # Seed the last two completed seasons once so the tab remains useful when
    # viewers change the global season selector. Refresh only the live season on
    # subsequent runs to keep API usage low.
    targets = [2024, 2025, current_year]
    for year in targets:
        label = label_for(year)
        if year != current_year and (seasons.get(label) or {}).get("players"):
            continue
        try:
            players = fetch_scorers(year, token)
        except Exception as exc:
            if year == current_year:
                raise
            print(f"WARNING: could not seed {label} player leaders: {exc}")
            continue
        seasons[label] = {
            "players": players,
            "updatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        print(f"Season stats {label}: {len(players)} player rows")

    payload["updatedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
