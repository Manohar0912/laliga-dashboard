#!/usr/bin/env python3
import csv
from pathlib import Path

path = Path('data/laliga_matches.csv')
with path.open(newline='', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))
fields = rows[0].keys() if rows else [
    'season','date','home','away','home_goals','away_goals','ht_home_goals','ht_away_goals',
    'home_shots','away_shots','home_sot','away_sot','home_fouls','away_fouls','home_corners',
    'away_corners','home_yellow','away_yellow','home_red','away_red'
]
repairs = [
    ('2026/27','2026-08-30','RC Deportivo','Valencia CF','3','1','2','1'),
    ('2026/27','2026-08-30','Celta Vigo','Athletic Club','0','2','0','2'),
]
existing = {(r['season'], r['home'], r['away']) for r in rows}
for season,date,home,away,hg,ag,hhg,hag in repairs:
    key = (season,home,away)
    if key in existing:
        continue
    row = {k: '' for k in fields}
    row.update({'season':season,'date':date,'home':home,'away':away,'home_goals':hg,'away_goals':ag,'ht_home_goals':hhg,'ht_away_goals':hag})
    rows.append(row)
    existing.add(key)
rows.sort(key=lambda r: (r['season'], r['date'], r['home'], r['away']))
with path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(fields))
    w.writeheader(); w.writerows(rows)
print('Repaired persisted Aug 30 results:', [(x[2], x[3], x[4], x[5]) for x in repairs])
