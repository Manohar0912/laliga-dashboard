#!/usr/bin/env python3
"""Build multi-season LaLiga player histories and player-vs-team match logs.

Understat's current first-party AJAX feeds provide consistent season totals and
player match logs. We use those feeds for player analytics while keeping the
main match/results pipeline independent.
"""
from __future__ import annotations

import csv
import gzip
import json
import re
import time
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MATCHES_CSV = DATA_DIR / "laliga_matches.csv"
STATIC_JSON = DATA_DIR / "static_data.json"
CONFIG_JSON = ROOT / "config.json"
OUT = DATA_DIR / "player_data.json"

TEAM_ALIASES = {
    "Alaves": "Deportivo Alavés",
    "Almeria": "UD Almería",
    "Athletic Bilbao": "Athletic Club",
    "Atletico Madrid": "Atlético Madrid",
    "Barcelona": "FC Barcelona",
    "Cadiz": "Cádiz CF",
    "Celta Vigo": "Celta Vigo",
    "Deportivo La Coruna": "RC Deportivo",
    "Elche": "Elche CF",
    "Espanol": "RCD Espanyol",
    "Espanyol": "RCD Espanyol",
    "Getafe": "Getafe CF",
    "Girona": "Girona FC",
    "Leganes": "CD Leganés",
    "Levante": "Levante UD",
    "Malaga": "Málaga CF",
    "Mallorca": "RCD Mallorca",
    "Osasuna": "CA Osasuna",
    "Oviedo": "Real Oviedo",
    "Rayo Vallecano": "Rayo Vallecano",
    "Real Betis": "Real Betis",
    "Real Madrid": "Real Madrid",
    "Real Sociedad": "Real Sociedad",
    "Sevilla": "Sevilla FC",
    "Sporting Gijon": "Sporting Gijón",
    "Valencia": "Valencia CF",
    "Villarreal": "Villarreal CF",
}

PLAYER_ALIASES = {
    "Kylian Mbappe-Lottin": "Kylian Mbappé",
    "Vinicius Junior": "Vinícius Júnior",
}


def canonical_team(name: str) -> str:
    name = (name or "").strip()
    return TEAM_ALIASES.get(name, name)


def season_label(year: int) -> str:
    return f"{year}/{str(year + 1)[-2:]}"


def num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def integer(value) -> int:
    return int(round(num(value)))


def norm_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", text)


def ajax_json(url: str, referer: str, retries: int = 3) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; laliga-dashboard/1.0)",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": referer,
    }
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=35) as response:
                raw = response.read()
                encoding = response.headers.get("Content-Encoding", "")
            if raw[:2] == b"\x1f\x8b" or "gzip" in encoding.lower():
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:  # network source: retry transient failures
            last = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Understat request failed: {url}: {last}")


def league_data(year: int) -> dict:
    return ajax_json(
        f"https://understat.com/getLeagueData/La_liga/{year}",
        f"https://understat.com/league/La_liga/{year}",
    )


def player_data(player_id: str) -> dict:
    return ajax_json(
        f"https://understat.com/getPlayerData/{player_id}",
        f"https://understat.com/player/{player_id}",
    )


def load_league_teams() -> dict[str, set[str]]:
    teams: dict[str, set[str]] = defaultdict(set)
    with MATCHES_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            teams[row["season"]].update((canonical_team(row["home"]), canonical_team(row["away"])))
    return teams


def static_display_names() -> list[str]:
    static = json.loads(STATIC_JSON.read_text(encoding="utf-8"))
    return sorted({p["name"] for rows in static.get("players", {}).values() for p in rows if p.get("name")})


def display_name(raw: str, preferred: dict[str, str]) -> str:
    if raw in PLAYER_ALIASES:
        return PLAYER_ALIASES[raw]
    normalized = norm_name(raw)
    return preferred.get(normalized, raw)


def split_teams(value: str) -> list[str]:
    return [canonical_team(x.strip()) for x in (value or "").split(",") if x.strip()]


def season_row(row: dict, preferred: dict[str, str]) -> dict:
    return {
        "id": str(row.get("id", "")),
        "name": display_name(str(row.get("player_name", "")), preferred),
        "team": ", ".join(split_teams(str(row.get("team_title", "")))),
        "apps": integer(row.get("games")),
        "minutes": integer(row.get("time")),
        "goals": integer(row.get("goals")),
        "assists": integer(row.get("assists")),
        "xg": round(num(row.get("xG")), 2),
        "xa": round(num(row.get("xA")), 2),
        "shots": integer(row.get("shots")),
        "keyPasses": integer(row.get("key_passes")),
        "npg": integer(row.get("npg")),
        "npxg": round(num(row.get("npxG")), 2),
        "yellow": integer(row.get("yellow_cards")),
        "red": integer(row.get("red_cards")),
        "position": str(row.get("position", "")),
    }


def choose_player_ids(seasons_by_year: dict[int, list[dict]], forced_names: list[str]) -> set[str]:
    chosen: set[str] = set()
    # A compact but useful catalogue: leading contributors from every Understat
    # LaLiga season, plus every player already exposed in our old player explorer.
    for rows in seasons_by_year.values():
        ranked = sorted(
            rows,
            key=lambda r: (integer(r.get("goals")) + integer(r.get("assists")), integer(r.get("time"))),
            reverse=True,
        )
        chosen.update(str(r.get("id")) for r in ranked[:20] if r.get("id"))

    raw_players = [r for rows in seasons_by_year.values() for r in rows]
    for wanted in forced_names:
        nw = norm_name(wanted)
        for row in raw_players:
            raw = str(row.get("player_name", ""))
            nr = norm_name(raw)
            if nr == nw or raw == "Kylian Mbappe-Lottin" and "mbappe" in nw:
                chosen.add(str(row.get("id")))
    return chosen


def match_row(match: dict, player_teams: list[str], season_teams: set[str]) -> dict | None:
    home = canonical_team(str(match.get("h_team", "")))
    away = canonical_team(str(match.get("a_team", "")))
    if not home or not away or home not in season_teams or away not in season_teams:
        return None
    possible = [t for t in player_teams if t in {home, away}]
    if len(possible) != 1:
        return None
    team = possible[0]
    opponent = away if team == home else home
    hg, ag = integer(match.get("h_goals")), integer(match.get("a_goals"))
    gf, ga = (hg, ag) if team == home else (ag, hg)
    result = "W" if gf > ga else "D" if gf == ga else "L"
    return {
        "season": season_label(int(match["season"])),
        "date": str(match.get("date", ""))[:10],
        "home": home,
        "away": away,
        "homeGoals": hg,
        "awayGoals": ag,
        "team": team,
        "opponent": opponent,
        "result": result,
        "minutes": integer(match.get("time")),
        "goals": integer(match.get("goals")),
        "assists": integer(match.get("assists")),
        "shots": integer(match.get("shots")),
        "keyPasses": integer(match.get("key_passes")),
        "xg": round(num(match.get("xG")), 2),
        "xa": round(num(match.get("xA")), 2),
        "position": str(match.get("position", "")),
    }


def main() -> int:
    config = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    current_year = int(config["apiSeasonStartYear"])
    forced = static_display_names()
    preferred = {norm_name(x): x for x in forced}
    league_teams = load_league_teams()

    seasons_by_year: dict[int, list[dict]] = {}
    # Understat LaLiga coverage starts in 2014/15. Current season may be empty
    # before the first match, which is fine; completed seasons remain available.
    for year in range(2014, current_year + 1):
        try:
            payload = league_data(year)
        except Exception as exc:
            if year == current_year:
                print(f"Current-season player feed not ready: {exc}")
                continue
            raise
        seasons_by_year[year] = payload.get("players") or []
        time.sleep(0.12)

    chosen_ids = choose_player_ids(seasons_by_year, forced)
    stats_by_id: dict[str, list[dict]] = defaultdict(list)
    raw_name_by_id: dict[str, str] = {}
    teams_by_id_season: dict[tuple[str, int], list[str]] = {}
    for year, rows in seasons_by_year.items():
        for raw in rows:
            pid = str(raw.get("id", ""))
            if not pid or pid not in chosen_ids:
                continue
            cooked = season_row(raw, preferred)
            cooked["season"] = season_label(year)
            stats_by_id[pid].append(cooked)
            raw_name_by_id[pid] = str(raw.get("player_name", ""))
            teams_by_id_season[(pid, year)] = split_teams(str(raw.get("team_title", "")))

    existing = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8")).get("players", {})
        except Exception:
            existing = {}

    players: dict[str, dict] = {}
    for index, pid in enumerate(sorted(chosen_ids, key=lambda x: int(x) if x.isdigit() else 10**9)):
        season_stats = sorted(stats_by_id.get(pid, []), key=lambda r: r["season"], reverse=True)
        if not season_stats:
            continue
        name = display_name(raw_name_by_id.get(pid, season_stats[0]["name"]), preferred)
        max_year = max(int(r["season"][:4]) for r in season_stats)
        old = existing.get(name) or {}
        use_cached = bool(old.get("matches")) and max_year < current_year - 1
        matches: list[dict] = []
        if use_cached:
            matches = old["matches"]
        else:
            try:
                detail = player_data(pid)
                for match in detail.get("matches") or []:
                    try:
                        year = int(match.get("season"))
                    except (TypeError, ValueError):
                        continue
                    label = season_label(year)
                    cooked = match_row(
                        match,
                        teams_by_id_season.get((pid, year), []),
                        league_teams.get(label, set()),
                    )
                    if cooked:
                        matches.append(cooked)
                matches.sort(key=lambda r: r["date"], reverse=True)
            except Exception as exc:
                if old.get("matches"):
                    print(f"Using cached matches for {name}: {exc}")
                    matches = old["matches"]
                else:
                    print(f"No opponent detail for {name}: {exc}")
            time.sleep(0.10)

        players[name] = {"id": pid, "seasons": season_stats, "matches": matches}
        if (index + 1) % 25 == 0:
            print(f"Player profiles processed: {index + 1}/{len(chosen_ids)}")

    payload = {
        "source": "Understat",
        "coverage": "LaLiga player data from 2014/15 onward",
        "updatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "players": dict(sorted(players.items())),
    }
    if "Kylian Mbappé" not in payload["players"]:
        raise RuntimeError("Kylian Mbappé missing from player dataset")
    mb = payload["players"]["Kylian Mbappé"]
    if len(mb["seasons"]) < 2:
        raise RuntimeError("Expected multiple LaLiga seasons for Kylian Mbappé")
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Built {OUT.name}: {len(players)} players; {sum(len(p['matches']) for p in players.values()):,} LaLiga player-match rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
