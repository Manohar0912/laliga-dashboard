#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Missing target for {label}")
    return text.replace(old, new, 1)

# 1) Prefer full official club names from the live API and normalize any
# short-name values already stored in the snapshot.
p = ROOT / "scripts" / "update_laliga.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    '    "Athletic Bilbao": "Athletic Club",\n',
    '    "Athletic Bilbao": "Athletic Club",\n    "Athletic": "Athletic Club",\n',
    "Athletic alias",
)
s = replace_once(
    s,
    '    "Barcelona": "FC Barcelona",\n',
    '    "Barcelona": "FC Barcelona",\n    "Barça": "FC Barcelona",\n    "Barca": "FC Barcelona",\n',
    "Barcelona aliases",
)
s = replace_once(
    s,
    '''    if name in ALIASES:\n        return ALIASES[name]\n    if short_name and short_name in ALIASES:\n        return ALIASES[short_name]\n    return short_name or name\n''',
    '''    # Prefer the API's full club name. Falling back to shortName caused\n    # display values such as "Barça" and "Athletic" to leak into fixtures.\n    if name:\n        return ALIASES.get(name, name)\n    if short_name:\n        return ALIASES.get(short_name, short_name)\n    return ""\n''',
    "canonical_team fallback",
)
normalize_fn = '''\n\ndef normalize_snapshot(snapshot: dict) -> dict:\n    out = dict(snapshot)\n    out["teams"] = sorted({canonical_team(t) for t in snapshot.get("teams", []) if canonical_team(t)})\n    for key in ("fixtures", "finished"):\n        cooked = []\n        for item in snapshot.get(key, []):\n            row = dict(item)\n            row["home"] = canonical_team(row.get("home", ""))\n            row["away"] = canonical_team(row.get("away", ""))\n            cooked.append(row)\n        out[key] = cooked\n    return out\n'''
s = replace_once(s, '\n\ndef read_rows() -> list[dict]:', normalize_fn + '\n\ndef read_rows() -> list[dict]:', "snapshot normalizer")
s = replace_once(
    s,
    '''    if args.offline:\n        snapshot = json.loads(SNAPSHOT_JSON.read_text(encoding="utf-8"))\n    else:\n        snapshot = fetch_live(config)\n        SNAPSHOT_JSON.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")\n\n    rows = merge_current(read_rows(), snapshot, config["currentSeason"])\n''',
    '''    if args.offline:\n        snapshot = json.loads(SNAPSHOT_JSON.read_text(encoding="utf-8"))\n    else:\n        snapshot = fetch_live(config)\n    snapshot = normalize_snapshot(snapshot)\n    # Persist canonical names in both live and offline rebuilds so downstream\n    # prediction training uses the same club identities as the dashboard.\n    SNAPSHOT_JSON.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")\n\n    rows = merge_current(read_rows(), snapshot, config["currentSeason"])\n''',
    "snapshot persistence",
)
p.write_text(s, encoding="utf-8")

# 2) Reconcile exact-score probabilities to the FINAL Poisson+Elo 1X2 marginals.
p = ROOT / "scripts" / "train_model_ensemble.py"
s = p.read_text(encoding="utf-8")
align_fn = '''\n\ndef aligned_scorelines(lh: float, la: float, rho: float, target_probs: list[float]) -> tuple[list[dict], dict, dict]:\n    total_target = sum(target_probs) or 1.0\n    targets = [max(0.0, x) / total_target for x in target_probs]\n    raw = []\n    buckets = [0.0, 0.0, 0.0]\n    for i in range(base.MAX_GOALS):\n        for j in range(base.MAX_GOALS):\n            p = base.poisson(i, lh) * base.poisson(j, la) * base.dc_tau(i, j, lh, la, rho)\n            outcome = 0 if i > j else 1 if i == j else 2\n            raw.append({"i": i, "j": j, "p": p, "outcome_idx": outcome})\n            buckets[outcome] += p\n\n    adjusted = []\n    best = [None, None, None]\n    for row in raw:\n        outcome = row["outcome_idx"]\n        p = row["p"] * (targets[outcome] / buckets[outcome] if buckets[outcome] else 0.0)\n        cooked = {"i": row["i"], "j": row["j"], "p": p, "outcome": "HDA"[outcome]}\n        adjusted.append(cooked)\n        if best[outcome] is None or p > best[outcome]["p"]:\n            best[outcome] = cooked\n\n    adjusted.sort(key=lambda x: x["p"], reverse=True)\n    top = [{**row, "p": round(row["p"], 5)} for row in adjusted[:3]]\n    scenarios = {\n        "HDA"[idx]: {**row, "p": round(row["p"], 5)}\n        for idx, row in enumerate(best) if row is not None\n    }\n    favourite = max(range(3), key=lambda idx: targets[idx])\n    pick = {**best[favourite], "p": round(best[favourite]["p"], 5)}\n    return top, scenarios, pick\n'''
s = replace_once(s, '\n\ndef main() -> int:', align_fn + '\n\ndef main() -> int:', "aligned scoreline function")
s = replace_once(
    s,
    '''        pp["hp"] = blend * pp["hp"] + (1.0 - blend) * ep[0]\n        pp["dp"] = blend * pp["dp"] + (1.0 - blend) * ep[1]\n        pp["ap"] = blend * pp["ap"] + (1.0 - blend) * ep[2]\n        conf, conf_rate = base.assign_confidence(pp, calibration)\n''',
    '''        pp["hp"] = blend * pp["hp"] + (1.0 - blend) * ep[0]\n        pp["dp"] = blend * pp["dp"] + (1.0 - blend) * ep[1]\n        pp["ap"] = blend * pp["ap"] + (1.0 - blend) * ep[2]\n        scorelines, scenarios, score_pick = aligned_scorelines(\n            pp["lh"], pp["la"], best_rho, [pp["hp"], pp["dp"], pp["ap"]]\n        )\n        conf, conf_rate = base.assign_confidence(pp, calibration)\n''',
    "scoreline alignment call",
)
s = replace_once(
    s,
    '''            "hp": round(pp["hp"], 5), "dp": round(pp["dp"], 5), "ap": round(pp["ap"], 5),\n            "o": round(pp["o"], 5), "b": round(pp["b"], 5), "s": pp["s"],\n            "conf": conf, "confRate": round(conf_rate, 4), "support": round(pp["support"], 2),\n''',
    '''            "hp": round(pp["hp"], 5), "dp": round(pp["dp"], 5), "ap": round(pp["ap"], 5),\n            "o": round(pp["o"], 5), "b": round(pp["b"], 5), "s": scorelines,\n            "scenarios": scenarios, "pick": score_pick,\n            "conf": conf, "confRate": round(conf_rate, 4), "support": round(pp["support"], 2),\n''',
    "prediction payload scorelines",
)
s = s.replace('"version": "2.1 historical Poisson + Elo ensemble"', '"version": "2.2 outcome-aligned Poisson + Elo ensemble"', 1)
s = s.replace(
    '"method": "Walk-forward ensemble: recency-weighted home/away Poisson plus Elo team strength; Dixon-Coles correction and calibrated confidence"',
    '"method": "Walk-forward ensemble: recency-weighted home/away Poisson plus Elo team strength; Dixon-Coles correction, calibrated confidence, and exact-score marginals aligned to final 1X2 probabilities"',
    1,
)
p.write_text(s, encoding="utf-8")

# 3) Make the dashboard's scoreline recommendation explicitly outcome-consistent.
p = ROOT / "template_parts" / "part04.html"
s = p.read_text(encoding="utf-8")n = s
helper_js = '''\nfunction scoreScenarioRows(p){const probs={H:p.hp,D:p.dp,A:p.ap},labels={H:'Home win',D:'Draw',A:'Away win'},given=p.scenarios||{},rows=[];for(const o of ['H','D','A']){let x=given[o];if(!x){x=(p.s||[]).filter(r=>(r.i>r.j?'H':r.i===r.j?'D':'A')===o).sort((a,b)=>b.p-a.p)[0]}if(x)rows.push({...x,outcome:o,label:labels[o],outcomeProb:probs[o]})}return rows.sort((a,b)=>b.outcomeProb-a.outcomeProb)}\nfunction modelScorePick(p){if(p.pick)return {...p.pick,label:{H:'Home win',D:'Draw',A:'Away win'}[p.pick.outcome]};const rows=scoreScenarioRows(p);return rows[0]||null}\n'''
s = replace_once(s, '\nfunction renderPredictions(){', helper_js + '\nfunction renderPredictions(){', "score scenario JS helpers")
s = replace_once(
    s,
    "const f=fs[state.fixture],p=pred(f),roundLabel=state.matchday!=null?`Matchday ${state.matchday}`:'Upcoming fixtures',",
    "const f=fs[state.fixture],p=pred(f),scoreScenarios=scoreScenarioRows(p),scorePick=modelScorePick(p),roundLabel=state.matchday!=null?`Matchday ${state.matchday}`:'Upcoming fixtures',",
    "prediction render variables",
)
old_card = '''<div class="grid g2"><div class="card"><div class="eyebrow">LIKELY SCORES</div>${p.s.map(x=>`<div class="bar"><span>${x.i}–${x.j}</span><div class="track"><div class="fill" style="width:${Math.min(100,x.p*500)}%"></div></div><b>${pct(x.p)}</b></div>`).join('')}</div><div class="card"><div class="eyebrow">MODEL VALIDATION</div>'''
new_card = '''<div class="grid g2"><div class="card"><div class="eyebrow">MODEL SCORE PICK</div><h3>${scorePick?`${esc(scorePick.label)} · ${scorePick.i}–${scorePick.j}`:'—'}</h3><p class="muted">The primary score pick now comes from the model's highest-probability result class, so it stays consistent with the Home / Draw / Away forecast.</p><div class="eyebrow" style="margin-top:16px">OUTCOME SCORE SCENARIOS</div>${scoreScenarios.map(x=>`<div class="bar"><span>${esc(x.label)} · ${x.i}–${x.j}</span><div class="track"><div class="fill" style="width:${Math.min(100,x.p*500)}%"></div></div><b>${pct(x.p)}</b></div>`).join('')}</div><div class="card"><div class="eyebrow">MODEL VALIDATION</div>'''
s = replace_once(s, old_card, new_card, "prediction score card")
p.write_text(s, encoding="utf-8")

# 4) Strengthen validation around canonical display names and score-pick logic.
p = ROOT / "scripts" / "validate.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    '''snapshot = json.loads((ROOT / 'data/current_snapshot.json').read_text(encoding='utf-8'))\nassert len(model.get('predictions') or {}) == len(snapshot.get('fixtures') or []), 'every upcoming fixture must have a trained prediction'\n''',
    '''snapshot = json.loads((ROOT / 'data/current_snapshot.json').read_text(encoding='utf-8'))\nsnapshot_teams = set(snapshot.get('teams') or [])\nassert 'Barça' not in snapshot_teams and 'Barca' not in snapshot_teams, 'Barcelona short name leaked into snapshot'\nassert 'Athletic' not in snapshot_teams, 'Athletic short name leaked into snapshot'\nassert 'FC Barcelona' in snapshot_teams, 'FC Barcelona canonical name missing from snapshot'\nassert 'Athletic Club' in snapshot_teams, 'Athletic Club canonical name missing from snapshot'\npredictions = model.get('predictions') or {}\nassert len(predictions) == len(snapshot.get('fixtures') or []), 'every upcoming fixture must have a trained prediction'\nfor key, pred in predictions.items():\n    probs = [pred.get('hp', 0), pred.get('dp', 0), pred.get('ap', 0)]\n    expected = 'HDA'[max(range(3), key=lambda i: probs[i])]\n    pick = pred.get('pick') or {}\n    assert pick.get('outcome') == expected, f'score pick contradicts 1X2 favourite for {key}: {pred}'\n    scenarios = pred.get('scenarios') or {}\n    assert set(scenarios) == {'H', 'D', 'A'}, f'missing outcome score scenarios for {key}'\n''',
    "prediction and naming validation",
)
s = replace_once(
    s,
    "assert 'historical hit rate' in html\n",
    "assert 'historical hit rate' in html\nassert 'MODEL SCORE PICK' in html and 'OUTCOME SCORE SCENARIOS' in html\nassert 'Barça' not in html and '>Athletic<' not in html\n",
    "dashboard score UI validation",
)
p.write_text(s, encoding="utf-8")

print("Applied canonical club naming and outcome-aligned scoreline fixes.")
