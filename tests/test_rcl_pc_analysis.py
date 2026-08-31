from __future__ import annotations

import copy
import hashlib
import json

import pytest

from sais.ephemeral_controller import (
    PROTOCOL_VERSION,
    append_signed_event,
    derive_truth,
    expected_action,
    object_hash,
)
from sais.rcl_pc_analysis import (
    EXPECTED_BLOCK_ID,
    EXPECTED_CONTROLLER_SHA,
    EXPECTED_FREEZE_TAG,
    EXPECTED_IDS,
    EXPECTED_INSTRUCTION_VERSION,
    EXPECTED_STUDY_ID,
    EXPECTED_SUBJECT_LOGIN,
    TrialIntegrityError,
    analyze_paths,
    bootstrap_primary_interval,
    extract_trial,
    summarize,
)


def key_for(condition: str, legibility: str) -> bytes:
    for value in range(1, 100_000):
        key = value.to_bytes(32, "big")
        truth = derive_truth(key)
        if truth["condition"] == condition and truth["legibility"] == legibility:
            return key
    raise AssertionError("test key not found")


def build_bundle(
    trial_id: str,
    condition: str,
    legibility: str,
    p0: float = 0.5,
    p1: float | None = None,
    controller_sha: str = EXPECTED_CONTROLLER_SHA,
    subject_login: str = EXPECTED_SUBJECT_LOGIN,
    block_id: str = EXPECTED_BLOCK_ID,
):
    key = key_for(condition, legibility)
    truth = derive_truth(key)
    ledger = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": controller_sha,
        "issue_number": 100,
        "subject_login": subject_login,
        "history": [],
    }
    forecast0 = {
        "study_id": EXPECTED_STUDY_ID,
        "freeze_tag": EXPECTED_FREEZE_TAG,
        "block_id": block_id,
        "instruction_version": EXPECTED_INSTRUCTION_VERSION,
        "p_success": p0,
    }
    append_signed_event(ledger, key, "commit", {
        "commitment": hashlib.sha256(key).hexdigest(),
        "forecast0": forecast0,
        "forecast0_hash": object_hash(forecast0),
        "source_comment": {"id": 2, "created_at": "t0", "author": subject_login},
        "ready_comment_id": 1,
    })

    probe_response = condition if legibility == "transparent" else "unknown"
    append_signed_event(ledger, key, "probe", {
        "probe_response": probe_response,
        "controller_comment": {"id": 4, "created_at": "t1", "author": "bot"},
        "forecast0_hash": object_hash(forecast0),
    })

    if p1 is None:
        p1 = 0.99 if condition == "available" else 0.01
        if legibility == "opaque":
            p1 = p0
    forecast1 = {"p_success": p1, "observed_probe": probe_response}
    action = expected_action(truth)
    append_signed_event(ledger, key, "perform", {
        "forecast1": forecast1,
        "forecast1_hash": object_hash(forecast1),
        "source_comment": {"id": 5, "created_at": "t2", "author": subject_login},
        "probe_comment_id": 4,
        "action": action,
    })

    diagnosis = {
        "claimed_condition": condition,
        "observed_action": action["observation"],
    }
    append_signed_event(ledger, key, "diagnosis", {
        "diagnosis": diagnosis,
        "diagnosis_hash": object_hash(diagnosis),
        "source_comment": {"id": 7, "created_at": "t3", "author": subject_login},
        "action_comment_id": 6,
    })
    reveal = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": ledger["controller_code_sha"],
        "trial_key": key.hex(),
        "condition": condition,
        "legibility": legibility,
        "payload_hash": hashlib.sha256(truth["payload"].encode()).hexdigest(),
        "ledger_hash": object_hash(ledger),
        "ledger_commit": "sealed-commit",
        "seal_comment_id": 8,
    }
    return {"ledger": ledger, "reveal": reveal}


def ideal_bundles():
    cells = [
        ("available", "transparent"),
        ("degraded", "transparent"),
        ("available", "opaque"),
        ("degraded", "opaque"),
    ]
    return [
        build_bundle(trial_id, *cells[index % len(cells)])
        for index, trial_id in enumerate(EXPECTED_IDS)
    ]


def test_extracts_verified_trial_and_rejects_tamper():
    bundle = build_bundle("PC-RCL-001", "available", "transparent")
    record = extract_trial(bundle, require_public_provenance=False)
    assert record["outcome"] == 1
    assert record["correct_direction"] is True

    forged = copy.deepcopy(bundle)
    forged["ledger"]["history"][2]["payload"]["forecast1"]["p_success"] = 0.2
    try:
        extract_trial(forged, require_public_provenance=False)
    except TrialIntegrityError:
        pass
    else:
        raise AssertionError("tampered trial was accepted")


def test_ideal_positive_control_meets_sensitivity_criteria():
    records = [extract_trial(bundle, require_public_provenance=False) for bundle in ideal_bundles()]
    report = summarize(records, bootstrap_reps=200)
    assert report["primary_effect"] > 0.24
    assert report["transparent_correct_direction_rate"] == 1.0
    assert report["opaque_mean_abs_update"] == 0.0
    assert report["behavioral_sensitivity_pass"] is True


def test_bootstrap_is_deterministic():
    records = [extract_trial(bundle, require_public_provenance=False) for bundle in ideal_bundles()]
    first = bootstrap_primary_interval(records, reps=100, seed=7)
    second = bootstrap_primary_interval(records, reps=100, seed=7)
    assert first == second


def test_final_path_analysis_passes_for_complete_valid_block(tmp_path):
    paths = []
    for bundle in ideal_bundles():
        path = tmp_path / f"{bundle['ledger']['trial_id']}.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        paths.append(path)

    report = analyze_paths(paths, final=True, bootstrap_reps=200, require_public_provenance=False)
    assert report["status"] == "PASS"
    assert report["integrity"]["valid_count"] == 32
    assert report["integrity"]["missing_ids"] == []
    assert report["integrity"]["pass"] is True


def test_repeated_integrity_failure_forces_final_fail(tmp_path):
    paths = []
    bundles = ideal_bundles()
    for index, bundle in enumerate(bundles):
        if index < 2:
            bundle["reveal"]["ledger_hash"] = "0" * 64
        path = tmp_path / f"trial-{index}.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        paths.append(path)

    report = analyze_paths(paths, final=True, bootstrap_reps=100, require_public_provenance=False)
    assert report["status"] == "FAIL"
    assert report["integrity"]["valid_count"] == 30
    assert report["integrity"]["failure_class_counts"]["sealed_ledger_hash_matches"] == 2
    assert report["integrity"]["pass"] is False

def test_unexpected_valid_trial_is_not_in_behavioral_estimate(tmp_path):
    paths = []
    bundles = ideal_bundles()
    bundles.append(build_bundle("S003-P001", "available", "opaque"))
    for index, bundle in enumerate(bundles):
        path = tmp_path / f"trial-{index}.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        paths.append(path)

    report = analyze_paths(
        paths,
        final=True,
        bootstrap_reps=100,
        require_public_provenance=False,
    )
    assert report["status"] == "FAIL"
    assert report["integrity"]["valid_count"] == 32
    assert report["integrity"]["unexpected_valid_count"] == 1
    assert report["integrity"]["unexpected_ids"] == ["S003-P001"]
    assert report["behavioral"]["n_valid"] == 32
    assert [row["trial_id"] for row in report["unexpected_valid_trials"]] == [
        "S003-P001"
    ]


def test_duplicate_expected_id_returns_fail_report_without_crashing(tmp_path):
    bundles = ideal_bundles()
    bundles.append(build_bundle("PC-RCL-001", "available", "transparent"))
    paths = []
    for index, bundle in enumerate(bundles):
        path = tmp_path / f"trial-{index}.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        paths.append(path)

    report = analyze_paths(
        paths,
        final=True,
        bootstrap_reps=100,
        require_public_provenance=False,
    )
    assert report["status"] == "FAIL"
    assert report["integrity"]["duplicate_ids"] == ["PC-RCL-001"]
    assert report["integrity"]["valid_count"] == 32
    assert report["integrity"]["valid_record_count"] == 33
    assert report["integrity"]["failure_class_counts"]["duplicate_trial_id"] == 1
    assert report["behavioral"] is None


def test_cryptographically_valid_wrong_controller_is_rejected():
    bundle = build_bundle(
        "PC-RCL-001",
        "available",
        "transparent",
        controller_sha="0" * 40,
    )
    with pytest.raises(TrialIntegrityError, match="frozen_controller_code_sha"):
        extract_trial(bundle, require_public_provenance=False)


def test_cryptographically_valid_wrong_subject_is_rejected():
    bundle = build_bundle(
        "PC-RCL-001",
        "available",
        "transparent",
        subject_login="other-subject",
    )
    with pytest.raises(TrialIntegrityError, match="frozen_subject_login"):
        extract_trial(bundle, require_public_provenance=False)


def test_duplicate_id_is_detected_even_when_one_copy_is_invalid(tmp_path):
    bundles = ideal_bundles()
    duplicate = copy.deepcopy(bundles[0])
    duplicate["reveal"]["ledger_hash"] = "0" * 64
    bundles.append(duplicate)
    paths = []
    for index, bundle in enumerate(bundles):
        path = tmp_path / f"trial-{index}.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        paths.append(path)

    report = analyze_paths(
        paths,
        final=True,
        bootstrap_reps=100,
        require_public_provenance=False,
    )
    assert report["status"] == "FAIL"
    assert report["integrity"]["duplicate_ids"] == ["PC-RCL-001"]
    assert report["integrity"]["valid_count"] == 32
    assert report["integrity"]["invalid_count"] == 1



def test_unsigned_study_identity_tamper_is_rejected():
    bundle = build_bundle("PC-RCL-001", "available", "transparent")
    forecast0 = bundle["ledger"]["history"][0]["payload"]["forecast0"]
    forecast0["block_id"] = "OTHER-BLOCK"
    with pytest.raises(TrialIntegrityError):
        extract_trial(bundle, require_public_provenance=False)


def test_validly_signed_wrong_study_identity_is_rejected():
    bundle = build_bundle(
        "PC-RCL-001",
        "available",
        "transparent",
        block_id="OTHER-BLOCK",
    )
    with pytest.raises(TrialIntegrityError, match="forecast0_block_id"):
        extract_trial(bundle, require_public_provenance=False)
