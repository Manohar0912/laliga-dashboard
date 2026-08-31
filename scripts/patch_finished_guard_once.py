#!/usr/bin/env python3
from pathlib import Path

p = Path('scripts/update_laliga.py')
s = p.read_text(encoding='utf-8')
old = '''def merge_current(rows: list[dict], snapshot: dict, season: str) -> list[dict]:
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
'''
new = '''def result_pair(row: dict) -> tuple[str, str]:
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
'''
if old not in s:
    raise SystemExit('merge_current anchor not found')
s = s.replace(old, new)
old_main = '''    snapshot = normalize_snapshot(snapshot)
    # Persist canonical names in both live and offline rebuilds so downstream
    # prediction training uses the same club identities as the dashboard.
    SNAPSHOT_JSON.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")

    rows = merge_current(read_rows(), snapshot, config["currentSeason"])
'''
new_main = '''    snapshot = normalize_snapshot(snapshot)
    existing_rows = read_rows()
    snapshot = reconcile_finished(snapshot, existing_rows, config["currentSeason"])
    # Persist canonical names and monotonic FINISHED state so downstream
    # prediction training sees the same authoritative results as the dashboard.
    SNAPSHOT_JSON.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")

    rows = merge_current(existing_rows, snapshot, config["currentSeason"])
'''
if old_main not in s:
    raise SystemExit('main anchor not found')
s = s.replace(old_main, new_main)
p.write_text(s, encoding='utf-8')

v = Path('scripts/validate.py')
vs = v.read_text(encoding='utf-8')
anchor = "snapshot_teams = set(snapshot.get('teams') or [])\n"
insert = '''config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
current_label = config['currentSeason']
archive_current_pairs = {
    (r['home'], r['away']) for r in rows if r.get('season') == current_label
}
snapshot_finished_pairs = {
    (m.get('home'), m.get('away')) for m in snapshot.get('finished', [])
}
snapshot_fixture_pairs = {
    (m.get('home'), m.get('away')) for m in snapshot.get('fixtures', [])
}
assert archive_current_pairs <= snapshot_finished_pairs, (
    f'confirmed results missing from snapshot.finished: {sorted(archive_current_pairs - snapshot_finished_pairs)[:5]}'
)
assert not (snapshot_finished_pairs & snapshot_fixture_pairs), (
    f'finished matches leaked back into fixtures: {sorted(snapshot_finished_pairs & snapshot_fixture_pairs)[:5]}'
)
'''
if anchor not in vs:
    raise SystemExit('validate anchor not found')
vs = vs.replace(anchor, insert + anchor, 1)
v.write_text(vs, encoding='utf-8')
print('Patched updater and validation with monotonic FINISHED guard')
