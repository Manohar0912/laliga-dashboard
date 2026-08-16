#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Missing target for {label}")
    return text.replace(old, new, 1)

p = ROOT / "template_parts" / "part04.html"
s = p.read_text(encoding="utf-8")

old_helpers = """function scoreScenarioRows(p){const probs={H:p.hp,D:p.dp,A:p.ap},labels={H:'Home win',D:'Draw',A:'Away win'},given=p.scenarios||{},rows=[];for(const o of ['H','D','A']){let x=given[o];if(!x){x=(p.s||[]).filter(r=>(r.i>r.j?'H':r.i===r.j?'D':'A')===o).sort((a,b)=>b.p-a.p)[0]}if(x)rows.push({...x,outcome:o,label:labels[o],outcomeProb:probs[o]})}return rows.sort((a,b)=>b.outcomeProb-a.outcomeProb)}
function modelScorePick(p){if(p.pick)return {...p.pick,label:{H:'Home win',D:'Draw',A:'Away win'}[p.pick.outcome]};const rows=scoreScenarioRows(p);return rows[0]||null}
"""
new_helpers = """function topScoreRows(p){return [...(p.s||[])].sort((a,b)=>b.p-a.p).slice(0,3)}
"""
s = replace_once(s, old_helpers, new_helpers, "scoreline helpers")

s = replace_once(
    s,
    "const f=fs[state.fixture],p=pred(f),scoreScenarios=scoreScenarioRows(p),scorePick=modelScorePick(p),roundLabel=state.matchday!=null?`Matchday ${state.matchday}`:'Upcoming fixtures',",
    "const f=fs[state.fixture],p=pred(f),scoreRows=topScoreRows(p),roundLabel=state.matchday!=null?`Matchday ${state.matchday}`:'Upcoming fixtures',",
    "render score variables",
)

old_card = """<div class=\"grid g2\"><div class=\"card\"><div class=\"eyebrow\">MODEL SCORE PICK</div><h3>${scorePick?`${esc(scorePick.label)} · ${scorePick.i}–${scorePick.j}`:'—'}</h3><p class=\"muted\">The primary score pick now comes from the model's highest-probability result class, so it stays consistent with the Home / Draw / Away forecast.</p><div class=\"eyebrow\" style=\"margin-top:16px\">OUTCOME SCORE SCENARIOS</div>${scoreScenarios.map(x=>`<div class=\"bar\"><span>${esc(x.label)} · ${x.i}–${x.j}</span><div class=\"track\"><div class=\"fill\" style=\"width:${Math.min(100,x.p*500)}%\"></div></div><b>${pct(x.p)}</b></div>`).join('')}</div><div class=\"card\"><div class=\"eyebrow\">MODEL VALIDATION</div>"""
new_card = """<div class=\"grid g2\"><div class=\"card\"><div class=\"eyebrow\">TOP 3 EXACT SCORES</div><p class=\"muted\" style=\"margin:6px 0 12px\">These are the three most likely individual scorelines. The Home / Draw / Away percentages above are aggregate probabilities across all scorelines.</p>${scoreRows.map((x,i)=>`<div class=\"bar\"><span><b style=\"margin-right:8px\">${i+1}.</b>${x.i}–${x.j}</span><div class=\"track\"><div class=\"fill\" style=\"width:${Math.min(100,x.p*500)}%\"></div></div><b>${pct(x.p)}</b></div>`).join('')}</div><div class=\"card\"><div class=\"eyebrow\">MODEL VALIDATION</div>"""
s = replace_once(s, old_card, new_card, "scoreline card")
p.write_text(s, encoding="utf-8")

p = ROOT / "scripts" / "validate.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    "assert 'MODEL SCORE PICK' in html and 'OUTCOME SCORE SCENARIOS' in html\n",
    "assert 'TOP 3 EXACT SCORES' in html\nassert 'MODEL SCORE PICK' not in html and 'OUTCOME SCORE SCENARIOS' not in html\n",
    "scoreline UI validation",
)
p.write_text(s, encoding="utf-8")

print("Simplified Predictions to top-three exact scorelines.")
