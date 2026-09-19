#!/usr/bin/env python3
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "current"
OUT.mkdir(parents=True, exist_ok=True)

LEAGUES = {
    "epl":       {"name": "Premier League", "slug": "eng.1", "country": "England", "type": "league", "history": "en.1"},
    "laliga":    {"name": "LaLiga", "slug": "esp.1", "country": "Spain", "type": "league", "history": "es.1"},
    "bundesliga":{"name": "Bundesliga", "slug": "ger.1", "country": "Germany", "type": "league", "history": "de.1"},
    "seriea":    {"name": "Serie A", "slug": "ita.1", "country": "Italy", "type": "league", "history": "it.1"},
    "ligue1":    {"name": "Ligue 1", "slug": "fra.1", "country": "France", "type": "league", "history": "fr.1"},
    "ucl":       {"name": "UEFA Champions League", "slug": "uefa.champions", "country": "Europe", "type": "uefa"},
    "uel":       {"name": "UEFA Europa League", "slug": "uefa.europa", "country": "Europe", "type": "uefa"},
    "uecl":      {"name": "UEFA Conference League", "slug": "uefa.europa.conf", "country": "Europe", "type": "uefa"},
    "copa":      {"name": "Copa del Rey", "slug": "esp.copa_del_rey", "country": "Spain", "type": "cup"},
    "eflcup":    {"name": "Carabao Cup (EFL Cup)", "slug": "eng.league_cup", "country": "England", "type": "cup"},
    "facup":     {"name": "FA Cup", "slug": "eng.fa", "country": "England", "type": "cup"},
}

UA = "FootballIntelligenceDashboard/1.1 (+https://github.com/Manohar0912/laliga-dashboard)"

def get_json(url, tries=2):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=18) as r:
                return json.load(r)
        except Exception as exc:
            last = exc
            if attempt + 1 < tries:
                time.sleep(1.5)
    raise last

def as_int(v):
    try:
        return int(float(v))
    except Exception:
        return None

def parse_event(ev):
    competition = (ev.get("competitions") or [{}])[0]
    sides = {c.get("homeAway"): c for c in competition.get("competitors", [])}
    home, away = sides.get("home", {}), sides.get("away", {})
    if not home or not away:
        return None
    status = ev.get("status", {}).get("type", {})
    home_team, away_team = home.get("team", {}), away.get("team", {})
    return {
        "id": str(ev.get("id", "")),
        "date": (ev.get("date") or "")[:10],
        "dateTime": ev.get("date") or "",
        "status": status.get("description") or status.get("detail") or "",
        "statusDetail": status.get("detail") or "",
        "state": status.get("state") or "",
        "completed": bool(status.get("completed")),
        "home": home_team.get("displayName") or home_team.get("name") or "",
        "away": away_team.get("displayName") or away_team.get("name") or "",
        "homeShort": home_team.get("abbreviation") or "",
        "awayShort": away_team.get("abbreviation") or "",
        "homeLogo": home_team.get("logo") or "",
        "awayLogo": away_team.get("logo") or "",
        "homeScore": as_int(home.get("score")),
        "awayScore": as_int(away.get("score")),
        "venue": competition.get("venue", {}).get("fullName") or "",
        "round": str((ev.get("week") or {}).get("text") or (ev.get("week") or {}).get("number") or ""),
        "provider": "espn",
    }

def fetch_scoreboard(slug):
    # ESPN's default soccer scoreboard gives the current relevant match window.
    # It is substantially lighter than querying every day of the season.
    urls = [
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?limit=100",
        f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?limit=100",
    ]
    last = None
    for url in urls:
        try:
            payload = get_json(url)
            rows = {}
            for ev in payload.get("events", []):
                row = parse_event(ev)
                if row and row["id"] and row["home"] and row["away"]:
                    rows[row["id"]] = row
            return rows
        except Exception as exc:
            last = exc
    raise last

def seed_openfootball(cfg, season):
    code = cfg.get("history")
    if not code:
        return []
    path = f"{season}-{str((season+1)%100).zfill(2)}"
    url = f"https://raw.githubusercontent.com/openfootball/football.json/master/{path}/{code}.json"
    try:
        payload = get_json(url)
    except Exception as exc:
        print(f"OpenFootball seed warning {code}: {exc}")
        return []
    out = []
    for i, m in enumerate(payload.get("matches", [])):
        team1, team2 = m.get("team1") or "", m.get("team2") or ""
        if not team1 or not team2:
            continue
        score = m.get("score")
        if isinstance(score, dict):
            ft = score.get("ft")
        elif isinstance(score, list) and len(score) >= 2:
            ft = score
        else:
            ft = None
        completed = isinstance(ft, list) and len(ft) >= 2
        date = m.get("date") or ""
        time_s = m.get("time") or ""
        out.append({
            "id": f"open-{code}-{date}-{i}",
            "date": date,
            "dateTime": date + (f"T{time_s}:00Z" if time_s else "T12:00:00Z"),
            "status": "Full Time" if completed else "Scheduled",
            "statusDetail": "Full Time" if completed else "Scheduled",
            "state": "post" if completed else "pre",
            "completed": completed,
            "home": team1,
            "away": team2,
            "homeShort": "",
            "awayShort": "",
            "homeLogo": "",
            "awayLogo": "",
            "homeScore": as_int(ft[0]) if completed else None,
            "awayScore": as_int(ft[1]) if completed else None,
            "venue": "",
            "round": str(m.get("round") or ""),
            "provider": "openfootball",
        })
    return out

def stat_map(stats):
    out = {}
    for s in stats or []:
        value = s.get("value", s.get("displayValue"))
        for key in (s.get("name"), s.get("abbreviation"), s.get("displayName"), s.get("shortDisplayName"), s.get("description")):
            if key:
                out[str(key).lower().replace(" ", "").replace("-", "")] = value
    return out

def pick(m, *names, default=0):
    for n in names:
        key = n.lower().replace(" ", "").replace("-", "")
        if key in m and m[key] is not None:
            return m[key]
    return default

def number(v, default=0):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except Exception:
        return default

def parse_standings(slug, season):
    urls = [
        f"https://site.web.api.espn.com/apis/v2/sports/soccer/{slug}/standings?season={season}&type=0&level=0",
        f"https://site.api.espn.com/apis/v2/sports/soccer/{slug}/standings?season={season}&type=0&level=0",
    ]
    payload = None
    for url in urls:
        try:
            payload = get_json(url)
            break
        except Exception as exc:
            print(f"standings warning {slug}: {exc}")
    if not payload:
        return []
    rows = []
    for child in payload.get("children", []):
        group_name = child.get("name") or child.get("abbreviation") or ""
        for ent in (child.get("standings") or {}).get("entries", []):
            team = ent.get("team") or {}
            sm = stat_map(ent.get("stats"))
            logos = team.get("logos") or []
            rows.append({
                "group": group_name,
                "rank": number(pick(sm, "rank", "playoffseed", default=0)),
                "team": team.get("displayName") or team.get("name") or "",
                "short": team.get("abbreviation") or "",
                "logo": logos[0].get("href", "") if logos else "",
                "played": number(pick(sm, "gamesplayed", "games", "gp", default=0)),
                "wins": number(pick(sm, "wins", "w", default=0)),
                "draws": number(pick(sm, "ties", "draws", "d", default=0)),
                "losses": number(pick(sm, "losses", "l", default=0)),
                "gf": number(pick(sm, "pointsfor", "goalsfor", "gf", default=0)),
                "ga": number(pick(sm, "pointsagainst", "goalsagainst", "ga", default=0)),
                "gd": number(pick(sm, "pointdifferential", "goaldifference", "gd", default=0)),
                "points": number(pick(sm, "points", "pts", default=0)),
                "form": str(pick(sm, "streak", "form", default="") or ""),
            })
    rows.sort(key=lambda x: (x["group"], x["rank"] or 999, -x["points"], -x["gd"], x["team"]))
    return rows

def load_existing(path):
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("matches", [])
    except Exception:
        return []

def merge_matches(seed, existing, fresh):
    # Dedupe by fixture identity rather than provider ID. Fresh ESPN data wins.
    by_fixture = {}
    for row in list(seed) + list(existing) + list(fresh.values()):
        if not row.get("home") or not row.get("away") or not row.get("date"):
            continue
        key = (row["date"], row["home"].strip().lower(), row["away"].strip().lower())
        prev = by_fixture.get(key)
        if prev is None or row.get("provider") == "espn" or (row.get("completed") and not prev.get("completed")):
            by_fixture[key] = row
    return sorted(by_fixture.values(), key=lambda m: (m.get("dateTime") or m.get("date") or "", m.get("home") or ""))

def main():
    now = dt.datetime.now(dt.timezone.utc)
    season = now.year if now.month >= 7 else now.year - 1
    meta = {"updatedAt": now.isoformat(), "season": season, "sources": {}, "errors": {}}

    for key, cfg in LEAGUES.items():
        path = OUT / f"{key}.json"
        print(f"Updating {key} ({cfg['slug']})")
        try:
            existing = load_existing(path)
            seed = [] if existing else seed_openfootball(cfg, season)
            try:
                fresh = fetch_scoreboard(cfg["slug"])
            except Exception as exc:
                print(f"scoreboard warning {cfg['slug']}: {exc}")
                fresh = {}
            standings = parse_standings(cfg["slug"], season)
            matches = merge_matches(seed, existing, fresh)
            teams = {}
            for s in standings:
                if s.get("team"):
                    teams[s["team"]] = {"name": s["team"], "short": s.get("short", ""), "logo": s.get("logo", "")}
            for m in matches:
                for side in ("home", "away"):
                    name = m.get(side)
                    if not name:
                        continue
                    teams.setdefault(name, {
                        "name": name,
                        "short": m.get(side + "Short", ""),
                        "logo": m.get(side + "Logo", ""),
                    })
                    if m.get(side + "Logo"):
                        teams[name]["logo"] = m.get(side + "Logo")
            payload = {
                "updatedAt": now.isoformat(),
                "source": "ESPN current feeds + OpenFootball season seed",
                "season": season,
                "competition": {**cfg, "id": key},
                "standings": standings,
                "matches": matches,
                "teams": sorted(teams.values(), key=lambda t: t["name"]),
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            meta["sources"][key] = {"ok": True, "matches": len(matches), "freshEvents": len(fresh), "standings": len(standings)}
        except Exception as exc:
            print(f"ERROR {key}: {exc}")
            meta["errors"][key] = str(exc)
            meta["sources"][key] = {"ok": False}

    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
