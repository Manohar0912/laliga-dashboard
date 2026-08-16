#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Missing target for {label}")
    return text.replace(old, new, 1)

# Model: keep the calibrated 1X2 forecast as the decision layer, then rank
# scorelines only inside the favoured result class. This makes the scoreline
# recommendation interpretable and consistent with the headline prediction.
p = ROOT / "scripts" / "train_model_ensemble.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    'def aligned_scorelines(lh: float, la: float, rho: float, target_probs: list[float]) -> tuple[list[dict], dict, dict]:',
    'def aligned_scorelines(lh: float, la: float, rho: float, target_probs: list[float]) -> tuple[list[dict], dict, dict, list[dict], str]:',
    'aligned scoreline signature',
)
s = replace_once(
    s,
    '''    favourite = max(range(3), key=lambda idx: targets[idx])\n    pick = {**best[favourite], "p": round(best[favourite]["p"], 5)}\n    return top, scenarios, pick\n''',
    '''    favourite = max(range(3), key=lambda idx: targets[idx])\n    fav_code = "HDA"[favourite]\n    pick = {**best[favourite], "p": round(best[favourite]["p"], 5)}\n    fav_total = targets[favourite] or 1.0\n    fav_pool = sorted(\n        (row for row in adjusted if row["outcome"] == fav_code),\n        key=lambda row: row["p"], reverse=True\n    )[:3]\n    favoured_scores = [\n        {**row, "p": round(row["p"], 5), "conditional": round(row["p"] / fav_total, 5)}\n        for row in fav_pool\n    ]\n    return top, scenarios, pick, favoured_scores, fav_code\n''',
    'favoured scoreline calculation',
)
s = replace_once(
    s,
    '''        scorelines, scenarios, score_pick = aligned_scorelines(\n            pp["lh"], pp["la"], best_rho, [pp["hp"], pp["dp"], pp["ap"]]\n        )\n''',
    '''        scorelines, scenarios, score_pick, favoured_scores, favoured_outcome = aligned_scorelines(\n            pp["lh"], pp["la"], best_rho, [pp["hp"], pp["dp"], pp["ap"]]\n        )\n''',
    'aligned scoreline unpack',
)
s = replace_once(
    s,
    '''            "o": round(pp["o"], 5), "b": round(pp["b"], 5), "s": scorelines,\n            "scenarios": scenarios, "pick": score_pick,\n''',
    '''            "o": round(pp["o"], 5), "b": round(pp["b"], 5), "s": scorelines,\n            "scenarios": scenarios, "pick": score_pick,\n            "favouredScores": favoured_scores, "favouredOutcome": favoured_outcome,\n''',
    'prediction payload favoured scores',
)
s = s.replace('"version": "2.2 outcome-aligned Poisson + Elo ensemble"', '"version": "2.3 favourite-conditioned scoreline ensemble"', 1)
s = s.replace(
    '"method": "Walk-forward ensemble: recency-weighted home/away Poisson plus Elo team strength; Dixon-Coles correction, calibrated confidence, and exact-score marginals aligned to final 1X2 probabilities"',
    '"method": "Walk-forward ensemble: recency-weighted home/away Poisson plus Elo team strength; Dixon-Coles correction and calibrated confidence. Displayed scorelines are ranked conditionally within the highest-probability 1X2 outcome."',
    1,
)
p.write_text(s, encoding="utf-8")

# Dashboard: scoreline card follows the favoured outcome rather than ranking
# unconditional exact scores, which could put a draw above a favoured team win.
p = ROOT / "template_parts" / "part04.html"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    "function topScoreRows(p){return [...(p.s||[])].sort((a,b)=>b.p-a.p).slice(0,3)}",
    "function favouredScoreRows(p){if(p.favouredScores?.length)return p.favouredScores;const probs=[p.hp,p.dp,p.ap],idx=probs.indexOf(Math.max(...probs)),code='HDA'[idx],den=probs[idx]||1;return [...(p.s||[])].filter(x=>(x.i>x.j?'H':x.i===x.j?'D':'A')===code).sort((a,b)=>b.p-a.p).slice(0,3).map(x=>({...x,outcome:code,conditional:x.p/den}))}",
    'favoured score rows helper',
)
s = replace_once(
    s,
    "const f=fs[state.fixture],p=pred(f),scoreRows=topScoreRows(p),roundLabel=state.matchday!=null?`Matchday ${state.matchday}`:'Upcoming fixtures',",
    "const f=fs[state.fixture],p=pred(f),scoreRows=favouredScoreRows(p),favCode=p.favouredOutcome||'HDA'[[p.hp,p.dp,p.ap].indexOf(Math.max(p.hp,p.dp,p.ap))],favTitle=favCode==='H'?`${f.home} WIN`:favCode==='A'?`${f.away} WIN`:'DRAW',roundLabel=state.matchday!=null?`Matchday ${state.matchday}`:'Upcoming fixtures',",
    'favoured score render variables',
)
old_card = '''<div class="grid g2"><div class="card"><div class="eyebrow">TOP 3 EXACT SCORES</div><p class="muted" style="margin:6px 0 12px">These are the three most likely individual scorelines. The Home / Draw / Away percentages above are aggregate probabilities across all scorelines.</p>${scoreRows.map((x,i)=>`<div class="bar"><span><b style="margin-right:8px">${i+1}.</b>${x.i}–${x.j}</span><div class="track"><div class="fill" style="width:${Math.min(100,x.p*500)}%"></div></div><b>${pct(x.p)}</b></div>`).join('')}</div><div class="card"><div class="eyebrow">MODEL VALIDATION</div>'''
new_card = '''<div class="grid g2"><div class="card"><div class="eyebrow">LIKELY SCORES · ${esc(favTitle)}</div><p class="muted" style="margin:6px 0 12px">The scorelines below are ranked only within the model's favoured result. Percentages show the share of that favoured outcome represented by each scoreline.</p>${scoreRows.map((x,i)=>`<div class="bar"><span><b style="margin-right:8px">${i+1}.</b>${x.i}–${x.j}</span><div class="track"><div class="fill" style="width:${Math.min(100,(x.conditional??x.p)*100)}%"></div></div><b>${pct(x.conditional??x.p)}</b></div>`).join('')}</div><div class="card"><div class="eyebrow">MODEL VALIDATION</div>'''
s = replace_once(s, old_card, new_card, 'favoured scoreline card')
p.write_text(s, encoding="utf-8")

# Validation: the three displayed scorelines must all belong to the highest
# probability result class. This prevents a favoured away win from ever showing
# a draw as the scoreline recommendation again.
p = ROOT / "scripts" / "validate.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    '''    scenarios = pred.get('scenarios') or {}\n    assert set(scenarios) == {'H', 'D', 'A'}, f'missing outcome score scenarios for {key}'\n''',
    '''    scenarios = pred.get('scenarios') or {}\n    assert set(scenarios) == {'H', 'D', 'A'}, f'missing outcome score scenarios for {key}'\n    assert pred.get('favouredOutcome') == expected, f'favoured score class contradicts 1X2 favourite for {key}'\n    favoured = pred.get('favouredScores') or []\n    assert len(favoured) == 3, f'expected three favoured scorelines for {key}: {favoured}'\n    assert all(x.get('outcome') == expected for x in favoured), f'contradictory scoreline in favoured set for {key}: {favoured}'\n    conditional = [x.get('conditional', 0) for x in favoured]\n    assert conditional == sorted(conditional, reverse=True), f'favoured scorelines not ranked for {key}: {favoured}'\n''',
    'favoured scoreline validation',
)
s = replace_once(
    s,
    "assert 'TOP 3 EXACT SCORES' in html\nassert 'MODEL SCORE PICK' not in html and 'OUTCOME SCORE SCENARIOS' not in html\n",
    "assert 'LIKELY SCORES ·' in html\nassert 'TOP 3 EXACT SCORES' not in html\nassert 'MODEL SCORE PICK' not in html and 'OUTCOME SCORE SCENARIOS' not in html\n",
    'scoreline UI validation',
)
p.write_text(s, encoding="utf-8")

print('Applied favourite-conditioned scoreline display and validation.')
