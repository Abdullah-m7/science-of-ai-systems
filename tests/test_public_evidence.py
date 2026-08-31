from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sais import public_evidence
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
    record = extract_trial(bundle)
    assert record["trial_id"] == "S003-P001"
    assert record["outcome"] == 1
    assert record["legibility"] == "opaque"


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


def test_outsider_fake_reveal_is_ignored_by_frozen_actor_selection():
    bundle = load_fixture()
    forged = copy.deepcopy(bundle)
    forged["public_record"]["comments"].append({
        "id": 999_000_003,
        "created_at": "2026-08-31T04:21:02Z",
        "user": {"login": "outsider"},
        "body": 'SAIS_REVEAL {"forged":true}',
    })
    assert verify_public_trial(forged)["valid"] is True


def test_duplicate_controller_phase_from_frozen_actor_is_rejected():
    bundle = load_fixture()
    forged = copy.deepcopy(bundle)
    forged["public_record"]["comments"].append({
        "id": 999_000_004,
        "created_at": "2026-08-31T04:21:03Z",
        "user": {"login": "github-actions[bot]"},
        "body": 'SAIS_COMMIT {"forged":true}',
    })
    checks = verify_public_trial(forged)
    assert checks["valid"] is False
    assert checks["public_structure_valid"] is False


def test_expected_repository_mismatch_is_rejected():
    bundle = load_fixture()
    checks = verify_public_trial(
        bundle, expected_repository="other-owner/other-repository"
    )
    assert checks["valid"] is False
    assert checks["repository_matches_expected"] is False


def test_collector_uses_frozen_actor_and_round_trips_fixture(monkeypatch):
    fixture = load_fixture()
    monkeypatch.setattr(
        public_evidence,
        "_fetch_comments",
        lambda repository, issue_number, token: fixture["public_record"]["comments"],
    )
    source = fixture["public_record"]["ledger_source"]
    monkeypatch.setattr(
        public_evidence,
        "_api_get",
        lambda url, token=None: {
            "type": "file",
            "encoding": "base64",
            "content": "\n".join(
                source["content_base64"][index:index + 60]
                for index in range(0, len(source["content_base64"]), 60)
            ),
            "sha": source["api_blob_sha"],
        },
    )
    collected = collect_public_trial(
        "Abdullah-m7/science-of-ai-systems",
        6,
        controller_actor="github-actions[bot]",
    )
    assert collected["ledger"]["trial_id"] == "S003-P001"
    assert collected["public_verification"]["valid"] is True


def test_confirmatory_extractor_rejects_cross_repository_bundle():
    bundle = load_fixture()
    bundle["public_record"]["repository"] = "other-owner/other-repository"
    with pytest.raises(TrialIntegrityError, match="repository_matches_expected"):
        extract_trial(bundle)


def test_confirmatory_extractor_rejects_wrong_subject_actor():
    bundle = load_fixture()
    bundle["ledger"]["subject_login"] = "other-subject"
    with pytest.raises(TrialIntegrityError):
        extract_trial(bundle)


def test_confirmatory_extractor_rejects_wrong_controller_code_sha_early():
    bundle = load_fixture()
    bundle["ledger"]["controller_code_sha"] = "0" * 40
    bundle["reveal"]["controller_code_sha"] = "0" * 40
    with pytest.raises(TrialIntegrityError, match="controller_code_sha_mismatch"):
        extract_trial(bundle)


def test_confirmatory_extractor_rejects_wrong_protocol_early():
    bundle = load_fixture()
    bundle["ledger"]["protocol_version"] = "SMI-CP/UNFROZEN"
    bundle["reveal"]["protocol_version"] = "SMI-CP/UNFROZEN"
    with pytest.raises(TrialIntegrityError, match="controller_protocol_mismatch"):
        extract_trial(bundle)


def test_github_base64_decoder_accepts_ascii_wrapping_and_rejects_noise():
    encoded = "YQ==\n\t"
    assert public_evidence.decode_github_base64(encoded, source="fixture") == b"a"
    with pytest.raises(public_evidence.PublicEvidenceError, match="not valid base64"):
        public_evidence.decode_github_base64("YQ==!", source="fixture")
