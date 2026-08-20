#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected patch target not found in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# Navigation + view container.
p = ROOT / "template_parts" / "part01.html"
replace(
    p,
    '<div class="sub">1928/29 onward · teams · H2H · predictions</div>',
    '<div class="sub">1928/29 onward · teams · season stats · H2H · predictions</div>',
)
replace(
    p,
    '<button data-v="teams">TEAMS</button><button data-v="h2h">H2H</button>',
    '<button data-v="teams">TEAMS</button><button data-v="stats">SEASON STATS</button><button data-v="h2h">H2H</button>',
)
replace(
    p,
    '<section id="teams" class="view"></section><section class="vie',
    '<section id="teams" class="view"></section><section id="stats" class="view"></section><section class="vie',
)

# Make season_stats.json available in the standalone DATA payload.
p = ROOT / "scripts" / "update_laliga.py"
replace(
    p,
    'SNAPSHOT_JSON = DATA_DIR / "current_snapshot.json"\n',
    'SNAPSHOT_JSON = DATA_DIR / "current_snapshot.json"\nSEASON_STATS_JSON = DATA_DIR / "season_stats.json"\n',
)
replace(
    p,
    '\ndef build_data(rows: list[dict], snapshot: dict, static: dict, config: dict) -> dict:\n',
    '''\ndef load_season_stats() -> dict:\n    if not SEASON_STATS_JSON.exists():\n        return {"seasons": {}}\n    try:\n        payload = json.loads(SEASON_STATS_JSON.read_text(encoding="utf-8"))\n    except Exception as exc:\n        print(f"WARNING: season_stats.json could not be loaded: {exc}", file=sys.stderr)\n        return {"seasons": {}}\n    payload.setdefault("seasons", {})\n    return payload\n\n\ndef build_data(rows: list[dict], snapshot: dict, static: dict, config: dict) -> dict:\n''',
)
replace(
    p,
    '    player_payload = load_player_payload()\n    return {\n',
    '    player_payload = load_player_payload()\n    season_stats = load_season_stats()\n    return {\n',
)
replace(
    p,
    '        "fixtures": snapshot.get("fixtures", []),\n',
    '        "fixtures": snapshot.get("fixtures", []),\n        "seasonStats": season_stats,\n',
)

# Add Season Stats renderer before Predictions.
p = ROOT / "template_parts" / "part04.html"
season_stats_js = r'''
function seasonStatTeams(s){const ms=sm(s),t={};for(const m of ms){for(const name of [m.h,m.a])t[name]??={team:name,p:0,w:0,d:0,l:0,gf:0,ga:0,cs:0,y:0,r:0};const h=t[m.h],a=t[m.a];h.p++;a.p++;h.gf+=m.hg;h.ga+=m.ag;a.gf+=m.ag;a.ga+=m.hg;if(m.hg>m.ag){h.w++;a.l++}else if(m.hg<m.ag){a.w++;h.l++}else{h.d++;a.d++}if(m.ag===0)h.cs++;if(m.hg===0)a.cs++;h.y+=Number.isFinite(m.hy)?m.hy:0;a.y+=Number.isFinite(m.ay)?m.ay:0;h.r+=Number.isFinite(m.hr)?m.hr:0;a.r+=Number.isFinite(m.ar)?m.ar:0}return Object.values(t).map(x=>({...x,gd:x.gf-x.ga}))}
function seasonApiPlayers(s){return (DATA.seasonStats?.seasons?.[s]?.players||[]).map(p=>({name:p.name,team:p.team,m:+p.matches||0,g:+p.goals||0,a:+p.assists||0,pk:+p.penalties||0}))}
function seasonLegacyScorers(s){return (DATA.players?.[s]||[]).map(p=>({name:p.name,team:p.team,m:+p.m||0,g:+p.g||0,a:+p.a||0,pk:+p.pk||0}))}
function playerLeaderTable(rows,key,label){const sorted=[...rows].sort((a,b)=>b[key]-a[key]||b.g-a.g||a.name.localeCompare(b.name)).slice(0,10);if(!sorted.length)return '<div class="empty">Player leaderboard unavailable for this season.</div>';return `<div class="table"><table><thead><tr><th>#</th><th>Player</th><th>Club</th><th>Apps</th><th>${label}</th></tr></thead><tbody>${sorted.map((p,i)=>`<tr><td>${i+1}</td><td class="team">${esc(p.name)}</td><td>${esc(p.team)}</td><td>${p.m||'—'}</td><td><b>${p[key]}</b></td></tr>`).join('')}</tbody></table></div>`}
function teamLeaderTable(rows,key,label,asc=false){const sorted=[...rows].sort((a,b)=>(asc?a[key]-b[key]:b[key]-a[key])||b.gd-a.gd||a.team.localeCompare(b.team)).slice(0,10);return `<div class="table"><table><thead><tr><th>#</th><th>Club</th><th>P</th><th>${label}</th></tr></thead><tbody>${sorted.map((x,i)=>`<tr><td>${i+1}</td><td class="team">${esc(x.team)}</td><td>${x.p}</td><td><b>${x[key]}</b></td></tr>`).join('')}</tbody></table></div>`}
function renderSeasonStats(){const s=state.season,teams=seasonStatTeams(s),api=seasonApiPlayers(s),legacy=seasonLegacyScorers(s),scorers=api.length?api:legacy,assists=api,topScorer=[...scorers].sort((a,b)=>b.g-a.g||b.a-a.a)[0],topAssist=[...assists].sort((a,b)=>b.a-a.a||b.g-a.g)[0],cs=[...teams].sort((a,b)=>b.cs-a.cs||a.ga-b.ga)[0],attack=[...teams].sort((a,b)=>b.gf-a.gf||b.gd-a.gd)[0],defence=[...teams].sort((a,b)=>a.ga-b.ga||b.gd-a.gd)[0],wins=[...teams].sort((a,b)=>b.w-a.w||b.gd-a.gd)[0],hasCards=teams.some(x=>x.y||x.r),coverage=api.length?`Player leaders: football-data.org · ${api.length} players`:(legacy.length?'Goals: archived scorer snapshot · assists unavailable':'Player leaderboards unavailable for this season');$('#stats').innerHTML=`<div class="toolbar"><div><div class="eyebrow">SEASON STATS</div><h2 class="title">${esc(s)} leaders</h2></div><div class="muted">${esc(coverage)}</div></div><div class="grid g6" style="margin-bottom:13px"><div class="card kpi"><span>Top scorer</span><b style="font-size:18px">${topScorer?esc(topScorer.name):'—'}</b><div class="muted">${topScorer?`${topScorer.g} goals · ${esc(topScorer.team)}`:'No player data'}</div></div><div class="card kpi"><span>Assist leader</span><b style="font-size:18px">${topAssist?esc(topAssist.name):'—'}</b><div class="muted">${topAssist?`${topAssist.a} assists · ${esc(topAssist.team)}`:'No reliable assist feed'}</div></div><div class="card kpi"><span>Club clean sheets</span><b style="font-size:18px">${cs?esc(cs.team):'—'}</b><div class="muted">${cs?`${cs.cs} clean sheets`:'No matches'}</div></div><div class="card kpi"><span>Best attack</span><b style="font-size:18px">${attack?esc(attack.team):'—'}</b><div class="muted">${attack?`${attack.gf} goals`:'No matches'}</div></div><div class="card kpi"><span>Best defence</span><b style="font-size:18px">${defence?esc(defence.team):'—'}</b><div class="muted">${defence?`${defence.ga} conceded`:'No matches'}</div></div><div class="card kpi"><span>Most wins</span><b style="font-size:18px">${wins?esc(wins.team):'—'}</b><div class="muted">${wins?`${wins.w} wins`:'No matches'}</div></div></div><div class="grid g2" style="margin-bottom:13px"><div class="card"><div class="eyebrow">TOP GOAL SCORERS</div><div style="margin-top:10px">${playerLeaderTable(scorers,'g','Goals')}</div></div><div class="card"><div class="eyebrow">TOP ASSISTS</div><div style="margin-top:10px">${playerLeaderTable(assists,'a','Assists')}</div></div></div><div class="grid g2"><div class="card"><div class="eyebrow">CLUB CLEAN SHEETS</div><div style="margin-top:10px">${teamLeaderTable(teams,'cs','CS')}</div></div><div class="card"><div class="eyebrow">BEST ATTACKS</div><div style="margin-top:10px">${teamLeaderTable(teams,'gf','Goals')}</div></div></div>${hasCards?`<div class="grid g2" style="margin-top:13px"><div class="card"><div class="eyebrow">YELLOW CARDS · TEAM</div><div style="margin-top:10px">${teamLeaderTable(teams,'y','YC')}</div></div><div class="card"><div class="eyebrow">RED CARDS · TEAM</div><div style="margin-top:10px">${teamLeaderTable(teams,'r','RC')}</div></div></div>`:''}`}
'''
replace(p, '\nfunction renderPredictions(){', '\n' + season_stats_js + '\nfunction renderPredictions(){')
replace(
    p,
    'const renders={overview:renderOverview,matches:renderMatches,teams:renderTeams,h2h:renderH2H,predictions:renderPredictions};',
    'const renders={overview:renderOverview,matches:renderMatches,teams:renderTeams,stats:renderSeasonStats,h2h:renderH2H,predictions:renderPredictions};',
)

# Validation coverage.
p = ROOT / "scripts" / "validate.py"
replace(
    p,
    "snapshot = json.loads((ROOT / 'data/current_snapshot.json').read_text(encoding='utf-8'))\n",
    "snapshot = json.loads((ROOT / 'data/current_snapshot.json').read_text(encoding='utf-8'))\nseason_stats = json.loads((ROOT / 'data/season_stats.json').read_text(encoding='utf-8'))\ncurrent_players = ((season_stats.get('seasons') or {}).get('2026/27') or {}).get('players') or []\nassert current_players, 'current-season player leaderboards are empty'\n",
)
replace(
    p,
    "assert '<section class=\"view\" id=\"h2h\"></section>' in html\n",
    "assert '<section id=\"stats\" class=\"view\"></section>' in html\nassert 'data-v=\"stats\"' in html\nassert 'CLUB CLEAN SHEETS' in html and 'TOP GOAL SCORERS' in html and 'TOP ASSISTS' in html\nassert '<section class=\"view\" id=\"h2h\"></section>' in html\n",
)

print('Applied Season Stats tab patch.')
