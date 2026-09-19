#!/usr/bin/env python3
import calendar
import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "current"
OUT.mkdir(parents=True, exist_ok=True)

LEAGUES = {
    "epl":       {"name": "Premier League", "slug": "eng.1", "country": "England", "type": "league"},
    "laliga":    {"name": "LaLiga", "slug": "esp.1", "country": "Spain", "type": "league"},
    "bundesliga":{"name": "Bundesliga", "slug": "ger.1", "country": "Germany", "type": "league"},
    "seriea":    {"name": "Serie A", "slug": "ita.1", "country": "Italy", "type": "league"},
    "ligue1":    {"name": "Ligue 1", "slug": "fra.1", "country": "France", "type": "league"},
    "ucl":       {"name": "UEFA Champions League", "slug": "uefa.champions", "country": "Europe", "type": "uefa"},
    "uel":       {"name": "UEFA Europa League", "slug": "uefa.europa", "country": "Europe", "type": "uefa"},
    "uecl":      {"name": "UEFA Conference League", "slug": "uefa.europa.conf", "country": "Europe", "type": "uefa"},
    "copa":      {"name": "Copa del Rey", "slug": "esp.copa_del_rey", "country": "Spain", "type": "cup"},
    "eflcup":    {"name": "Carabao Cup (EFL Cup)", "slug": "eng.league_cup", "country": "England", "type": "cup"},
    "facup":     {"name": "FA Cup", "slug": "eng.fa", "country": "England", "type": "cup"},
}

UA = "FootballIntelligenceDashboard/1.0 (+https://github.com/Manohar0912/laliga-dashboard)"

def get_json(url, tries=3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=35) as r:
                return json.load(r)
        except Exception as exc:
            last = exc
            if attempt + 1 < tries:
                time.sleep(2 ** attempt)
    raise last

def iso_date(s):
    if not s:
        return ""
    return s[:10]

def month_chunks(start, end):
    cur = start.replace(day=1)
    while cur <= end:
        last_day = calendar.monthrange(cur.year, cur.month)[1]
        chunk_start = max(start, cur)
        chunk_end = min(end, cur.replace(day=last_day))
        yield chunk_start, chunk_end
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

def parse_scoreboard(slug, start, end):
    events = {}
    for a, b in month_chunks(start, end):
        dates = f"{a:%Y%m%d}-{b:%Y%m%d}"
        q = urllib.parse.urlencode({"dates": dates, "limit": 500})
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?{q}"
        try:
            payload = get_json(url)
        except Exception as exc:
            print(f"scoreboard warning {slug} {dates}: {exc}")
            continue
        for ev in payload.get("events", []):
            try:
                competition = (ev.get("competitions") or [{}])[0]
                sides = {}
                for c in competition.get("competitors", []):
                    sides[c.get("homeAway")] = c
                home = sides.get("home", {})
                away = sides.get("away", {})
                if not home or not away:
                    continue
                status = ev.get("status", {}).get("type", {})
                date_iso = ev.get("date", "")
                row = {
                    "id": str(ev.get("id", "")),
                    "date": iso_date(date_iso),
                    "dateTime": date_iso,
                    "status": status.get("description") or status.get("detail") or "",
                    "statusDetail": status.get("detail") or "",
                    "state": status.get("state") or "",
                    "completed": bool(status.get("completed")),
                    "home": home.get("team", {}).get("displayName") or home.get("team", {}).get("name") or "",
                    "away": away.get("team", {}).get("displayName") or away.get("team", {}).get("name") or "",
                    "homeShort": home.get("team", {}).get("abbreviation") or "",
                    "awayShort": away.get("team", {}).get("abbreviation") or "",
                    "homeLogo": home.get("team", {}).get("logo") or "",
                    "awayLogo": away.get("team", {}).get("logo") or "",
                    "homeScore": int(home.get("score")) if str(home.get("score", "")).lstrip("-").isdigit() else None,
                    "awayScore": int(away.get("score")) if str(away.get("score", "")).lstrip("-").isdigit() else None,
                    "venue": competition.get("venue", {}).get("fullName") or "",
                    "round": ((ev.get("week") or {}).get("text") or (ev.get("week") or {}).get("number") or ""),
                }
                if row["id"] and row["home"] and row["away"]:
                    events[row["id"]] = row
            except Exception as exc:
                print(f"event parse warning {slug}: {exc}")
    return events

def stat_map(stats):
    out = {}
    for s in stats or []:
        keys = [
            s.get("name"), s.get("abbreviation"), s.get("displayName"),
            s.get("shortDisplayName"), s.get("description")
        ]
        for k in keys:
            if k:
                out[str(k).lower().replace(" ", "").replace("-", "")] = s.get("value", s.get("displayValue"))
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
    groups = []
    for child in payload.get("children", []):
        group_name = child.get("name") or child.get("abbreviation") or ""
        standings = child.get("standings", {})
        for ent in standings.get("entries", []):
            team = ent.get("team", {})
            sm = stat_map(ent.get("stats"))
            rank = number(pick(sm, "rank", "playoffseed", default=0))
            groups.append({
                "group": group_name,
                "rank": rank,
                "team": team.get("displayName") or team.get("name") or "",
                "short": team.get("abbreviation") or "",
                "logo": (team.get("logos") or [{}])[0].get("href", "") if team.get("logos") else "",
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
    # Stable fallback ordering if rank is absent.
    groups.sort(key=lambda x: (x["group"], x["rank"] or 999, -x["points"], -x["gd"], x["team"]))
    return groups

def merge_existing(path, fresh):
    old = {}
    if path.exists():
        try:
            old_payload = json.loads(path.read_text(encoding="utf-8"))
            for m in old_payload.get("matches", []):
                if m.get("id"):
                    old[str(m["id"])] = m
        except Exception:
            pass
    old.update(fresh)
    return list(old.values())

def main():
    now = dt.datetime.now(dt.timezone.utc)
    season = now.year if now.month >= 7 else now.year - 1
    season_start = dt.date(season, 7, 1)
    season_end = dt.date(season + 1, 6, 30)
    today = now.date()

    meta = {"updatedAt": now.isoformat(), "season": season, "sources": {}, "errors": {}}

    for key, cfg in LEAGUES.items():
        path = OUT / f"{key}.json"
        if path.exists():
            start = max(season_start, today - dt.timedelta(days=24))
        else:
            start = season_start
        end = min(season_end, today + dt.timedelta(days=60))

        print(f"Updating {key} ({cfg['slug']}) {start}..{end}")
        try:
            fresh = parse_scoreboard(cfg["slug"], start, end)
            matches = merge_existing(path, fresh)
            matches = [m for m in matches if season_start.isoformat() <= (m.get("date") or "") <= season_end.isoformat()]
            matches.sort(key=lambda m: (m.get("dateTime") or m.get("date") or "", m.get("id") or ""))
            standings = parse_standings(cfg["slug"], season)
            teams = {}
            for s in standings:
                if s.get("team"):
                    teams[s["team"]] = {"name": s["team"], "short": s.get("short", ""), "logo": s.get("logo", "")}
            for m in matches:
                if m.get("home"):
                    teams.setdefault(m["home"], {"name": m["home"], "short": m.get("homeShort", ""), "logo": m.get("homeLogo", "")})
                if m.get("away"):
                    teams.setdefault(m["away"], {"name": m["away"], "short": m.get("awayShort", ""), "logo": m.get("awayLogo", "")})
            payload = {
                "updatedAt": now.isoformat(),
                "source": "ESPN public web feeds",
                "season": season,
                "competition": {**cfg, "id": key},
                "standings": standings,
                "matches": matches,
                "teams": sorted(teams.values(), key=lambda t: t["name"]),
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            meta["sources"][key] = {"ok": True, "matches": len(matches), "standings": len(standings)}
        except Exception as exc:
            print(f"ERROR {key}: {exc}")
            meta["errors"][key] = str(exc)
            meta["sources"][key] = {"ok": False}

    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
