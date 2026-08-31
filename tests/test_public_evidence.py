from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import sais.public_evidence as pe
from sais.public_evidence import collect_public_trial, verify_public_trial
from sais.rcl_pc_analysis import TrialIntegrityError, extract_trial

FIXTURE = (
    Path(__file__).parents[1]
    / "experiments"
    / "003-remote-controller"
    / "validation"
    / "S003-P001.public.json"
)


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_real_public_validation_fixture_verifies_offline():
    bundle = load_fixture()
    checks = verify_public_trial(bundle)
    assert checks["valid"] is True
    with pytest.raises(TrialIntegrityError, match="forecast0_study_id"):
        extract_trial(bundle)


def test_seal_reveal_reordering_is_detected():
    bundle = load_fixture()
    forged = copy.deepcopy(bundle)
    comments = forged["public_record"]["comments"]
    seal_index = next(i for i, item in enumerate(comments) if item["body"].startswith("SAIS_SEAL "))
    reveal_index = next(i for i, item in enumerate(comments) if item["body"].startswith("SAIS_REVEAL "))
    comments[seal_index], comments[reveal_index] = comments[reveal_index], comments[seal_index]
    checks = verify_public_trial(forged)
    assert checks["valid"] is False
    assert checks["seal_precedes_reveal"] is False


def test_ledger_byte_tampering_is_detected():
    bundle = load_fixture()
    forged = copy.deepcopy(bundle)
    encoded = forged["public_record"]["ledger_source"]["content_base64"]
    forged["public_record"]["ledger_source"]["content_base64"] = encoded[:-4] + "AAAA"
    assert verify_public_trial(forged)["valid"] is False


def test_artifact_only_bundle_is_rejected_by_default():
    bundle = load_fixture()
    del bundle["public_record"]
    with pytest.raises(TrialIntegrityError, match="public_provenance_missing"):
        extract_trial(bundle)


def test_later_alternative_subject_forecast_does_not_replace_sealed_one():
    bundle = load_fixture()
    forged = copy.deepcopy(bundle)
    comments = forged["public_record"]["comments"]
    comments.insert(-2, {
        "id": 999_000_001,
        "created_at": "2026-08-31T04:21:01Z",
        "user": {"login": "Abdullah-m7"},
        "body": 'SAIS_FORECAST0 {"p_success":0.99}',
    })
    assert verify_public_trial(forged)["valid"] is True


def test_subject_authored_fake_controller_prefix_is_ignored():
    bundle = load_fixture()
    forged = copy.deepcopy(bundle)
    comments = forged["public_record"]["comments"]
    comments.insert(2, {
        "id": 999_000_002,
        "created_at": "2026-08-31T04:20:29Z",
        "user": {"login": "Abdullah-m7"},
        "body": 'SAIS_COMMIT {"forged":true}',
    })
    assert verify_public_trial(forged)["valid"] is True


def test_frozen_analysis_rejects_wrong_public_repository():
    bundle = load_fixture()
    forged = copy.deepcopy(bundle)
    forged["public_record"]["repository"] = "other/repository"
    assert verify_public_trial(forged)["valid"] is True
    with pytest.raises(TrialIntegrityError, match="frozen_public_repository"):
        extract_trial(forged)


def test_frozen_analysis_rejects_wrong_controller_actor():
    bundle = load_fixture()
    forged = copy.deepcopy(bundle)
    forged["public_record"]["controller_actor"] = "other-bot"
    with pytest.raises(TrialIntegrityError, match="frozen_public_controller_actor"):
        extract_trial(forged)


def test_collector_ignores_subject_fake_reveal(monkeypatch):
    bundle = load_fixture()
    comments = copy.deepcopy(bundle["public_record"]["comments"])
    comments.append({
        "id": 999_000_003,
        "created_at": "2026-08-31T04:22:00Z",
        "user": {"login": "Abdullah-m7"},
        "body": 'SAIS_REVEAL {"forged":true}',
    })
    source = bundle["public_record"]["ledger_source"]
    monkeypatch.setattr(pe, "_fetch_comments", lambda *_args: comments)
    monkeypatch.setattr(pe, "_api_get", lambda *_args: {
        "type": "file",
        "encoding": "base64",
        "content": source["content_base64"],
        "sha": source["api_blob_sha"],
    })

    collected = collect_public_trial(
        "Abdullah-m7/science-of-ai-systems", 6, token=None
    )
    assert collected["public_verification"]["valid"] is True
    assert collected["reveal"]["trial_id"] == "S003-P001"
