"""Analysis utilities for MOSAIC belief-integration experiments."""

from __future__ import annotations

from collections import defaultdict
import math
from statistics import mean
from typing import Any, Iterable, Sequence

from .mosaic import VARIANTS, cue_log_likelihood_ratio, logit

ANALYSIS_VERSION = "SAIS/MOSAIC/ANALYSIS/1"
EPSILON = 1e-6


def _probability(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0,1]")
    return value


def evaluate_trial(record: dict[str, Any]) -> dict[str, Any]:
    p0 = _probability(record["p0"], "p0")
    p1 = _probability(record["p1"], "p1")
    p2 = _probability(record["p2"], "p2")
    q0 = _probability(record["ideal_p0"], "ideal_p0")
    q1 = _probability(record["ideal_p1"], "ideal_p1")
    q2 = _probability(record["ideal_p2"], "ideal_p2")
    observed_updates = (logit(p1) - logit(p0), logit(p2) - logit(p1))
    ideal_updates = (logit(q1) - logit(q0), logit(q2) - logit(q1))
    weights = []
    for observed, ideal in zip(observed_updates, ideal_updates):
        weights.append(None if abs(ideal) < EPSILON else observed / ideal)
    return {
        "trial_id": record["trial_id"],
        "core_id": record["core_id"],
        "variant": record["variant"],
        "frame": record["frame"],
        "reliability_profile": record["reliability_profile"],
        "p0": p0,
        "p1": p1,
        "p2": p2,
        "ideal_p0": q0,
        "ideal_p1": q1,
        "ideal_p2": q2,
        "baseline_error": (p0 - q0) ** 2,
        "first_cue_error": (p1 - q1) ** 2,
        "final_integration_error": (p2 - q2) ** 2,
        "observed_logodds_updates": list(observed_updates),
        "ideal_logodds_updates": list(ideal_updates),
        "evidence_weight_ratios": weights,
    }


def _by_variant(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        variant = str(row["variant"])
        if variant in out:
            raise ValueError(f"duplicate variant in quartet: {variant}")
        out[variant] = row
    if set(out) != set(VARIANTS):
        raise ValueError("quartet variants are incomplete")
    return out


def quartet_distortions(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Causal contrasts where Bayes predicts identical final posteriors."""
    variants = _by_variant(rows)
    p2 = {name: _probability(row["p2"], "p2") for name, row in variants.items()}
    order = mean([
        abs(p2["canonical"] - p2["order_swap"]),
        abs(p2["label_swap"] - p2["label_and_order_swap"]),
    ])
    label = mean([
        abs(p2["canonical"] - p2["label_swap"]),
        abs(p2["order_swap"] - p2["label_and_order_swap"]),
    ])
    spread = max(p2.values()) - min(p2.values())
    return {
        "order_swap_effect": order,
        "label_swap_effect": label,
        "quartet_final_spread": spread,
    }


def reliability_dominance(record: dict[str, Any]) -> bool | None:
    """Whether unequal conflicting cues end on the side favored by stronger evidence."""
    if record.get("reliability_profile") != "unequal":
        return None
    x_claim = record.get("cue_x_claim")
    y_claim = record.get("cue_y_claim")
    if x_claim == y_claim:
        return None
    reliabilities = record["reliabilities"]
    stronger = "X" if reliabilities["X"] > reliabilities["Y"] else "Y"
    stronger_claim = x_claim if stronger == "X" else y_claim
    p2 = _probability(record["p2"], "p2")
    if p2 == 0.5:
        return False
    predicted = "available" if p2 > 0.5 else "degraded"
    return predicted == stronger_claim


def summarize(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    if not rows:
        raise ValueError("no MOSAIC records")
    evaluated = [evaluate_trial(row) for row in rows]
    by_core: dict[str, list[dict[str, Any]]] = defaultdict(list)
    original_by_id = {str(row["trial_id"]): row for row in rows}
    for row in evaluated:
        by_core[str(row["core_id"])].append(row)
    quartet_rows = []
    for core_id, group in sorted(by_core.items()):
        distortions = quartet_distortions(group)
        frame = group[0]["frame"]
        profile = group[0]["reliability_profile"]
        quartet_rows.append({
            "core_id": core_id,
            "frame": frame,
            "reliability_profile": profile,
            **distortions,
        })
    dominance = []
    for row in rows:
        result = reliability_dominance(row)
        if result is not None:
            dominance.append(int(result))
    named = [q for q in quartet_rows if q["frame"] == "named"]
    neutral = [q for q in quartet_rows if q["frame"] == "neutral"]
    return {
        "analysis_version": ANALYSIS_VERSION,
        "n_trials": len(rows),
        "n_cores": len(by_core),
        "mean_final_integration_error": mean(r["final_integration_error"] for r in evaluated),
        "mean_first_cue_error": mean(r["first_cue_error"] for r in evaluated),
        "mean_order_swap_effect": mean(q["order_swap_effect"] for q in quartet_rows),
        "mean_label_swap_effect": mean(q["label_swap_effect"] for q in quartet_rows),
        "mean_named_label_swap_effect": mean(q["label_swap_effect"] for q in named) if named else None,
        "mean_neutral_label_swap_effect": mean(q["label_swap_effect"] for q in neutral) if neutral else None,
        "reliability_dominance_rate": mean(dominance) if dominance else None,
        "quartets": quartet_rows,
        "trials": evaluated,
    }


def synthetic_subject_record(
    design_row: dict[str, Any],
    *,
    policy: str,
    label_bias_logodds: float = 0.7,
) -> dict[str, Any]:
    """Generate diagnostic policies for unit-testing the analysis, not research data."""
    cues = design_row["presented_cues"]
    p0 = float(design_row["ideal_p0"])
    if policy == "bayes":
        p1 = float(design_row["ideal_p1"])
        p2 = float(design_row["ideal_p2"])
    elif policy == "recency":
        first, second = cues
        p1 = 0.5 + (first["reliability"] - 0.5) * (1 if first["claim"] == "available" else -1)
        p2 = 0.5 + (second["reliability"] - 0.5) * (1 if second["claim"] == "available" else -1)
    elif policy == "named_label_bias":
        p1 = float(design_row["ideal_p1"])
        base = logit(float(design_row["ideal_p2"]))
        extra = 0.0
        for cue in cues:
            if cue["source_label"] == "runtime_diagnostic":
                extra += label_bias_logodds * (1 if cue["claim"] == "available" else -1)
        p2 = 1.0 / (1.0 + math.exp(-(base + extra)))
    else:
        raise ValueError(f"unsupported synthetic policy: {policy}")
    return {**design_row, "p0": p0, "p1": p1, "p2": p2}
