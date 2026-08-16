#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT / path).read_text(encoding='utf-8')

def write(path, text):
    (ROOT / path).write_text(text, encoding='utf-8')

# Remove Players from header/nav/view.
p = read('template_parts/part01.html')
p = p.replace('1928/29 onward · teams · players · H2H · predictions', '1928/29 onward · teams · H2H · predictions')
p = p.replace('<button data-v="players">PLAYERS</button>', '')
p = p.replace('<section id="players" class="view"></section>', '')
write('template_parts/part01.html', p)

# Remove player-only state.
p = read('template_parts/part02.html')
p = p.replace(',player:null,pa:null,pb:null', '')
write('template_parts/part02.html', p)

# Remove all player renderer code while preserving H2H code and the template boundary.
p = read('template_parts/part03.html')
start = p.find('function pnum(')
end = p.find('function h2hMs()')
if start < 0 or end < 0 or end <= start:
    raise RuntimeError('Could not locate Players renderer block in part03.html')
p = p[:start] + p[end:]
write('template_parts/part03.html', p)

# Remove Players from the renderer registry.
p = read('template_parts/part04.html')
p = p.replace(',players:renderPlayers', '')
write('template_parts/part04.html', p)

# Simplify production automation: nightly results/model refresh only.
p = read('.github/workflows/update-laliga.yml')
p = p.replace("      - 'scripts/update_players.py'\n", '')
p = p.replace("    # Weekly deeper refresh also updates the player analytics catalogue.\n    - cron: '17 5 * * 2'\n", '')
p = p.replace("\n      - name: Refresh player analytics\n        if: github.event_name != 'schedule' || github.event.schedule == '17 5 * * 2'\n        run: python scripts/update_players.py\n", '')
p = p.replace(' data/player_data.json', '')
write('.github/workflows/update-laliga.yml', p)

# Remove player-specific validation and explicitly guard against the tab returning.
p = read('scripts/validate.py')
start = p.find("player_path = ROOT / 'data/player_data.json'")
end = p.find("model_path = ROOT / 'data/model_predictions.json'")
if start < 0 or end < 0 or end <= start:
    raise RuntimeError('Could not locate player validation block')
p = p[:start] + p[end:]
p = p.replace("assert 'playerProfiles' in html and 'Kylian Mbappé' in html\n", '')
p = p.replace("assert 'PLAYER VS TEAM' in html and 'Performance across seasons' in html\n", '')
p = p.replace("    f'{len(profiles)} player profiles; Mbappé-Barcelona matches={len(mbappe_barca)}; '\n", '')
needle = "assert '<section class=\"view\" id=\"predictions\"></section>' in html\n"
replacement = needle + "assert 'data-v=\"players\"' not in html\nassert 'id=\"players\"' not in html\n"
if needle not in p:
    raise RuntimeError('Could not locate dashboard section validation')
p = p.replace(needle, replacement, 1)
write('scripts/validate.py', p)

# Update repository documentation.
p = read('README.md')
p = p.replace('- team and player explorers', '- team intelligence and season match-centre analytics')
p = p.replace('- weekly validation and rebuild through GitHub Actions', '- nightly validation, model retraining and rebuild through GitHub Actions')
p = p.replace('The automated refresh is designed to run every Tuesday after the weekend/Monday match round, with a manual workflow trigger available for on-demand updates.', 'The automated refresh runs nightly to capture completed results, retrain predictions, validate the build and redeploy the dashboard. A manual workflow trigger remains available for on-demand updates.')
write('README.md', p)

# Remove the now-unused external player feed and cached player dataset.
(ROOT / 'scripts/update_players.py').unlink(missing_ok=True)
(ROOT / 'data/player_data.json').unlink(missing_ok=True)

print('Players section and player refresh pipeline removed.')
