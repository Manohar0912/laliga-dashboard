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
config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
current_season = config['currentSeason']
season_stats = json.loads((ROOT / 'data/season_stats.json').read_text(encoding='utf-8'))
current_season_stats = ((season_stats.get('seasons') or {}).get(current_season) or {})
current_players = current_season_stats.get('players') or []
current_assists = current_season_stats.get('assists') or []
assert current_players, 'current-season goal leaderboard is empty'
assert current_assists, 'current-season dedicated assist leaderboard is empty'
assert 'asistencias-de-gol' in (current_season_stats.get('assistsSource') or ''), 'assist leaderboard is not using the dedicated assist-ranked source'
# The goal-ranked population must never be reused as the assist leaderboard.
assert all('assists' not in p for p in current_players), 'goal-ranked rows contain a generic assists field; source separation regressed'
assist_values = [int(p.get('assists', 0)) for p in current_assists]
assert len(assist_values) >= 3, f'dedicated assist leaderboard suspiciously short: {len(assist_values)}'
assert assist_values == sorted(assist_values, reverse=True), 'dedicated assist leaderboard is not sorted descending'
assert max(assist_values, default=0) > 0, 'dedicated assist leaderboard has no positive values'
# Concrete regression for the season in which the original omission was found.
# It is scoped to 2026/27 so the validation rolls forward cleanly next season.
if current_season == '2026/27':
    javi = [p for p in current_assists if p.get('name') == 'Javi Hernández']
    assert javi and max(p.get('assists', 0) for p in javi) >= 2, f'Javi Hernández assist regression: {javi}'

config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
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
snapshot_teams = set(snapshot.get('teams') or [])
assert 'Barça' not in snapshot_teams and 'Barca' not in snapshot_teams, 'Barcelona short name leaked into snapshot'
assert 'Athletic' not in snapshot_teams, 'Athletic short name leaked into snapshot'
assert 'FC Barcelona' in snapshot_teams, 'FC Barcelona canonical name missing from snapshot'
assert 'Athletic Club' in snapshot_teams, 'Athletic Club canonical name missing from snapshot'
predictions = model.get('predictions') or {}
assert len(predictions) == len(snapshot.get('fixtures') or []), 'every upcoming fixture must have a trained prediction'
for key, pred in predictions.items():
    probs = [pred.get('hp', 0), pred.get('dp', 0), pred.get('ap', 0)]
    expected = 'HDA'[max(range(3), key=lambda i: probs[i])]
    pick = pred.get('pick') or {}
    assert pick.get('outcome') == expected, f'score pick contradicts 1X2 favourite for {key}: {pred}'
    scenarios = pred.get('scenarios') or {}
    assert set(scenarios) == {'H', 'D', 'A'}, f'missing outcome score scenarios for {key}'
    assert pred.get('favouredOutcome') == expected, f'favoured score class contradicts 1X2 favourite for {key}'
    favoured = pred.get('favouredScores') or []
    assert len(favoured) == 3, f'expected three favoured scorelines for {key}: {favoured}'
    assert all(x.get('outcome') == expected for x in favoured), f'contradictory scoreline in favoured set for {key}: {favoured}'
    conditional = [x.get('conditional', 0) for x in favoured]
    assert conditional == sorted(conditional, reverse=True), f'favoured scorelines not ranked for {key}: {favoured}'

html = (ROOT / 'index.html').read_text(encoding='utf-8')
assert 'const DATA={' in html
assert 'const PREDICTION_MODEL={' in html
assert '__DATA_JSON__' not in html and '__LAST_UPDATED__' not in html
assert '1928/29' in html and current_season in html
assert '<section id="stats" class="view"></section>' in html
assert 'data-v="stats"' in html
assert 'CLUB CLEAN SHEETS' in html and 'TOP GOAL SCORERS' in html and 'TOP ASSISTS' in html
assert '<section class="view" id="h2h"></section>' in html
assert '<section class="view" id="predictions"></section>' in html
assert 'data-v="players"' not in html
assert 'id="players"' not in html
assert 'Historically trained Poisson + Elo ensemble' in html
assert 'historical hit rate' in html
assert 'LIKELY SCORES ·' in html
assert 'TOP 3 EXACT SCORES' not in html
assert 'MODEL SCORE PICK' not in html and 'OUTCOME SCORE SCENARIOS' not in html
assert 'Barça' not in html and '>Athletic<' not in html
print(
    f'OK: {len(rows):,} match rows; no duplicates; '
    f'Barcelona-Athletic H2H={len(barca_athletic)}; '
    f"prediction holdout={validation['matches']:,}, accuracy={validation['accuracy']:.1%}, "
    f"high-confidence={high['accuracy']:.1%}; dashboard placeholders resolved"
)
