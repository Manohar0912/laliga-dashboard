#!/usr/bin/env python3
"""Refresh reliable LaLiga player leaderboards for the Season Stats tab.

Goals come from football-data.org's goal-ranked scorers endpoint. Assists are
fetched separately from AS.com's dedicated goal-assist ranking page. Keeping
those datasets separate is intentional: the football-data scorers endpoint is
ranked by goals, so using its embedded ``assists`` field as a league-wide assist
leaderboard can omit players with few/no goals.

Completed seasons are cached once; the current season is refreshed whenever
this script runs. Team-level season stats are derived directly in the dashboard
from the canonical match archive.
"""
from __future__ import annotations

import html as html_lib
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from update_laliga import canonical_team, load_config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "season_stats.json"

AS_TEAM_ALIASES = {
    "Alavés": "Deportivo Alavés",
    "Athletic": "Athletic Club",
    "Atlético": "Atlético Madrid",
    "Barcelona": "FC Barcelona",
    "Betis": "Real Betis",
    "Celta": "Celta Vigo",
    "Deportivo": "RC Deportivo",
    "Elche": "Elche CF",
    "Espanyol": "RCD Espanyol",
    "Getafe": "Getafe CF",
    "Levante": "Levante UD",
    "Málaga": "Málaga CF",
    "Osasuna": "CA Osasuna",
    "R. Sociedad": "Real Sociedad",
    "Racing": "Racing Santander",
    "Rayo": "Rayo Vallecano",
    "Real Madrid": "Real Madrid",
    "Sevilla": "Sevilla FC",
    "Valencia": "Valencia CF",
    "Villarreal": "Villarreal CF",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def label_for(start_year: int) -> str:
    return f"{start_year}/{str(start_year + 1)[-2:]}"


def load_existing() -> dict:
    if not OUT.exists():
        return {"source": "mixed verified leaderboards", "seasons": {}}
    try:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    payload["source"] = "mixed verified leaderboards"
    payload.setdefault("seasons", {})
    return payload


def fetch_scorers(start_year: int, token: str) -> list[dict]:
    """Fetch the goal-ranked player list. Safe for goals, not for assists."""
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
                # Retain the provider value only for consistency checks. The UI
                # never builds the assists leaderboard from this goal-ranked list.
                "assistsInScorerFeed": int(item.get("assists") or 0),
                "penalties": int(item.get("penalties") or 0),
            }
        )
    rows.sort(key=lambda x: (-x["goals"], x["name"]))
    return rows


class AssistRankingParser(HTMLParser):
    """Extract player/team/value rows from AS's dedicated assist-ranking table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_row = False
        self.cell: str | None = None
        self.row: dict[str, str] = {}
        self.rows: list[dict] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs = dict(attrs)
        if tag == "tr":
            self.in_row = True
            self.row = {}
            self.cell = None
            return
        if not self.in_row or tag != "td":
            return
        classes = (attrs.get("class") or "").split()
        for key in ("pos", "player", "team", "a_tb_rk"):
            if key in classes:
                self.cell = key
                self.row.setdefault(key, "")
                break

    def handle_data(self, data: str) -> None:
        if self.in_row and self.cell:
            self.row[self.cell] = self.row.get(self.cell, "") + data

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self.cell = None
            return
        if tag != "tr" or not self.in_row:
            return
        clean = {k: re.sub(r"\s+", " ", html_lib.unescape(v)).strip() for k, v in self.row.items()}
        if clean.get("player") and clean.get("team") and clean.get("a_tb_rk", "").isdigit():
            club = AS_TEAM_ALIASES.get(clean["team"], canonical_team(clean["team"]))
            self.rows.append(
                {
                    "name": clean["player"],
                    "team": club,
                    "assists": int(clean["a_tb_rk"]),
                }
            )
        self.in_row = False
        self.cell = None
        self.row = {}


def fetch_assists(start_year: int) -> list[dict]:
    end_year = start_year + 1
    url = (
        "https://as.com/resultados/futbol/primera/"
        f"{start_year}_{end_year}/ranking/jugadores/asistencias-de-gol/"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; laliga-dashboard/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        page = response.read().decode("utf-8", "replace")
    parser = AssistRankingParser()
    parser.feed(page)
    rows = parser.rows
    if not rows:
        raise RuntimeError(f"dedicated assists ranking returned no rows: {url}")
    # Deduplicate defensively in case the provider repeats a rendered table.
    unique: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["name"], row["team"])
        previous = unique.get(key)
        if previous is None or row["assists"] > previous["assists"]:
            unique[key] = row
    rows = list(unique.values())
    rows.sort(key=lambda x: (-x["assists"], x["name"]))
    return rows


def validate_cross_source(scorers: list[dict], assists: list[dict], label: str) -> None:
    """Catch truncation/parser failures before they can reach the dashboard."""
    if not scorers:
        raise RuntimeError(f"{label}: goal scorer feed is empty")
    if not assists:
        raise RuntimeError(f"{label}: dedicated assists feed is empty")

    assist_lookup = {(r["name"], r["team"]): r["assists"] for r in assists}
    # Any player visible in the goal-ranked feed with recorded assists must not
    # have a smaller value in the dedicated assist ranking.
    mismatches = []
    for row in scorers:
        embedded = row.get("assistsInScorerFeed", 0)
        if not embedded:
            continue
        dedicated = assist_lookup.get((row["name"], row["team"]))
        if dedicated is None or dedicated < embedded:
            mismatches.append((row["name"], row["team"], embedded, dedicated))
    if mismatches:
        raise RuntimeError(f"{label}: assist source cross-check failed: {mismatches[:5]}")

    max_embedded = max((r.get("assistsInScorerFeed", 0) for r in scorers), default=0)
    max_dedicated = max((r["assists"] for r in assists), default=0)
    if max_dedicated < max_embedded:
        raise RuntimeError(
            f"{label}: dedicated assist leader {max_dedicated} below scorer-feed maximum {max_embedded}"
        )


def refresh_year(year: int, token: str) -> dict:
    label = label_for(year)
    scorers = fetch_scorers(year, token)
    assists = fetch_assists(year)
    validate_cross_source(scorers, assists, label)
    return {
        "players": scorers,
        "assists": assists,
        "goalsSource": "football-data.org v4 / competitions/PD/scorers (goal-ranked)",
        "assistsSource": "AS.com / dedicated asistencias-de-gol ranking",
        "updatedAt": now_iso(),
    }


def main() -> int:
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        raise RuntimeError("FOOTBALL_DATA_TOKEN is required for season stats refresh")

    config = load_config()
    current_year = int(config["apiSeasonStartYear"])
    payload = load_existing()
    seasons = payload["seasons"]

    # Seed the last two completed seasons if the new separated assist dataset is
    # missing. Always refresh the live season so corrections are picked up.
    targets = [2024, 2025, current_year]
    for year in targets:
        label = label_for(year)
        existing = seasons.get(label) or {}
        if year != current_year and existing.get("players") and existing.get("assists"):
            continue
        try:
            season_payload = refresh_year(year, token)
        except Exception as exc:
            if year == current_year:
                raise
            print(f"WARNING: could not seed {label} season leaders: {exc}")
            continue
        seasons[label] = season_payload
        print(
            f"Season stats {label}: {len(season_payload['players'])} goal-ranked players, "
            f"{len(season_payload['assists'])} assist-ranked players"
        )

    payload["updatedAt"] = now_iso()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
