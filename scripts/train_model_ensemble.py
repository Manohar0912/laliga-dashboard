#!/usr/bin/env python3
"""Train an ensemble of the recency Poisson model and an Elo strength model."""
from __future__ import annotations

import itertools
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import train_model as base


def elo_probs(home_rating: float, away_rating: float, params: dict) -> list[float]:
    diff = home_rating + params["home_adv"] - away_rating
    home_share = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
    draw = params["draw_base"] * math.exp(-abs(diff) / 700.0)
    draw = min(0.32, max(0.12, draw))
    return [(1.0 - draw) * home_share, draw, (1.0 - draw) * (1.0 - home_share)]


def elo_run(matches: list[dict], params: dict, collect_validation: bool) -> tuple[dict[str, float], list[dict]]:
    ratings: dict[str, float] = defaultdict(lambda: 1500.0)
    records = []
    current_season = None
    for m in matches:
        if m["season_start"] < 1995:
            continue
        if current_season is None:
            current_season = m["season_start"]
        elif m["season_start"] != current_season:
            carry = params["carry"]
            for team in list(ratings):
                ratings[team] = 1500.0 + (ratings[team] - 1500.0) * carry
            current_season = m["season_start"]

        rh, ra = ratings[m["home"]], ratings[m["away"]]
        probs = elo_probs(rh, ra, params)
        if collect_validation and base.HOLDOUT_START <= m["season_start"] <= base.HOLDOUT_END:
            records.append({"probs": probs, "actual": base.outcome(m)})

        expected = 1.0 / (1.0 + 10.0 ** (-(rh + params["home_adv"] - ra) / 400.0))
        actual = 1.0 if m["hg"] > m["ag"] else 0.5 if m["hg"] == m["ag"] else 0.0
        margin = 1.0 + 0.12 * min(4, abs(m["hg"] - m["ag"]))
        delta = params["k"] * margin * (actual - expected)
        ratings[m["home"]] += delta
        ratings[m["away"]] -= delta
    return dict(ratings), records


def combine_records(poisson_records: list[dict], elo_records: list[dict], weight: float) -> list[dict]:
    if len(poisson_records) != len(elo_records):
        raise RuntimeError(f"Validation alignment mismatch: {len(poisson_records)} vs {len(elo_records)}")
    out = []
    for pr, er in zip(poisson_records, elo_records):
        if pr["actual"] != er["actual"]:
            raise RuntimeError("Validation outcomes are not aligned")
        probs = [weight * pr["probs"][i] + (1.0 - weight) * er["probs"][i] for i in range(3)]
        ordered = sorted(probs, reverse=True)
        out.append({
            "probs": probs,
            "actual": pr["actual"],
            "top": ordered[0],
            "margin": ordered[0] - ordered[1],
            "support": pr["support"],
        })
    return out


def main() -> int:
    matches = base.load_matches()
    snapshot = json.loads(base.SNAPSHOT_JSON.read_text(encoding="utf-8"))
    groups = base.validation_groups(matches)
    baseline = base.evaluate_baseline(matches)

    poisson_candidates = []
    for half_life, prior, form_weight in itertools.product(
        [360.0, 540.0, 720.0, 900.0], [6.0, 10.0, 14.0], [0.0, 0.15, 0.30]
    ):
        params = {"half_life": half_life, "prior": prior, "form_weight": form_weight}
        metrics, _ = base.evaluate_model(matches, groups, params, -0.08)
        poisson_candidates.append((metrics["logLoss"], metrics["brier"], params))
    poisson_candidates.sort(key=lambda x: (x[0], x[1]))
    best_poisson = poisson_candidates[0][2]

    rho_candidates = []
    for rho in [-0.15, -0.10, -0.05, 0.0, 0.05]:
        metrics, records = base.evaluate_model(matches, groups, best_poisson, rho)
        rho_candidates.append((metrics["logLoss"], metrics["brier"], rho, metrics, records))
    rho_candidates.sort(key=lambda x: (x[0], x[1]))
    _, _, best_rho, poisson_metrics, poisson_records = rho_candidates[0]

    elo_candidates = []
    for k, home_adv, draw_base, carry in itertools.product(
        [12.0, 20.0, 28.0], [45.0, 65.0, 85.0], [0.24, 0.27], [0.75, 0.90]
    ):
        ep = {"k": k, "home_adv": home_adv, "draw_base": draw_base, "carry": carry}
        _, records = elo_run(matches, ep, True)
        metrics = base.score_records(records)
        elo_candidates.append((metrics["logLoss"], metrics["brier"], ep, metrics, records))
    elo_candidates.sort(key=lambda x: (x[0], x[1]))
    _, _, best_elo, elo_metrics, elo_records = elo_candidates[0]

    ensemble_candidates = []
    for weight in [0.35, 0.50, 0.65, 0.75, 0.85, 0.92]:
        records = combine_records(poisson_records, elo_records, weight)
        metrics = base.score_records(records)
        ensemble_candidates.append((metrics["logLoss"], metrics["brier"], weight, metrics, records))
    ensemble_candidates.sort(key=lambda x: (x[0], x[1]))
    _, _, blend, validation, validation_records = ensemble_candidates[0]
    calibration = base.calibrate_confidence(validation_records)

    strengths = base.build_strengths(matches, date.today() + timedelta(days=1), best_poisson)
    ratings, _ = elo_run(matches, best_elo, False)
    predictions = {}
    for f in snapshot.get("fixtures", []):
        pp = base.predict(f["home"], f["away"], strengths, best_poisson, best_rho)
        ep = elo_probs(ratings.get(f["home"], 1500.0), ratings.get(f["away"], 1500.0), best_elo)
        pp["hp"] = blend * pp["hp"] + (1.0 - blend) * ep[0]
        pp["dp"] = blend * pp["dp"] + (1.0 - blend) * ep[1]
        pp["ap"] = blend * pp["ap"] + (1.0 - blend) * ep[2]
        conf, conf_rate = base.assign_confidence(pp, calibration)
        predictions[base.fixture_key(f)] = {
            "lh": round(pp["lh"], 4), "la": round(pp["la"], 4),
            "hp": round(pp["hp"], 5), "dp": round(pp["dp"], 5), "ap": round(pp["ap"], 5),
            "o": round(pp["o"], 5), "b": round(pp["b"], 5), "s": pp["s"],
            "conf": conf, "confRate": round(conf_rate, 4), "support": round(pp["support"], 2),
        }

    improvement = (baseline["logLoss"] - validation["logLoss"]) / baseline["logLoss"]
    payload = {
        "version": "2.1 historical Poisson + Elo ensemble",
        "updatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "method": "Walk-forward ensemble: recency-weighted home/away Poisson plus Elo team strength; Dixon-Coles correction and calibrated confidence",
        "params": {
            "halfLifeDays": int(best_poisson["half_life"]),
            "priorMatches": int(best_poisson["prior"]),
            "formWeight": best_poisson["form_weight"],
            "rho": best_rho,
            "recentMatches": base.RECENT_N,
            "poissonBlend": blend,
            "eloK": best_elo["k"],
            "eloHomeAdvantage": best_elo["home_adv"],
            "eloDrawBase": best_elo["draw_base"],
            "eloSeasonCarry": best_elo["carry"],
        },
        "validation": {
            "holdout": f"{base.HOLDOUT_START}/{str(base.HOLDOUT_START + 1)[-2:]}–{base.HOLDOUT_END}/{str(base.HOLDOUT_END + 1)[-2:]}",
            "matches": validation["matches"],
            "accuracy": round(validation["accuracy"], 5),
            "logLoss": round(validation["logLoss"], 5),
            "brier": round(validation["brier"], 5),
            "baselineAccuracy": round(baseline["accuracy"], 5),
            "baselineLogLoss": round(baseline["logLoss"], 5),
            "baselineBrier": round(baseline["brier"], 5),
            "poissonAccuracy": round(poisson_metrics["accuracy"], 5),
            "poissonLogLoss": round(poisson_metrics["logLoss"], 5),
            "eloAccuracy": round(elo_metrics["accuracy"], 5),
            "eloLogLoss": round(elo_metrics["logLoss"], 5),
            "logLossImprovement": round(improvement, 5),
            "confidence": calibration,
        },
        "predictions": predictions,
    }
    base.OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    print(f"Baseline: accuracy={baseline['accuracy']:.3f} logLoss={baseline['logLoss']:.4f} brier={baseline['brier']:.4f}")
    print(f"Poisson:  accuracy={poisson_metrics['accuracy']:.3f} logLoss={poisson_metrics['logLoss']:.4f} brier={poisson_metrics['brier']:.4f}")
    print(f"Elo:      accuracy={elo_metrics['accuracy']:.3f} logLoss={elo_metrics['logLoss']:.4f} brier={elo_metrics['brier']:.4f}")
    print(f"Ensemble: accuracy={validation['accuracy']:.3f} logLoss={validation['logLoss']:.4f} brier={validation['brier']:.4f} ({improvement * 100:.1f}% log-loss improvement)")
    print(f"Poisson params: {best_poisson}, rho={best_rho}; Elo params: {best_elo}; blend={blend}")
    print(f"Confidence: High {calibration['high']['accuracy']:.1%} ({calibration['high']['matches']}), Medium {calibration['medium']['accuracy']:.1%} ({calibration['medium']['matches']})")
    print(f"Built {base.OUT.name}: {len(predictions)} upcoming fixture predictions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
