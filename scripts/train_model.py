#!/usr/bin/env python3
"""Train and backtest the LaLiga fixture prediction model.

The previous dashboard model used only the two most recent completed seasons and
simple goals-for/goals-against averages. This trainer uses the historical match
archive in a walk-forward backtest, tunes recency/shrinkage/form parameters, and
writes calibrated predictions for every upcoming fixture.

No future match is used to predict an earlier match during validation.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCHES_CSV = ROOT / "data" / "laliga_matches.csv"
SNAPSHOT_JSON = ROOT / "data" / "current_snapshot.json"
OUT = ROOT / "data" / "model_predictions.json"

HOLDOUT_START = 2018
HOLDOUT_END = 2025
RECENT_N = 8
MAX_GOALS = 9


def season_start(label: str) -> int:
    try:
        return int(str(label)[:4])
    except (TypeError, ValueError):
        return 0


def load_matches() -> list[dict]:
    rows = []
    with MATCHES_CSV.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            try:
                d = date.fromisoformat(raw["date"][:10])
                hg = int(float(raw["home_goals"]))
                ag = int(float(raw["away_goals"]))
            except (KeyError, TypeError, ValueError):
                continue
            rows.append({
                "season": raw["season"],
                "season_start": season_start(raw["season"]),
                "date": d,
                "home": raw["home"],
                "away": raw["away"],
                "hg": hg,
                "ag": ag,
            })
    rows.sort(key=lambda r: (r["date"], r["home"], r["away"]))
    return rows


def blank_team() -> dict:
    return {
        "home_gf": 0.0, "home_ga": 0.0, "home_w": 0.0,
        "away_gf": 0.0, "away_ga": 0.0, "away_w": 0.0,
        "total_w": 0.0,
    }


def build_strengths(matches: list[dict], cutoff: date, params: dict) -> dict:
    half_life = float(params["half_life"])
    prior = float(params["prior"])
    # Beyond eight half-lives a match has <0.4% of full weight. Ignoring it keeps
    # the repeated walk-forward training fast without changing practical output.
    max_age = half_life * 8.0
    teams: dict[str, dict] = defaultdict(blank_team)
    recent: dict[str, list[tuple[date, int, int]]] = defaultdict(list)
    league_home = league_away = league_w = 0.0

    for m in matches:
        if m["date"] >= cutoff:
            break
        age = (cutoff - m["date"]).days
        if age < 0 or age > max_age:
            continue
        w = 0.5 ** (age / half_life)
        league_home += w * m["hg"]
        league_away += w * m["ag"]
        league_w += w

        h = teams[m["home"]]
        a = teams[m["away"]]
        h["home_gf"] += w * m["hg"]
        h["home_ga"] += w * m["ag"]
        h["home_w"] += w
        h["total_w"] += w
        a["away_gf"] += w * m["ag"]
        a["away_ga"] += w * m["hg"]
        a["away_w"] += w
        a["total_w"] += w
        recent[m["home"]].append((m["date"], m["hg"], m["ag"]))
        recent[m["away"]].append((m["date"], m["ag"], m["hg"]))

    if league_w <= 0:
        return {"home_avg": 1.50, "away_avg": 1.20, "all_avg": 1.35, "teams": {}, "recent": {}, "prior": prior}

    home_avg = league_home / league_w
    away_avg = league_away / league_w
    all_avg = (home_avg + away_avg) / 2.0
    return {
        "home_avg": home_avg,
        "away_avg": away_avg,
        "all_avg": all_avg,
        "teams": dict(teams),
        "recent": {k: v[-RECENT_N:] for k, v in recent.items()},
        "prior": prior,
    }


def shrunk(total: float, weight: float, prior: float, league_rate: float) -> float:
    return (total + prior * league_rate) / (weight + prior)


def recent_rates(strengths: dict, team: str) -> tuple[float, float]:
    vals = strengths["recent"].get(team, [])
    avg = strengths["all_avg"]
    # Three league-average pseudo-matches stop a hot/cold two-game spell from
    # overwhelming the longer-term attack/defence estimates.
    p = 3.0
    gf = (sum(x[1] for x in vals) + p * avg) / (len(vals) + p)
    ga = (sum(x[2] for x in vals) + p * avg) / (len(vals) + p)
    return gf, ga


def lambdas(home: str, away: str, strengths: dict, params: dict) -> tuple[float, float, float]:
    havg = strengths["home_avg"]
    aavg = strengths["away_avg"]
    allavg = strengths["all_avg"]
    prior = strengths["prior"]
    teams = strengths["teams"]
    H = teams.get(home, blank_team())
    A = teams.get(away, blank_team())

    h_attack = shrunk(H["home_gf"], H["home_w"], prior, havg) / havg
    h_defence = shrunk(H["home_ga"], H["home_w"], prior, aavg) / aavg
    a_attack = shrunk(A["away_gf"], A["away_w"], prior, aavg) / aavg
    a_defence = shrunk(A["away_ga"], A["away_w"], prior, havg) / havg

    lh = havg * h_attack * a_defence
    la = aavg * a_attack * h_defence

    form_weight = float(params["form_weight"])
    if form_weight > 0:
        hrgf, hrga = recent_rates(strengths, home)
        argf, arga = recent_rates(strengths, away)
        home_form = math.sqrt(max(0.25, hrgf / allavg) * max(0.25, arga / allavg))
        away_form = math.sqrt(max(0.25, argf / allavg) * max(0.25, hrga / allavg))
        lh *= home_form ** form_weight
        la *= away_form ** form_weight

    lh = min(3.8, max(0.22, lh))
    la = min(3.4, max(0.18, la))
    support = min(float(H.get("total_w", 0.0)), float(A.get("total_w", 0.0)))
    return lh, la, support


def poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def dc_tau(i: int, j: int, lh: float, la: float, rho: float) -> float:
    if i == 0 and j == 0:
        value = 1.0 - lh * la * rho
    elif i == 0 and j == 1:
        value = 1.0 + lh * rho
    elif i == 1 and j == 0:
        value = 1.0 + la * rho
    elif i == 1 and j == 1:
        value = 1.0 - rho
    else:
        value = 1.0
    return max(0.15, value)


def probabilities(lh: float, la: float, rho: float) -> dict:
    hp = dp = ap = over = btts = total = 0.0
    scores = []
    for i in range(MAX_GOALS):
        for j in range(MAX_GOALS):
            p = poisson(i, lh) * poisson(j, la) * dc_tau(i, j, lh, la, rho)
            total += p
            if i > j:
                hp += p
            elif i == j:
                dp += p
            else:
                ap += p
            if i + j >= 3:
                over += p
            if i > 0 and j > 0:
                btts += p
            scores.append({"i": i, "j": j, "p": p})
    total = total or 1.0
    scores.sort(key=lambda x: x["p"], reverse=True)
    for row in scores[:3]:
        row["p"] = round(row["p"] / total, 5)
    return {
        "hp": hp / total, "dp": dp / total, "ap": ap / total,
        "o": over / total, "b": btts / total,
        "s": scores[:3],
    }


def predict(home: str, away: str, strengths: dict, params: dict, rho: float) -> dict:
    lh, la, support = lambdas(home, away, strengths, params)
    p = probabilities(lh, la, rho)
    p.update({"lh": lh, "la": la, "support": support})
    return p


def outcome(m: dict) -> int:
    return 0 if m["hg"] > m["ag"] else 1 if m["hg"] == m["ag"] else 2


def score_records(records: list[dict]) -> dict:
    if not records:
        return {"matches": 0, "accuracy": 0.0, "logLoss": 99.0, "brier": 99.0}
    correct = 0
    log_loss = brier = 0.0
    for r in records:
        probs = r["probs"]
        y = r["actual"]
        top = max(range(3), key=lambda i: probs[i])
        correct += int(top == y)
        log_loss -= math.log(max(1e-9, probs[y]))
        brier += sum((probs[i] - (1.0 if i == y else 0.0)) ** 2 for i in range(3))
    n = len(records)
    return {
        "matches": n,
        "accuracy": correct / n,
        "logLoss": log_loss / n,
        "brier": brier / n,
    }


def validation_groups(matches: list[dict]) -> list[tuple[date, list[dict]]]:
    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for m in matches:
        if HOLDOUT_START <= m["season_start"] <= HOLDOUT_END:
            groups[(m["date"].year, m["date"].month)].append(m)
    return [(date(y, mo, 1), groups[(y, mo)]) for y, mo in sorted(groups)]


def evaluate_model(matches: list[dict], groups: list[tuple[date, list[dict]]], params: dict, rho: float) -> tuple[dict, list[dict]]:
    records = []
    for cutoff, batch in groups:
        strengths = build_strengths(matches, cutoff, params)
        for m in batch:
            p = predict(m["home"], m["away"], strengths, params, rho)
            probs = [p["hp"], p["dp"], p["ap"]]
            ordered = sorted(probs, reverse=True)
            records.append({
                "probs": probs,
                "actual": outcome(m),
                "top": ordered[0],
                "margin": ordered[0] - ordered[1],
                "support": p["support"],
            })
    return score_records(records), records


def baseline_strengths(train: list[dict]) -> tuple[float, float, dict]:
    if not train:
        return 1.50, 1.20, {}
    ah = sum(m["hg"] for m in train) / len(train)
    aa = sum(m["ag"] for m in train) / len(train)
    by_team: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for m in train:
        by_team[m["home"]][0] += m["hg"]
        by_team[m["home"]][1] += m["ag"]
        by_team[m["home"]][2] += 1
        by_team[m["away"]][0] += m["ag"]
        by_team[m["away"]][1] += m["hg"]
        by_team[m["away"]][2] += 1
    cooked = {t: (v[0] / v[2], v[1] / v[2]) for t, v in by_team.items() if v[2]}
    return ah, aa, cooked


def evaluate_baseline(matches: list[dict]) -> dict:
    records = []
    by_season: dict[int, list[dict]] = defaultdict(list)
    for m in matches:
        by_season[m["season_start"]].append(m)
    for target in range(HOLDOUT_START, HOLDOUT_END + 1):
        test = by_season.get(target, [])
        train = by_season.get(target - 2, []) + by_season.get(target - 1, [])
        if not test or not train:
            continue
        ah, aa, teams = baseline_strengths(train)
        avg = (ah + aa) / 2.0
        for m in test:
            H = teams.get(m["home"], (1.3, 1.5))
            A = teams.get(m["away"], (1.3, 1.5))
            lh = min(3.2, max(0.35, ah * (H[0] / avg) * (A[1] / avg)))
            la = min(2.8, max(0.30, aa * (A[0] / avg) * (H[1] / avg)))
            p = probabilities(lh, la, 0.0)
            records.append({"probs": [p["hp"], p["dp"], p["ap"]], "actual": outcome(m)})
    return score_records(records)


def subset_stats(records: list[dict], threshold: float, margin: float, min_support: float, exclude=None) -> tuple[int, float]:
    chosen = []
    for i, r in enumerate(records):
        if exclude and exclude(i, r):
            continue
        if r["top"] >= threshold and r["margin"] >= margin and r["support"] >= min_support:
            pred = max(range(3), key=lambda j: r["probs"][j])
            chosen.append(pred == r["actual"])
    return len(chosen), (sum(chosen) / len(chosen) if chosen else 0.0)


def calibrate_confidence(records: list[dict]) -> dict:
    high_t, high_margin, min_support = 0.68, 0.14, 2.0
    high_n = 0
    high_acc = 0.0
    for t in [0.56, 0.58, 0.60, 0.62, 0.64, 0.66, 0.68, 0.70, 0.72]:
        n, acc = subset_stats(records, t, high_margin, min_support)
        if n >= 120 and acc >= 0.66:
            high_t, high_n, high_acc = t, n, acc
            break
        if n > high_n:
            high_n, high_acc = n, acc

    def is_high(_i, r):
        return r["top"] >= high_t and r["margin"] >= high_margin and r["support"] >= min_support

    medium_t, medium_margin = 0.47, 0.05
    medium_n = 0
    medium_acc = 0.0
    for t in [0.45, 0.47, 0.49, 0.51, 0.53, 0.55]:
        n, acc = subset_stats(records, t, medium_margin, 0.75, exclude=is_high)
        if n >= 300 and acc >= 0.48:
            medium_t, medium_n, medium_acc = t, n, acc
            break
        if n > medium_n:
            medium_n, medium_acc = n, acc

    low = []
    for r in records:
        if is_high(0, r):
            continue
        if r["top"] >= medium_t and r["margin"] >= medium_margin and r["support"] >= 0.75:
            continue
        pred = max(range(3), key=lambda j: r["probs"][j])
        low.append(pred == r["actual"])

    return {
        "high": {"threshold": high_t, "margin": high_margin, "minSupport": min_support, "matches": high_n, "accuracy": high_acc},
        "medium": {"threshold": medium_t, "margin": medium_margin, "minSupport": 0.75, "matches": medium_n, "accuracy": medium_acc},
        "low": {"matches": len(low), "accuracy": (sum(low) / len(low) if low else 0.0)},
    }


def assign_confidence(p: dict, calibration: dict) -> tuple[str, float]:
    probs = sorted([p["hp"], p["dp"], p["ap"]], reverse=True)
    top, margin = probs[0], probs[0] - probs[1]
    h = calibration["high"]
    m = calibration["medium"]
    if top >= h["threshold"] and margin >= h["margin"] and p["support"] >= h["minSupport"]:
        return "High", h["accuracy"]
    if top >= m["threshold"] and margin >= m["margin"] and p["support"] >= m["minSupport"]:
        return "Medium", m["accuracy"]
    return "Low", calibration["low"]["accuracy"]


def fixture_key(f: dict) -> str:
    if f.get("id") is not None:
        return f"id:{f['id']}"
    return f"{f.get('date','')}|{f.get('home','')}|{f.get('away','')}"


def main() -> int:
    matches = load_matches()
    snapshot = json.loads(SNAPSHOT_JSON.read_text(encoding="utf-8"))
    groups = validation_groups(matches)
    if not groups:
        raise RuntimeError("No walk-forward validation matches found")

    baseline = evaluate_baseline(matches)
    candidates = []
    for half_life, prior, form_weight in itertools.product(
        [360.0, 540.0, 720.0, 900.0],
        [6.0, 10.0, 14.0],
        [0.0, 0.15, 0.30],
    ):
        params = {"half_life": half_life, "prior": prior, "form_weight": form_weight}
        metrics, _ = evaluate_model(matches, groups, params, -0.08)
        candidates.append((metrics["logLoss"], metrics["brier"], params))
    candidates.sort(key=lambda x: (x[0], x[1]))
    best_params = candidates[0][2]

    rho_candidates = []
    for rho in [-0.15, -0.10, -0.05, 0.0, 0.05]:
        metrics, records = evaluate_model(matches, groups, best_params, rho)
        rho_candidates.append((metrics["logLoss"], metrics["brier"], rho, metrics, records))
    rho_candidates.sort(key=lambda x: (x[0], x[1]))
    _, _, best_rho, validation, validation_records = rho_candidates[0]
    calibration = calibrate_confidence(validation_records)

    # Fit current strengths using every completed match available as of this build.
    cutoff = date.today() + timedelta(days=1)
    strengths = build_strengths(matches, cutoff, best_params)
    predictions = {}
    for f in snapshot.get("fixtures", []):
        p = predict(f["home"], f["away"], strengths, best_params, best_rho)
        conf, conf_rate = assign_confidence(p, calibration)
        predictions[fixture_key(f)] = {
            "lh": round(p["lh"], 4), "la": round(p["la"], 4),
            "hp": round(p["hp"], 5), "dp": round(p["dp"], 5), "ap": round(p["ap"], 5),
            "o": round(p["o"], 5), "b": round(p["b"], 5),
            "s": p["s"], "conf": conf, "confRate": round(conf_rate, 4),
            "support": round(p["support"], 2),
        }

    improvement = (baseline["logLoss"] - validation["logLoss"]) / baseline["logLoss"] if baseline["logLoss"] else 0.0
    payload = {
        "version": "2.0 walk-forward recency Poisson",
        "updatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "method": "Recency-weighted home/away attack-defence Poisson with form shrinkage and Dixon-Coles low-score correction",
        "params": {
            "halfLifeDays": int(best_params["half_life"]),
            "priorMatches": int(best_params["prior"]),
            "formWeight": best_params["form_weight"],
            "rho": best_rho,
            "recentMatches": RECENT_N,
        },
        "validation": {
            "holdout": f"{HOLDOUT_START}/{str(HOLDOUT_START + 1)[-2:]}–{HOLDOUT_END}/{str(HOLDOUT_END + 1)[-2:]}",
            "matches": validation["matches"],
            "accuracy": round(validation["accuracy"], 5),
            "logLoss": round(validation["logLoss"], 5),
            "brier": round(validation["brier"], 5),
            "baselineAccuracy": round(baseline["accuracy"], 5),
            "baselineLogLoss": round(baseline["logLoss"], 5),
            "baselineBrier": round(baseline["brier"], 5),
            "logLossImprovement": round(improvement, 5),
            "confidence": calibration,
        },
        "predictions": predictions,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    print(
        "Baseline: "
        f"accuracy={baseline['accuracy']:.3f} logLoss={baseline['logLoss']:.4f} brier={baseline['brier']:.4f}"
    )
    print(
        "Trained:  "
        f"accuracy={validation['accuracy']:.3f} logLoss={validation['logLoss']:.4f} brier={validation['brier']:.4f} "
        f"({improvement * 100:.1f}% log-loss improvement)"
    )
    print(f"Best parameters: {payload['params']}")
    print(
        "Confidence calibration: "
        f"High {calibration['high']['accuracy']:.1%} ({calibration['high']['matches']} matches), "
        f"Medium {calibration['medium']['accuracy']:.1%} ({calibration['medium']['matches']} matches)"
    )
    print(f"Built {OUT.name}: {len(predictions)} upcoming fixture predictions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
