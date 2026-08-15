#!/usr/bin/env python3
from __future__ import annotations
import csv
import json
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

barca_athletic = [
    r for r in rows
    if {r['home'], r['away']} == {'FC Barcelona', 'Athletic Club'}
]
assert len(barca_athletic) >= 190, (
    f'FC Barcelona vs Athletic Club H2H incomplete: {len(barca_athletic)} matches'
)

player_path = ROOT / 'data/player_data.json'
assert player_path.exists(), 'player_data.json must be built before validation'
player_payload = json.loads(player_path.read_text(encoding='utf-8'))
profiles = player_payload.get('players') or {}
assert len(profiles) >= 40, f'player catalogue unexpectedly small: {len(profiles)}'
assert 'Kylian Mbappé' in profiles, 'Kylian Mbappé missing from player profiles'
mbappe = profiles['Kylian Mbappé']
assert len(mbappe.get('seasons') or []) >= 2, 'Mbappé must have multi-season LaLiga history'
mbappe_barca = [m for m in (mbappe.get('matches') or []) if m.get('opponent') == 'FC Barcelona']
assert len(mbappe_barca) >= 3, f'Mbappé vs Barcelona history incomplete: {len(mbappe_barca)} matches'
assert sum(int(m.get('goals', 0)) for m in mbappe_barca) >= 4, 'Mbappé vs Barcelona goals unexpectedly low'

model_path = ROOT / 'data/model_predictions.json'
assert model_path.exists(), 'model_predictions.json must be trained before validation'
model = json.loads(model_path.read_text(encoding='utf-8'))
validation = model.get('validation') or {}
assert validation.get('matches', 0) >= 2500, f"prediction validation sample too small: {validation}"
assert validation.get('logLoss', 99) < validation.get('baselineLogLoss', 0), f"trained model did not beat baseline log loss: {validation}"
assert validation.get('brier', 99) <= validation.get('baselineBrier', 0), f"trained model did not beat baseline Brier score: {validation}"
assert validation.get('accuracy', 0) >= validation.get('baselineAccuracy', 1), f"trained model did not beat baseline accuracy: {validation}"
high = (validation.get('confidence') or {}).get('high') or {}
assert high.get('matches', 0) >= 100, f"high-confidence validation sample too small: {high}"
assert high.get('accuracy', 0) >= 0.64, f"high-confidence bucket is not reliable enough: {high}"
snapshot = json.loads((ROOT / 'data/current_snapshot.json').read_text(encoding='utf-8'))
assert len(model.get('predictions') or {}) == len(snapshot.get('fixtures') or []), 'every upcoming fixture must have a trained prediction'

html = (ROOT / 'index.html').read_text(encoding='utf-8')
assert 'const DATA={' in html
assert 'const PREDICTION_MODEL={' in html
assert '__DATA_JSON__' not in html and '__LAST_UPDATED__' not in html
assert '1928/29' in html and '2026/27' in html
assert '<section class="view" id="h2h"></section>' in html
assert '<section class="view" id="predictions"></section>' in html
assert 'playerProfiles' in html and 'Kylian Mbappé' in html
assert 'PLAYER VS TEAM' in html and 'Performance across seasons' in html
assert 'Historically trained Poisson + Elo ensemble' in html
assert 'historical hit rate' in html
print(
    f'OK: {len(rows):,} match rows; no duplicates; '
    f'Barcelona-Athletic H2H={len(barca_athletic)}; '
    f'{len(profiles)} player profiles; Mbappé-Barcelona matches={len(mbappe_barca)}; '
    f"prediction holdout={validation['matches']:,}, accuracy={validation['accuracy']:.1%}, "
    f"high-confidence={high['accuracy']:.1%}; dashboard placeholders resolved"
)
