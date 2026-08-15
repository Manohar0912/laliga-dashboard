#!/usr/bin/env python3
"""Bootstrap the all-time LaLiga result archive when the repository is empty.

Sources:
- engsoccerdata `spain.rda` for Spanish top-flight results through 2024/25.
- football-data.co.uk SP1.csv for the completed 2025/26 season, including
  richer match statistics where available.

The resulting CSV is subsequently maintained by update_laliga.py, which
reconciles the current season from football-data.org.
"""
from __future__ import annotations

import csv
import io
import math
import urllib.request
from pathlib import Path

import pyreadr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "laliga_matches.csv"
TMP_RDA = ROOT / "data" / ".spain.rda"

SPAIN_RDA = "https://raw.githubusercontent.com/jalapic/engsoccerdata/master/data/spain.rda"
SEASON_2526 = "https://www.football-data.co.uk/mmz4281/2526/SP1.csv"

FIELDS = [
    "season", "date", "home", "away", "home_goals", "away_goals",
    "ht_home_goals", "ht_away_goals", "home_shots", "away_shots",
    "home_sot", "away_sot", "home_fouls", "away_fouls",
    "home_corners", "away_corners", "home_yellow", "away_yellow",
    "home_red", "away_red",
]

TEAM_ALIASES = {
    "Alaves": "Deportivo Alavés",
    "Ath Bilbao": "Athletic Club",
    "Ath Madrid": "Atlético Madrid",
    "Barcelona": "FC Barcelona",
    "Betis": "Real Betis",
    "Celta": "Celta Vigo",
    "Elche": "Elche CF",
    "Espanol": "RCD Espanyol",
    "Getafe": "Getafe CF",
    "Girona": "Girona FC",
    "Levante": "Levante UD",
    "Mallorca": "RCD Mallorca",
    "Osasuna": "CA Osasuna",
    "Oviedo": "Real Oviedo",
    "Vallecano": "Rayo Vallecano",
    "Sociedad": "Real Sociedad",
    "Sevilla": "Sevilla FC",
    "Valencia": "Valencia CF",
    "Villarreal": "Villarreal CF",
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "laliga-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def clean_number(value):
    if value is None:
        return ""
    try:
        if math.isnan(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text in {"", "nan", "NaN", "None", "NA", "<NA>"}:
        return ""
    try:
        number = float(text)
        return str(int(number)) if number.is_integer() else str(number)
    except ValueError:
        return text


def season_label(value) -> str:
    year = int(float(value))
    return f"{year}/{str(year + 1)[-2:]}"


def date_label(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    return text[:10]


def historical_rows() -> list[dict]:
    TMP_RDA.write_bytes(fetch(SPAIN_RDA))
    try:
        objects = pyreadr.read_r(str(TMP_RDA))
    finally:
        TMP_RDA.unlink(missing_ok=True)
    if not objects:
        raise RuntimeError("engsoccerdata spain.rda contained no data frame")
    frame = objects["spain"] if "spain" in objects else next(iter(objects.values()))
    rows: list[dict] = []
    for _, r in frame.iterrows():
        if clean_number(r.get("tier")) not in {"", "1"}:
            continue
        home = str(r.get("home", "")).strip()
        away = str(r.get("visitor", "")).strip()
        if not home or not away:
            continue
        rows.append({
            "season": season_label(r.get("Season")),
            "date": date_label(r.get("Date")),
            "home": home,
            "away": away,
            "home_goals": clean_number(r.get("hgoal")),
            "away_goals": clean_number(r.get("vgoal")),
            "ht_home_goals": "",
            "ht_away_goals": "",
            "home_shots": "",
            "away_shots": "",
            "home_sot": "",
            "away_sot": "",
            "home_fouls": "",
            "away_fouls": "",
            "home_corners": "",
            "away_corners": "",
            "home_yellow": "",
            "away_yellow": "",
            "home_red": "",
            "away_red": "",
        })
    return rows


def recent_rows() -> list[dict]:
    text = fetch(SEASON_2526).decode("utf-8-sig")
    rows: list[dict] = []
    for r in csv.DictReader(io.StringIO(text)):
        if not r.get("HomeTeam") or r.get("FTHG", "") == "":
            continue
        raw_date = r.get("Date", "")
        day, month, year = raw_date.split("/")
        if len(year) == 2:
            year = "20" + year
        rows.append({
            "season": "2025/26",
            "date": f"{year}-{month.zfill(2)}-{day.zfill(2)}",
            "home": TEAM_ALIASES.get(r["HomeTeam"], r["HomeTeam"]),
            "away": TEAM_ALIASES.get(r["AwayTeam"], r["AwayTeam"]),
            "home_goals": clean_number(r.get("FTHG")),
            "away_goals": clean_number(r.get("FTAG")),
            "ht_home_goals": clean_number(r.get("HTHG")),
            "ht_away_goals": clean_number(r.get("HTAG")),
            "home_shots": clean_number(r.get("HS")),
            "away_shots": clean_number(r.get("AS")),
            "home_sot": clean_number(r.get("HST")),
            "away_sot": clean_number(r.get("AST")),
            "home_fouls": clean_number(r.get("HF")),
            "away_fouls": clean_number(r.get("AF")),
            "home_corners": clean_number(r.get("HC")),
            "away_corners": clean_number(r.get("AC")),
            "home_yellow": clean_number(r.get("HY")),
            "away_yellow": clean_number(r.get("AY")),
            "home_red": clean_number(r.get("HR")),
            "away_red": clean_number(r.get("AR")),
        })
    return rows


def main() -> int:
    if OUT.exists() and OUT.stat().st_size > 100_000:
        print(f"History already present: {OUT}")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = historical_rows()
    rows = [row for row in rows if row["season"] != "2025/26"]
    rows.extend(recent_rows())
    rows.sort(key=lambda r: (r["season"], r["date"], r["home"], r["away"]))

    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Bootstrapped {len(rows):,} LaLiga match rows into {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
