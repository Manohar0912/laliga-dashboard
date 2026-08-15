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

html = (ROOT / 'index.html').read_text(encoding='utf-8')
assert 'const DATA={' in html
assert '__DATA_JSON__' not in html and '__LAST_UPDATED__' not in html
assert '1928/29' in html and '2026/27' in html
assert '<section class="view" id="h2h"></section>' in html
assert '<section class="view" id="predictions"></section>' in html
print(f'OK: {len(rows):,} match rows; no duplicates; dashboard placeholders resolved')
