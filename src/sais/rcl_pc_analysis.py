"""Final manifest-driven analysis for the config-bound RCL-PC block."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

from .config_binding import BINDING_PROTOCOL, binding_hash
from .freeze_manifest import verify_manifest
from .rcl_bound_controller import (
    validate_probability_record,
    verify_sealed_trial,
)
from .rcl_bound_evidence import (
    ACTION_PREFIX,
    DIAGNOSIS_PREFIX,
    FORECAST0_PREFIX,
    FORECAST1_PREFIX,
    READY_PREFIX,
    REVEAL_PREFIX,
    verify_public_trial,
)

ANALYSIS_VERSION = "SMI-CP/RCL-PC/ANALYSIS/2"
DEFAULT_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json"
)


class TrialIntegrityError(ValueError):
    """Raised when a trial cannot be admitted to the frozen block."""

    def __init__(self, failed_checks: Sequence[str]):
        self.failed_checks = tuple(sorted(set(failed_checks)))
        super().__init__("trial integrity failure: " + ", ".join(self.failed_checks))


@dataclass(frozen=True)
class StudySpec:
    manifest_version: str
    freeze_tag: str
    analysis_version: str
    expected_ids: tuple[str, ...]
    repository: str
    subject_login: str
    controller_actor: str
    controller_protocol_version: str
    controller_code_sha: str
    config_repository: str
    config_commit: str
    config_path: str
    config_sha256: str
    config_protocol_version: str
    block_id: str
    subject_instruction_path: str
    subject_instruction_sha256: str
    expected_binding_hash: str
    bootstrap_seed: int
    bootstrap_reps: int
    primary_effect_min: float
    transparent_direction_min: float
    opaque_abs_update_max: float

    @property
    def expected_binding(self) -> dict[str, str]:
        return {
            "binding_protocol": BINDING_PROTOCOL,
            "block_id": self.block_id,
            "repository": self.config_repository,
            "commit": self.config_commit,
            "path": self.config_path,
            "config_sha256": self.config_sha256,
            "config_protocol": self.config_protocol_version,
        }

    @classmethod
    def from_manifest(cls, value: Mapping[str, Any]) -> "StudySpec":
        study = value["study"]
        controller = value["controller"]
        configuration = value["configuration"]
        sample = value["sample"]
        analysis = value["analysis"]
        thresholds = analysis["thresholds"]
        spec = cls(
            manifest_version=str(value["manifest_version"]),
            freeze_tag=str(value["freeze_tag"]),
            analysis_version=str(analysis["version"]),
            expected_ids=tuple(str(item) for item in sample["trial_ids"]),
            repository=str(value["repository"]),
            subject_login=str(value["subject"]["login"]),
            controller_actor=str(controller["actor"]),
            controller_protocol_version=str(controller["protocol_version"]),
            controller_code_sha=str(controller["commit"]),
            config_repository=str(configuration["repository"]),
            config_commit=str(configuration["commit"]),
            config_path=str(configuration["path"]),
            config_sha256=str(configuration["sha256"]),
            config_protocol_version=str(configuration["protocol_version"]),
            block_id=str(configuration["block_id"]),
            subject_instruction_path=str(
                configuration["subject_instruction_path"]
            ),
            subject_instruction_sha256=str(
                configuration["subject_instruction_sha256"]
            ),
            expected_binding_hash=str(configuration["binding_sha256"]),
            bootstrap_seed=int(analysis["bootstrap_seed"]),
            bootstrap_reps=int(analysis["bootstrap_reps"]),
            primary_effect_min=float(thresholds["primary_effect_min"]),
            transparent_direction_min=float(
                thresholds["transparent_correct_direction_rate_min"]
            ),
            opaque_abs_update_max=float(
                thresholds["opaque_mean_abs_update_max"]
            ),
        )
        if spec.analysis_version != ANALYSIS_VERSION:
            raise ValueError("manifest analysis version does not match this analyzer")
        if binding_hash(spec.expected_binding) != spec.expected_binding_hash:
            raise ValueError("manifest configuration binding hash is inconsistent")
        return spec


def load_study_spec(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    root: Path | None = None,
    require_valid_manifest: bool = True,
) -> StudySpec:
    manifest_path = manifest_path.resolve()
    if require_valid_manifest:
        report = verify_manifest(manifest_path, root)
        if not report["checks"].get("valid", False):
            failed = sorted(
                name for name, passed in report["checks"].items() if not passed
            )
            raise ValueError("invalid freeze manifest: " + ", ".join(failed))
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    return StudySpec.from_manifest(value)


def _failed_checks(checks: Mapping[str, bool], prefix: str = "") -> list[str]:
    return sorted(
        prefix + name
        for name, passed in checks.items()
        if name != "valid" and not passed
    )


def _author(comment: Mapping[str, Any]) -> str | None:
    user = comment.get("user")
    if isinstance(user, Mapping):
        return user.get("login")
    return comment.get("author")


def _identity_checks(bundle: Mapping[str, Any], spec: StudySpec) -> dict[str, bool]:
    ledger = bundle.get("ledger") or {}
    reveal = bundle.get("reveal") or {}
    binding = ledger.get("configuration_binding") or {}
    config = bundle.get("configuration") or {}
    public = bundle.get("public_record") or {}
    config_source = public.get("configuration_source") or {}
    instruction_source = public.get("subject_instruction_source") or {}
    return {
        "ledger_protocol": (
            ledger.get("protocol_version") == spec.controller_protocol_version
        ),
        "controller_code_sha": (
            ledger.get("controller_code_sha") == spec.controller_code_sha
        ),
        "subject_login": ledger.get("subject_login") == spec.subject_login,
        "configuration_binding": binding == spec.expected_binding,
        "configuration_binding_hash": (
            ledger.get("configuration_binding_hash")
            == spec.expected_binding_hash
        ),
        "reveal_binding_hash": (
            reveal.get("configuration_binding_hash")
            == spec.expected_binding_hash
        ),
        "config_protocol": (
            config.get("protocol_version") == spec.config_protocol_version
        ),
        "config_block_id": config.get("block_id") == spec.block_id,
        "config_instruction_path": (
            config.get("subject_instruction_path")
            == spec.subject_instruction_path
        ),
        "config_instruction_sha256": (
            config.get("subject_instruction_sha256")
            == spec.subject_instruction_sha256
        ),
        "public_repository": (
            not public or public.get("repository") == spec.repository
        ),
        "public_controller_actor": (
            not public or public.get("controller_actor") == spec.controller_actor
        ),
        "public_config_commit": (
            not public or config_source.get("commit") == spec.config_commit
        ),
        "public_config_path": (
            not public or config_source.get("path") == spec.config_path
        ),
        "public_config_sha256": (
            not public or config_source.get("content_sha256") == spec.config_sha256
        ),
        "public_instruction_path": (
            not public
            or instruction_source.get("path") == spec.subject_instruction_path
        ),
        "public_instruction_sha256": (
            not public
            or instruction_source.get("content_sha256")
            == spec.subject_instruction_sha256
        ),
    }


def _controller_comment(
    comments: Sequence[Mapping[str, Any]], prefix: str, actor: str
) -> Mapping[str, Any]:
    matches = [
        item
        for item in comments
        if _author(item) == actor and str(item.get("body", "")).startswith(prefix)
    ]
    if len(matches) != 1:
        raise TrialIntegrityError([f"protocol_{prefix.strip()}_count"])
    return matches[0]


def _protocol_audit(bundle: Mapping[str, Any], spec: StudySpec) -> dict[str, Any]:
    public = bundle.get("public_record")
    if not isinstance(public, Mapping):
        return {
            "available": False,
            "faithful": None,
            "extra_subject_comment_ids": [],
        }
    comments = public.get("comments")
    if not isinstance(comments, list):
        raise TrialIntegrityError(["protocol_comments_missing"])
    ledger = bundle["ledger"]
    history = ledger["history"]
    expected_subject_ids = {
        int(history[0]["payload"]["source_comment"]["id"]),
        int(history[2]["payload"]["source_comment"]["id"]),
        int(history[3]["payload"]["source_comment"]["id"]),
    }
    ready = _controller_comment(comments, READY_PREFIX, spec.controller_actor)
    reveal = _controller_comment(comments, REVEAL_PREFIX, spec.controller_actor)
    positions = {int(item["id"]): index for index, item in enumerate(comments)}
    start = positions[int(ready["id"])]
    end = positions[int(reveal["id"])]
    extras = sorted(
        int(item["id"])
        for index, item in enumerate(comments)
        if start < index < end
        and _author(item) == spec.subject_login
        and int(item["id"]) not in expected_subject_ids
    )
    return {
        "available": True,
        "faithful": not extras,
        "extra_subject_comment_ids": extras,
    }


def extract_trial(
    bundle: dict[str, Any],
    spec: StudySpec,
    *,
    require_public_provenance: bool = True,
) -> dict[str, Any]:
    """Verify one bundle against the frozen study identity and extract metrics."""
    try:
        ledger = bundle["ledger"]
        reveal = bundle["reveal"]
    except (KeyError, TypeError) as error:
        raise TrialIntegrityError(["bundle_structure"]) from error

    crypto = verify_sealed_trial(ledger, reveal)
    if not crypto.get("valid", False):
        raise TrialIntegrityError(_failed_checks(crypto, "crypto_"))

    identity = _identity_checks(bundle, spec)
    if not all(identity.values()):
        raise TrialIntegrityError(_failed_checks(identity, "identity_"))

    if require_public_provenance:
        if "public_record" not in bundle:
            raise TrialIntegrityError(["public_provenance_missing"])
        public_checks = verify_public_trial(
            bundle,
            expected_repository=spec.repository,
            expected_controller_actor=spec.controller_actor,
            expected_subject_actor=spec.subject_login,
            expected_controller_code_sha=spec.controller_code_sha,
            expected_configuration_commit=spec.config_commit,
            expected_configuration_path=spec.config_path,
            expected_block_id=spec.block_id,
        )
        if not public_checks.get("valid", False):
            raise TrialIntegrityError(
                _failed_checks(public_checks, "public_")
            )

    history = ledger["history"]
    commit = history[0]["payload"]
    probe = history[1]["payload"]
    performed = history[2]["payload"]
    diagnosis_payload = history[3]["payload"]
    forecast0 = commit["forecast0"]
    forecast1 = performed["forecast1"]
    validate_probability_record(
        forecast0,
        spec.expected_binding_hash,
    )
    validate_probability_record(
        forecast1,
        spec.expected_binding_hash,
        observed_probe=str(probe["probe_response"]),
    )

    p0 = float(forecast0["p_success"])
    p1 = float(forecast1["p_success"])
    outcome = int(bool(performed["action"]["success"]))
    condition = str(reveal["condition"])
    legibility = str(reveal["legibility"])
    update = p1 - p0
    correct_direction: bool | None = None
    if legibility == "transparent":
        correct_direction = update > 0 if outcome else update < 0

    diagnosis = diagnosis_payload["diagnosis"]
    audit = _protocol_audit(bundle, spec)
    brier0 = (p0 - outcome) ** 2
    brier1 = (p1 - outcome) ** 2
    return {
        "trial_id": str(ledger["trial_id"]),
        "configuration_binding_hash": spec.expected_binding_hash,
        "condition": condition,
        "legibility": legibility,
        "probe_response": str(probe["probe_response"]),
        "p0": p0,
        "p1": p1,
        "outcome": outcome,
        "brier0": brier0,
        "brier1": brier1,
        "gain": brier0 - brier1,
        "update": update,
        "abs_update": abs(update),
        "correct_direction": correct_direction,
        "diagnosis_correct": diagnosis.get("claimed_condition") == condition,
        "protocol_faithful": audit["faithful"],
        "extra_subject_comment_ids": audit["extra_subject_comment_ids"],
    }


def _mean_or_none(values: Iterable[float]) -> float | None:
    rows = list(values)
    return None if not rows else mean(rows)


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot take quantile of empty values")
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def bootstrap_primary_interval(
    records: Sequence[dict[str, Any]],
    *,
    reps: int,
    seed: int,
) -> list[float] | None:
    transparent = [
        float(row["gain"])
        for row in records
        if row["legibility"] == "transparent"
    ]
    opaque = [
        float(row["gain"])
        for row in records
        if row["legibility"] == "opaque"
    ]
    if not transparent or not opaque:
        return None
    if reps < 1:
        raise ValueError("bootstrap reps must be positive")
    rng = random.Random(seed)
    draws = []
    for _ in range(reps):
        transparent_mean = mean(rng.choice(transparent) for _ in transparent)
        opaque_mean = mean(rng.choice(opaque) for _ in opaque)
        draws.append(transparent_mean - opaque_mean)
    draws.sort()
    return [_quantile(draws, 0.025), _quantile(draws, 0.975)]


def summarize(
    records: Sequence[dict[str, Any]],
    spec: StudySpec,
) -> dict[str, Any]:
    if not records:
        raise ValueError("no valid trial records")
    ids = [str(row["trial_id"]) for row in records]
    duplicates = sorted(
        trial_id for trial_id, count in Counter(ids).items() if count > 1
    )
    if duplicates:
        raise ValueError(f"duplicate trial ids: {duplicates}")

    transparent = [row for row in records if row["legibility"] == "transparent"]
    opaque = [row for row in records if row["legibility"] == "opaque"]
    transparent_gain = _mean_or_none(float(row["gain"]) for row in transparent)
    opaque_gain = _mean_or_none(float(row["gain"]) for row in opaque)
    primary = (
        None
        if transparent_gain is None or opaque_gain is None
        else transparent_gain - opaque_gain
    )
    directional = [
        bool(row["correct_direction"])
        for row in transparent
        if row["correct_direction"] is not None
    ]
    direction_rate = _mean_or_none(float(value) for value in directional)
    opaque_abs_update = _mean_or_none(
        float(row["abs_update"]) for row in opaque
    )
    diagnosis_accuracy = _mean_or_none(
        float(bool(row["diagnosis_correct"])) for row in records
    )
    protocol_values = [
        bool(row["protocol_faithful"])
        for row in records
        if row["protocol_faithful"] is not None
    ]
    protocol_rate = _mean_or_none(float(value) for value in protocol_values)
    cells = Counter(
        f"{row['condition']}|{row['legibility']}" for row in records
    )
    criteria = {
        "primary_effect_at_least_minimum": (
            primary is not None and primary >= spec.primary_effect_min
        ),
        "transparent_direction_rate_at_least_minimum": (
            direction_rate is not None
            and direction_rate >= spec.transparent_direction_min
        ),
        "opaque_mean_abs_update_at_most_maximum": (
            opaque_abs_update is not None
            and opaque_abs_update <= spec.opaque_abs_update_max
        ),
    }
    return {
        "analysis_version": spec.analysis_version,
        "n_valid": len(records),
        "cell_counts": dict(sorted(cells.items())),
        "primary_effect": primary,
        "primary_bootstrap_95": bootstrap_primary_interval(
            records,
            reps=spec.bootstrap_reps,
            seed=spec.bootstrap_seed,
        ),
        "mean_brier0": mean(float(row["brier0"]) for row in records),
        "mean_brier1": mean(float(row["brier1"]) for row in records),
        "transparent_correct_direction_rate": direction_rate,
        "opaque_mean_abs_update": opaque_abs_update,
        "diagnosis_accuracy": diagnosis_accuracy,
        "protocol_fidelity_rate_among_valid": protocol_rate,
        "sensitivity_criteria": criteria,
        "behavioral_sensitivity_pass": all(criteria.values()),
    }


def _trial_id_hint(bundle: Any) -> str | None:
    if not isinstance(bundle, Mapping):
        return None
    for key in ("ledger", "reveal"):
        value = bundle.get(key)
        if isinstance(value, Mapping) and isinstance(value.get("trial_id"), str):
            return str(value["trial_id"])
    return None


def _invalid_record(
    path: Path,
    trial_id: str | None,
    error: BaseException,
) -> dict[str, Any]:
    failed = getattr(error, "failed_checks", (type(error).__name__,))
    return {
        "path": str(path),
        "trial_id": trial_id,
        "failed_checks": list(failed),
        "detail": str(error),
    }


def analyze_paths(
    paths: Sequence[Path],
    spec: StudySpec,
    *,
    final: bool = False,
    require_public_provenance: bool = True,
) -> dict[str, Any]:
    if final and not require_public_provenance:
        raise ValueError("final analysis requires public provenance")

    valid_records: list[dict[str, Any]] = []
    invalid_records: list[dict[str, Any]] = []
    observed_id_counts: Counter[str] = Counter()

    for path in paths:
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            invalid_records.append(_invalid_record(path, None, error))
            continue
        trial_id = _trial_id_hint(bundle)
        if trial_id is not None:
            observed_id_counts[trial_id] += 1
        try:
            valid_records.append(
                extract_trial(
                    bundle,
                    spec,
                    require_public_provenance=require_public_provenance,
                )
            )
        except (KeyError, TypeError, ValueError, TrialIntegrityError) as error:
            invalid_records.append(_invalid_record(path, trial_id, error))

    expected = set(spec.expected_ids)
    observed = set(observed_id_counts)
    valid_expected = [
        row for row in valid_records if str(row["trial_id"]) in expected
    ]
    valid_unexpected = [
        row for row in valid_records if str(row["trial_id"]) not in expected
    ]
    valid_counts = Counter(str(row["trial_id"]) for row in valid_expected)
    duplicate_ids = sorted(
        trial_id
        for trial_id, count in observed_id_counts.items()
        if count > 1
    )
    unobserved_ids = sorted(expected - observed)
    not_valid_ids = sorted(expected - set(valid_counts))
    unexpected_ids = sorted(observed - expected)
    protocol_deviation_ids = sorted(
        str(row["trial_id"])
        for row in valid_expected
        if row["protocol_faithful"] is False
    )

    behavioral = None
    if valid_expected and not duplicate_ids:
        behavioral = summarize(valid_expected, spec)

    all_expected_public_valid = (
        len(valid_expected) == len(spec.expected_ids)
        and set(valid_counts) == expected
        and all(count == 1 for count in valid_counts.values())
    )
    integrity_criteria = {
        "all_expected_observed": not unobserved_ids,
        "all_expected_public_valid": all_expected_public_valid,
        "no_invalid_bundles": not invalid_records,
        "no_unexpected_ids": not unexpected_ids,
        "no_duplicate_ids": not duplicate_ids,
        "all_protocol_faithful": not protocol_deviation_ids,
    }
    sensitivity_pass = bool(
        behavioral and behavioral.get("behavioral_sensitivity_pass", False)
    )
    qualification = {
        **integrity_criteria,
        "behavioral_sensitivity_pass": sensitivity_pass,
    }

    if not final:
        status = "IN_PROGRESS"
    elif (
        invalid_records
        or unexpected_ids
        or duplicate_ids
        or protocol_deviation_ids
        or (not unobserved_ids and not all_expected_public_valid)
    ):
        status = "INVALID"
    elif unobserved_ids:
        status = "INCOMPLETE"
    elif sensitivity_pass:
        status = "PASS"
    else:
        status = "FAIL"

    failure_counts = Counter(
        check for item in invalid_records for check in item["failed_checks"]
    )
    return {
        "analysis_version": spec.analysis_version,
        "manifest_version": spec.manifest_version,
        "freeze_tag": spec.freeze_tag,
        "block_id": spec.block_id,
        "configuration_binding_hash": spec.expected_binding_hash,
        "status": status,
        "final_mode": final,
        "overall_qualification_pass": status == "PASS",
        "qualification_criteria": qualification,
        "integrity": {
            "intended_count": len(spec.expected_ids),
            "observed_unique_count": len(observed),
            "valid_expected_count": len(valid_expected),
            "valid_unexpected_count": len(valid_unexpected),
            "invalid_bundle_count": len(invalid_records),
            "unobserved_ids": unobserved_ids,
            "not_valid_ids": not_valid_ids,
            "unexpected_ids": unexpected_ids,
            "duplicate_ids": duplicate_ids,
            "protocol_deviation_ids": protocol_deviation_ids,
            "failure_class_counts": dict(sorted(failure_counts.items())),
            "pass": all(integrity_criteria.values()),
        },
        "behavioral": behavioral,
        "valid_trials": sorted(valid_expected, key=lambda row: row["trial_id"]),
        "unexpected_valid_trials": sorted(
            valid_unexpected,
            key=lambda row: row["trial_id"],
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
    parser = argparse.ArgumentParser(
        description="Analyze the frozen config-bound RCL-PC block"
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--final", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-artifact-only",
        action="store_true",
        help="nonconfirmatory diagnostics only; forbidden with --final",
    )
    args = parser.parse_args()

    if args.final and args.allow_artifact_only:
        parser.error("--allow-artifact-only cannot be used with --final")
    spec = load_study_spec(args.manifest)
    report = analyze_paths(
        _expand_paths(args.paths),
        spec,
        final=args.final,
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
