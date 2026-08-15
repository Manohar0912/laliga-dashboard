#!/usr/bin/env python3
from __future__ import annotations
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rows = list(csv.DictReader((ROOT / 'data/laliga_matches.csv').open(encoding='utf-8')))
keys = [(r['season'], r['date'], r['home'], r['away']) for r in rows]
dups = [k for k, n in Counter(keys).items() if n > 1]
assert not dups, f'duplicate matches: {dups[:5]}'
assert rows and rows[0]['season'] == '1928/29', 'archive must begin in 1928/29'
assert any(r['season'] == '2025/26' for r in rows), 'expected completed 2025/26 season'
for r in rows:
    hg, ag = int(float(r['home_goals'])), int(float(r['away_goals']))
    assert hg >= 0 and ag >= 0
    assert r['home'] and r['away'] and r['home'] != r['away']

# Historical naming variants must be collapsed before the dashboard is built.
legacy_aliases = {
    'Athletic Bilbao', 'Atletico Madrid', 'CD Alaves', 'CD Leganes',
    'Cadiz CF', 'Espanyol Barcelona', 'UD Almeria', 'Sporting Gijon',
    'Malaga CF', 'Deportivo La Coruna'
}
clubs = {r['home'] for r in rows} | {r['away'] for r in rows}
remaining_aliases = sorted(legacy_aliases & clubs)
assert not remaining_aliases, f'legacy club aliases remain: {remaining_aliases}'

# Barcelona and Athletic are ever-present top-flight clubs. Their all-time league
# H2H must include the historical archive, not only the two recent-season rows.
barca_athletic = [
    r for r in rows
    if {r['home'], r['away']} == {'FC Barcelona', 'Athletic Club'}
]
assert len(barca_athletic) >= 190, (
    f'FC Barcelona vs Athletic Club H2H incomplete: {len(barca_athletic)} matches'
)

html = (ROOT / 'index.html').read_text(encoding='utf-8')
assert 'const DATA={' in html
assert '__DATA_JSON__' not in html and '__LAST_UPDATED__' not in html
assert '1928/29' in html and '2026/27' in html
assert '<section class="view" id="h2h"></section>' in html
assert '<section class="view" id="predictions"></section>' in html
print(
    f'OK: {len(rows):,} match rows; no duplicates; '
    f'Barcelona-Athletic H2H={len(barca_athletic)}; dashboard placeholders resolved'
)
