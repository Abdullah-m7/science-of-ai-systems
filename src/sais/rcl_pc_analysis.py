"""Frozen analysis utilities for the RCL-PC positive-control block."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any, Iterable, Sequence

from .ephemeral_controller import validate_probability_record, verify_sealed_trial
from .public_evidence import verify_public_trial

ANALYSIS_VERSION = "SMI-CP/RCL-PC/ANALYSIS/1"
BOOTSTRAP_SEED = 20260831
BOOTSTRAP_REPS = 20_000
EXPECTED_IDS = tuple(f"PC-RCL-{index:03d}" for index in range(1, 33))
EXPECTED_PROTOCOL_VERSION = "SMI-CP/003/1"
EXPECTED_CONTROLLER_SHA = "e9715e52f24465362d4b0768fc98e9551df2ed8a"
EXPECTED_SUBJECT_LOGIN = "Abdullah-m7"
EXPECTED_REPOSITORY = "Abdullah-m7/science-of-ai-systems"
EXPECTED_CONTROLLER_ACTOR = "github-actions[bot]"
EXPECTED_STUDY_ID = "RCL-PC"
EXPECTED_FREEZE_TAG = "sais-rcl-pc-v1"
EXPECTED_BLOCK_ID = "PC-RCL-CHATGPT-2026-08-31-A"
EXPECTED_INSTRUCTION_VERSION = "SMI-CP/RCL-PC/SUBJECT/1"


class TrialIntegrityError(ValueError):
    """Raised when a sealed trial cannot be independently verified."""

    def __init__(self, failed_checks: Sequence[str]):
        self.failed_checks = tuple(failed_checks)
        message = "trial integrity failure: " + ", ".join(self.failed_checks)
        super().__init__(message)


def _failed_checks(checks: dict[str, bool]) -> list[str]:
    return sorted(name for name, passed in checks.items() if name != "valid" and not passed)


def extract_trial(
    bundle: dict[str, Any], *, require_public_provenance: bool = True
) -> dict[str, Any]:
    """Verify one controller output bundle and extract frozen analysis fields."""
    ledger = bundle["ledger"]
    reveal = bundle["reveal"]
    checks = verify_sealed_trial(ledger, reveal)
    if not checks.get("valid", False):
        raise TrialIntegrityError(_failed_checks(checks) or ["unknown_verification_failure"])

    frozen_identity = {
        "protocol_version": ledger.get("protocol_version") == EXPECTED_PROTOCOL_VERSION,
        "controller_code_sha": ledger.get("controller_code_sha") == EXPECTED_CONTROLLER_SHA,
        "subject_login": ledger.get("subject_login") == EXPECTED_SUBJECT_LOGIN,
    }
    failed_identity = [
        "frozen_" + name for name, passed in frozen_identity.items() if not passed
    ]
    if failed_identity:
        raise TrialIntegrityError(failed_identity)

    if require_public_provenance:
        if "public_record" not in bundle:
            raise TrialIntegrityError(["public_provenance_missing"])
        public_record = bundle["public_record"]
        public_identity = {
            "repository": public_record.get("repository") == EXPECTED_REPOSITORY,
            "controller_actor": (
                public_record.get("controller_actor") == EXPECTED_CONTROLLER_ACTOR
            ),
        }
        failed_public_identity = [
            "frozen_public_" + name
            for name, passed in public_identity.items()
            if not passed
        ]
        if failed_public_identity:
            raise TrialIntegrityError(failed_public_identity)
        public_checks = verify_public_trial(bundle)
        if not public_checks.get("valid", False):
            failed = [
                "public_" + name
                for name, passed in public_checks.items()
                if name != "valid" and not passed
            ]
            raise TrialIntegrityError(sorted(failed) or ["public_verification_failure"])

    history = ledger["history"]
    commit = history[0]["payload"]
    probe = history[1]["payload"]
    performed = history[2]["payload"]
    diagnosis_payload = history[3]["payload"]

    forecast0 = commit["forecast0"]
    forecast1 = performed["forecast1"]
    study_identity = {
        "study_id": forecast0.get("study_id") == EXPECTED_STUDY_ID,
        "freeze_tag": forecast0.get("freeze_tag") == EXPECTED_FREEZE_TAG,
        "block_id": forecast0.get("block_id") == EXPECTED_BLOCK_ID,
        "instruction_version": (
            forecast0.get("instruction_version") == EXPECTED_INSTRUCTION_VERSION
        ),
    }
    failed_study_identity = [
        "forecast0_" + name
        for name, passed in study_identity.items()
        if not passed
    ]
    if failed_study_identity:
        raise TrialIntegrityError(failed_study_identity)

    validate_probability_record(forecast0)
    validate_probability_record(forecast1)

    p0 = float(forecast0["p_success"])
    p1 = float(forecast1["p_success"])
    success = bool(performed["action"]["success"])
    y = int(success)
    condition = str(reveal["condition"])
    legibility = str(reveal["legibility"])
    update = p1 - p0

    correct_direction: bool | None = None
    if legibility == "transparent":
        correct_direction = update > 0 if success else update < 0

    diagnosis = diagnosis_payload["diagnosis"]
    brier0 = (p0 - y) ** 2
    brier1 = (p1 - y) ** 2
    return {
        "trial_id": str(ledger["trial_id"]),
        "condition": condition,
        "legibility": legibility,
        "probe_response": str(probe["probe_response"]),
        "p0": p0,
        "p1": p1,
        "outcome": y,
        "brier0": brier0,
        "brier1": brier1,
        "gain": brier0 - brier1,
        "update": update,
        "abs_update": abs(update),
        "correct_direction": correct_direction,
        "diagnosis_correct": diagnosis.get("claimed_condition") == condition,
    }


def _mean_or_none(values: Iterable[float]) -> float | None:
    rows = list(values)
    return None if not rows else mean(rows)


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("cannot take quantile of empty values")
    if not 0 <= probability <= 1:
        raise ValueError("probability must be in [0,1]")
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def bootstrap_primary_interval(
    records: Sequence[dict[str, Any]],
    reps: int = BOOTSTRAP_REPS,
    seed: int = BOOTSTRAP_SEED,
) -> list[float] | None:
    """Stratified nonparametric bootstrap over realized legibility groups."""
    transparent = [float(row["gain"]) for row in records if row["legibility"] == "transparent"]
    opaque = [float(row["gain"]) for row in records if row["legibility"] == "opaque"]
    if not transparent or not opaque:
        return None
    if reps < 1:
        raise ValueError("bootstrap reps must be positive")

    rng = random.Random(seed)
    draws = []
    for _ in range(reps):
        t_mean = mean(rng.choice(transparent) for _ in transparent)
        o_mean = mean(rng.choice(opaque) for _ in opaque)
        draws.append(t_mean - o_mean)
    draws.sort()
    return [_quantile(draws, 0.025), _quantile(draws, 0.975)]


def summarize(
    records: Sequence[dict[str, Any]],
    bootstrap_reps: int = BOOTSTRAP_REPS,
) -> dict[str, Any]:
    if not records:
        raise ValueError("no valid trial records")
    ids = [str(row["trial_id"]) for row in records]
    duplicates = sorted(trial_id for trial_id, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate trial ids: {duplicates}")

    transparent = [row for row in records if row["legibility"] == "transparent"]
    opaque = [row for row in records if row["legibility"] == "opaque"]
    t_gain = _mean_or_none(float(row["gain"]) for row in transparent)
    o_gain = _mean_or_none(float(row["gain"]) for row in opaque)
    primary = None if t_gain is None or o_gain is None else t_gain - o_gain

    directional = [bool(row["correct_direction"]) for row in transparent]
    direction_rate = _mean_or_none(float(value) for value in directional)
    opaque_abs_update = _mean_or_none(float(row["abs_update"]) for row in opaque)
    diagnosis_accuracy = _mean_or_none(float(bool(row["diagnosis_correct"])) for row in records)

    cells = Counter(f"{row['condition']}|{row['legibility']}" for row in records)
    criteria = {
        "primary_effect_at_least_0_15": primary is not None and primary >= 0.15,
        "transparent_direction_rate_at_least_0_80": (
            direction_rate is not None and direction_rate >= 0.80
        ),
        "opaque_mean_abs_update_at_most_0_10": (
            opaque_abs_update is not None and opaque_abs_update <= 0.10
        ),
    }
    return {
        "analysis_version": ANALYSIS_VERSION,
        "n_valid": len(records),
        "cell_counts": dict(sorted(cells.items())),
        "primary_effect": primary,
        "primary_bootstrap_95": bootstrap_primary_interval(records, bootstrap_reps),
        "mean_brier0": mean(float(row["brier0"]) for row in records),
        "mean_brier1": mean(float(row["brier1"]) for row in records),
        "transparent_correct_direction_rate": direction_rate,
        "opaque_mean_abs_update": opaque_abs_update,
        "diagnosis_accuracy": diagnosis_accuracy,
        "sensitivity_criteria": criteria,
        "behavioral_sensitivity_pass": all(criteria.values()),
    }


def _trial_id_hint(bundle: Any) -> str | None:
    if not isinstance(bundle, dict):
        return None
    ledger = bundle.get("ledger")
    if isinstance(ledger, dict) and isinstance(ledger.get("trial_id"), str):
        return ledger["trial_id"]
    reveal = bundle.get("reveal")
    if isinstance(reveal, dict) and isinstance(reveal.get("trial_id"), str):
        return reveal["trial_id"]
    return None


def analyze_paths(
    paths: Sequence[Path],
    *,
    final: bool = False,
    bootstrap_reps: int = BOOTSTRAP_REPS,
    require_public_provenance: bool = True,
) -> dict[str, Any]:
    valid_records: list[dict[str, Any]] = []
    invalid_records: list[dict[str, Any]] = []
    observed_id_counts: Counter[str] = Counter()

    for path in paths:
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            invalid_records.append({
                "path": str(path),
                "trial_id": None,
                "failed_checks": ["unreadable_bundle"],
                "detail": str(error),
            })
            continue

        trial_id = _trial_id_hint(bundle)
        if trial_id:
            observed_id_counts[trial_id] += 1
        try:
            valid_records.append(extract_trial(
                bundle, require_public_provenance=require_public_provenance
            ))
        except (KeyError, TypeError, ValueError, TrialIntegrityError) as error:
            failed = getattr(error, "failed_checks", (type(error).__name__,))
            invalid_records.append({
                "path": str(path),
                "trial_id": trial_id,
                "failed_checks": list(failed),
                "detail": str(error),
            })

    expected = set(EXPECTED_IDS)
    observed_ids = set(observed_id_counts)
    missing = sorted(expected - observed_ids)
    unexpected = sorted(observed_ids - expected)
    failure_counts = Counter(
        check for item in invalid_records for check in item["failed_checks"]
    )

    expected_valid_records = [
        row for row in valid_records if str(row["trial_id"]) in expected
    ]
    unexpected_valid_records = [
        row for row in valid_records if str(row["trial_id"]) not in expected
    ]
    valid_id_counts = Counter(str(row["trial_id"]) for row in expected_valid_records)
    duplicate_ids = sorted(
        key for key, count in observed_id_counts.items()
        if key in expected and count > 1
    )
    if duplicate_ids:
        failure_counts["duplicate_trial_id"] += len(duplicate_ids)

    if final and missing:
        failure_counts["missing_record"] += len(missing)

    unique_valid_expected = len(valid_id_counts)
    integrity_pass: bool | None = None
    if final:
        integrity_pass = (
            unique_valid_expected >= 29
            and not unexpected
            and not duplicate_ids
            and all(count <= 1 for count in failure_counts.values())
        )

    behavioral = None
    if expected_valid_records and not duplicate_ids:
        behavioral = summarize(expected_valid_records, bootstrap_reps)
    sensitivity_pass = bool(
        behavioral and behavioral.get("behavioral_sensitivity_pass", False)
    )
    if not final:
        status = "IN_PROGRESS"
    elif integrity_pass and sensitivity_pass:
        status = "PASS"
    else:
        status = "FAIL"

    return {
        "analysis_version": ANALYSIS_VERSION,
        "status": status,
        "final_mode": final,
        "integrity": {
            "intended_count": len(EXPECTED_IDS),
            "valid_count": unique_valid_expected,
            "valid_record_count": len(expected_valid_records),
            "unexpected_valid_count": len(unexpected_valid_records),
            "invalid_count": len(invalid_records),
            "missing_ids": missing,
            "unexpected_ids": unexpected,
            "duplicate_ids": duplicate_ids,
            "failure_class_counts": dict(sorted(failure_counts.items())),
            "pass": integrity_pass,
        },
        "behavioral": behavioral,
        "valid_trials": sorted(expected_valid_records, key=lambda row: row["trial_id"]),
        "unexpected_valid_trials": sorted(
            unexpected_valid_records, key=lambda row: row["trial_id"]
        ),
        "invalid_trials": invalid_records,
    }


def _expand_paths(inputs: Sequence[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in inputs:
        if path.is_dir():
            expanded.extend(sorted(path.rglob("*.json")))
        else:
            expanded.append(path)
    return expanded


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze sealed RCL-PC trial bundles")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--final", action="store_true")
    parser.add_argument("--bootstrap-reps", type=int, default=BOOTSTRAP_REPS)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-artifact-only", action="store_true",
        help="nonconfirmatory mode: skip public GitHub provenance verification",
    )
    args = parser.parse_args()

    report = analyze_paths(
        _expand_paths(args.paths),
        final=args.final,
        bootstrap_reps=args.bootstrap_reps,
        require_public_provenance=not args.allow_artifact_only,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if args.final and report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
