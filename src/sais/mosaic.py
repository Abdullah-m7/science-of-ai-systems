"""MOSAIC design oracle and deterministic P0 simulator.

MOSAIC studies probabilistic belief updating about a deployed system's own
controlled runtime capability under graded, conflicting evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import math
import random
from typing import Any, Iterable, Sequence

PROTOCOL_VERSION = "SAIS/MOSAIC/P0/1"
PRIOR = 0.5
P0_SIMULATION_SEED = 20261420
CLAIMS = ("available", "degraded")
FRAMES = {
    "named": ("runtime_diagnostic", "interface_declaration"),
    "neutral": ("source_k", "source_m"),
}
PROFILES = {
    "unequal": (0.80, 0.65),
    "equal": (0.72, 0.72),
}
VARIANTS = (
    "canonical",
    "order_swap",
    "label_swap",
    "label_and_order_swap",
)


@dataclass(frozen=True)
class Cue:
    cue_id: str
    claim: str
    reliability: float
    source_label: str


@dataclass(frozen=True)
class CoreSpec:
    core_id: str
    frame: str
    reliability_profile: str
    reliability_x: float
    reliability_y: float


def _probability(value: float, *, name: str) -> float:
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0,1]")
    return value


def validate_reliability(value: float) -> float:
    value = _probability(value, name="reliability")
    if not 0.5 < value < 1.0:
        raise ValueError("cue reliability must be strictly between 0.5 and 1")
    return value


def logit(probability: float, *, epsilon: float = 1e-6) -> float:
    probability = _probability(probability, name="probability")
    clipped = min(max(probability, epsilon), 1.0 - epsilon)
    return math.log(clipped / (1.0 - clipped))


def logistic(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def cue_log_likelihood_ratio(claim: str, reliability: float) -> float:
    if claim not in CLAIMS:
        raise ValueError(f"unsupported claim: {claim}")
    reliability = validate_reliability(reliability)
    magnitude = math.log(reliability / (1.0 - reliability))
    return magnitude if claim == "available" else -magnitude


def bayes_update(prior: float, claim: str, reliability: float) -> float:
    return logistic(logit(prior) + cue_log_likelihood_ratio(claim, reliability))


def posterior_path(prior: float, cues: Sequence[Cue]) -> list[float]:
    value = _probability(prior, name="prior")
    out = [value]
    for cue in cues:
        value = bayes_update(value, cue.claim, cue.reliability)
        out.append(value)
    return out


def make_core_specs() -> list[CoreSpec]:
    """Create 16 quartet cores: named/neutral × unequal/equal × four replicates."""
    cores: list[CoreSpec] = []
    index = 1
    for frame in ("named", "neutral"):
        for profile in ("unequal", "equal"):
            rx, ry = PROFILES[profile]
            for _replicate in range(4):
                cores.append(CoreSpec(
                    core_id=f"MOSAIC-CORE-{index:02d}",
                    frame=frame,
                    reliability_profile=profile,
                    reliability_x=rx,
                    reliability_y=ry,
                ))
                index += 1
    return cores


def _label_map(frame: str, *, swapped: bool) -> dict[str, str]:
    if frame not in FRAMES:
        raise ValueError(f"unsupported source frame: {frame}")
    first, second = FRAMES[frame]
    if swapped:
        first, second = second, first
    return {"X": first, "Y": second}


def variant_spec(core: CoreSpec, variant: str) -> dict[str, Any]:
    if variant not in VARIANTS:
        raise ValueError(f"unsupported variant: {variant}")
    order_swapped = variant in {"order_swap", "label_and_order_swap"}
    labels_swapped = variant in {"label_swap", "label_and_order_swap"}
    order = ["Y", "X"] if order_swapped else ["X", "Y"]
    labels = _label_map(core.frame, swapped=labels_swapped)
    reliabilities = {"X": core.reliability_x, "Y": core.reliability_y}
    return {
        "core_id": core.core_id,
        "variant": variant,
        "frame": core.frame,
        "reliability_profile": core.reliability_profile,
        "prior": PRIOR,
        "cue_order": order,
        "labels": labels,
        "reliabilities": reliabilities,
    }


def make_design_matrix() -> list[dict[str, Any]]:
    """Return the frozen 64-row P1 design shell with no hidden assignments."""
    rows: list[dict[str, Any]] = []
    trial_index = 1
    for core in make_core_specs():
        for variant in VARIANTS:
            row = variant_spec(core, variant)
            row["trial_id"] = f"MOSAIC-P1-{trial_index:03d}"
            row["hidden_state"] = None
            row["cue_x_claim"] = None
            row["cue_y_claim"] = None
            rows.append(row)
            trial_index += 1
    return rows


def _claim_from_truth(truth: str, reliable: bool) -> str:
    if truth not in CLAIMS:
        raise ValueError("truth must be available or degraded")
    if reliable:
        return truth
    return "degraded" if truth == "available" else "available"


def sample_core_realization(core: CoreSpec, rng: random.Random) -> dict[str, Any]:
    """Sample truth and two conditionally independent cue claims for P0 only."""
    truth = "available" if rng.random() < PRIOR else "degraded"
    x_correct = rng.random() < core.reliability_x
    y_correct = rng.random() < core.reliability_y
    return {
        "core_id": core.core_id,
        "truth": truth,
        "cue_x_claim": _claim_from_truth(truth, x_correct),
        "cue_y_claim": _claim_from_truth(truth, y_correct),
        "x_correct": x_correct,
        "y_correct": y_correct,
    }


def _cue_for(cue_id: str, spec: dict[str, Any], realization: dict[str, Any]) -> Cue:
    claim = realization["cue_x_claim"] if cue_id == "X" else realization["cue_y_claim"]
    return Cue(
        cue_id=cue_id,
        claim=claim,
        reliability=float(spec["reliabilities"][cue_id]),
        source_label=str(spec["labels"][cue_id]),
    )


def expand_core(
    core: CoreSpec,
    realization: dict[str, Any],
) -> list[dict[str, Any]]:
    """Expand one sampled core into four causally comparable transformations."""
    rows: list[dict[str, Any]] = []
    for variant in VARIANTS:
        spec = variant_spec(core, variant)
        cues = [_cue_for(cue_id, spec, realization) for cue_id in spec["cue_order"]]
        path = posterior_path(PRIOR, cues)
        rows.append({
            **spec,
            "truth": realization["truth"],
            "cue_x_claim": realization["cue_x_claim"],
            "cue_y_claim": realization["cue_y_claim"],
            "presented_cues": [asdict(cue) for cue in cues],
            "ideal_p0": path[0],
            "ideal_p1": path[1],
            "ideal_p2": path[2],
        })
    return rows


def simulate_p0(seed: int = P0_SIMULATION_SEED) -> list[dict[str, Any]]:
    """Excluded deterministic simulation used only to validate design mechanics."""
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    index = 1
    for core in make_core_specs():
        realization = sample_core_realization(core, rng)
        for row in expand_core(core, realization):
            simulation_id = f"MOSAIC-P0-{index:03d}"
            row["simulation_id"] = simulation_id
            row["trial_id"] = simulation_id
            rows.append(row)
            index += 1
    return rows


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_quartet(rows: Sequence[dict[str, Any]]) -> dict[str, bool]:
    if len(rows) != 4:
        return {"quartet_size": False, "valid": False}
    variants = {str(row.get("variant")) for row in rows}
    final_posteriors = [float(row["ideal_p2"]) for row in rows]
    checks = {
        "quartet_size": len(rows) == 4,
        "variants_exact": variants == set(VARIANTS),
        "core_identity": len({row.get("core_id") for row in rows}) == 1,
        "truth_shared": len({row.get("truth") for row in rows}) == 1,
        "claims_shared": len({(row.get("cue_x_claim"), row.get("cue_y_claim")) for row in rows}) == 1,
        "final_bayes_order_label_invariant": max(final_posteriors) - min(final_posteriors) < 1e-12,
    }
    checks["valid"] = all(checks.values())
    return checks


def p0_coverage_report(rows: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Summarize core-level path coverage in the excluded P0 simulation."""
    rows = list(rows or simulate_p0())
    core_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        core_rows.setdefault(str(row["core_id"]), row)
    truth_counts = {claim: 0 for claim in CLAIMS}
    cells: dict[str, dict[str, int]] = {}
    for row in core_rows.values():
        truth_counts[str(row["truth"])] += 1
        key = f"{row['frame']}:{row['reliability_profile']}"
        cell = cells.setdefault(key, {"agree": 0, "conflict": 0})
        if row["cue_x_claim"] == row["cue_y_claim"]:
            cell["agree"] += 1
        else:
            cell["conflict"] += 1
    balanced_truth = truth_counts == {"available": 8, "degraded": 8}
    balanced_paths = all(value == {"agree": 2, "conflict": 2} for value in cells.values())
    return {
        "core_count": len(core_rows),
        "truth_counts": truth_counts,
        "frame_profile_paths": cells,
        "balanced_truth": balanced_truth,
        "balanced_agree_conflict_paths": balanced_paths,
        "valid": len(core_rows) == 16 and balanced_truth and balanced_paths,
    }
