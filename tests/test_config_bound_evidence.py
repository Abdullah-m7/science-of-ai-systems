from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

import sais.rcl_bound_controller as controller
import sais.rcl_bound_evidence as evidence
from sais.public_evidence import git_blob_sha1

ROOT = Path(__file__).parents[1]
CONFIG = (
    ROOT / "experiments" / "005-config-bound-controller" / "validation" / "CONFIG.json"
)
CONFIG_PATH = "experiments/005-config-bound-controller/validation/CONFIG.json"
INSTRUCTION_PATH = "experiments/005-config-bound-controller/SUBJECT_INSTRUCTIONS.md"
INSTRUCTIONS = ROOT / INSTRUCTION_PATH
CONFIG_COMMIT = "a" * 40
CODE_SHA = "c" * 40
LEDGER_COMMIT = "b" * 40
REPOSITORY = "Abdullah-m7/science-of-ai-systems"


class FakeClient:
    issue_number = 88

    def __init__(self):
        self.items = []
        self.next_id = 1

    def _add(self, author, body):
        item = {
            "id": self.next_id,
            "created_at": f"t{self.next_id}",
            "user": {"login": author},
            "body": body,
        }
        self.next_id += 1
        self.items.append(item)
        return item

    def post(self, body):
        return self._add("github-actions[bot]", body)

    def _first(self, prefix):
        return next(
            (item for item in self.items if item["body"].startswith(prefix)), None
        )

    def comments(self):
        ready = self._first(controller.READY_PREFIX)
        if ready and not self._first(controller.FORECAST0_PREFIX):
            value = json.loads(ready["body"].split(" ", 1)[1])
            self._add(
                "subject",
                controller.FORECAST0_PREFIX
                + json.dumps(
                    {
                        "p_success": 0.5,
                        "configuration_binding_hash": value[
                            "configuration_binding_hash"
                        ],
                        "required_components": ["rcl_remote_controller"],
                        "rationale": "baseline",
                    }
                ),
            )
        probe = self._first(controller.PROBE_PREFIX)
        if probe and not self._first(controller.FORECAST1_PREFIX):
            value = json.loads(probe["body"].split(" ", 1)[1])
            self._add(
                "subject",
                controller.FORECAST1_PREFIX
                + json.dumps(
                    {
                        "p_success": 0.5,
                        "configuration_binding_hash": value[
                            "configuration_binding_hash"
                        ],
                        "observed_probe": value["probe_response"],
                        "required_components": ["rcl_remote_controller"],
                        "rationale": "probe update",
                    }
                ),
            )
        action = self._first(controller.ACTION_PREFIX)
        if action and not self._first(controller.DIAGNOSIS_PREFIX):
            value = json.loads(action["body"].split(" ", 1)[1])
            self._add(
                "subject",
                controller.DIAGNOSIS_PREFIX
                + json.dumps(
                    {
                        "claimed_condition": "available"
                        if value["success"]
                        else "degraded",
                        "configuration_binding_hash": value[
                            "configuration_binding_hash"
                        ],
                        "observed_action": value["observation"],
                        "rationale": "action diagnosis",
                    }
                ),
            )
        return list(self.items)


def make_bundle(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setattr(
        controller.secrets, "token_bytes", lambda _size: bytes.fromhex("45" * 32)
    )
    monkeypatch.setattr(
        controller,
        "persist_sealed_ledger",
        lambda _dir, _trial, ledger: (controller.object_hash(ledger), LEDGER_COMMIT),
    )
    result = controller.run_interactive_trial(
        client,
        trial_id="RCL-VAL-001",
        subject_login="subject",
        controller_code_sha=CODE_SHA,
        config_file=CONFIG,
        config_repository=REPOSITORY,
        config_commit=CONFIG_COMMIT,
        config_path=CONFIG_PATH,
        ledger_dir=tmp_path / "ledger",
        output_path=tmp_path / "result.json",
        timeout_seconds=1,
    )
    raw_ledger = (
        json.dumps(result["ledger"], indent=2, sort_keys=True) + "\n"
    ).encode()
    raw_config = CONFIG.read_bytes()
    raw_instructions = INSTRUCTIONS.read_bytes()
    bundle = {
        "ledger": result["ledger"],
        "reveal": result["reveal"],
        "configuration": json.loads(raw_config),
        "public_record": {
            "repository": REPOSITORY,
            "issue_number": 88,
            "controller_actor": "github-actions[bot]",
            "comments": client.items,
            "ledger_source": {
                "repository": REPOSITORY,
                "commit": LEDGER_COMMIT,
                "path": "rcl-controller/RCL-VAL-001.json",
                "api_blob_sha": git_blob_sha1(raw_ledger),
                "content_sha256": hashlib.sha256(raw_ledger).hexdigest(),
                "content_base64": base64.b64encode(raw_ledger).decode(),
            },
            "configuration_source": {
                "repository": REPOSITORY,
                "commit": CONFIG_COMMIT,
                "path": CONFIG_PATH,
                "api_blob_sha": git_blob_sha1(raw_config),
                "content_sha256": hashlib.sha256(raw_config).hexdigest(),
                "content_base64": base64.b64encode(raw_config).decode(),
            },
            "subject_instruction_source": {
                "repository": REPOSITORY,
                "commit": CONFIG_COMMIT,
                "path": INSTRUCTION_PATH,
                "api_blob_sha": git_blob_sha1(raw_instructions),
                "content_sha256": hashlib.sha256(raw_instructions).hexdigest(),
                "content_base64": base64.b64encode(raw_instructions).decode(),
            },
        },
    }
    return bundle


def verify(bundle):
    return evidence.verify_public_trial(
        bundle,
        expected_repository=REPOSITORY,
        expected_controller_actor="github-actions[bot]",
        expected_subject_actor="subject",
        expected_controller_code_sha=CODE_SHA,
        expected_configuration_commit=CONFIG_COMMIT,
        expected_configuration_path=CONFIG_PATH,
        expected_block_id="RCL-VAL-001",
    )


def test_public_bundle_verifies_ledger_and_configuration_bytes(monkeypatch, tmp_path):
    assert verify(make_bundle(monkeypatch, tmp_path))["valid"] is True


def test_configuration_object_substitution_is_detected(monkeypatch, tmp_path):
    forged = make_bundle(monkeypatch, tmp_path)
    forged["configuration"]["notes"] = "substituted"
    checks = verify(forged)
    assert checks["valid"] is False
    assert checks["configuration_object_matches"] is False


def test_subject_instruction_byte_substitution_is_detected(monkeypatch, tmp_path):
    forged = make_bundle(monkeypatch, tmp_path)
    replacement = b"substituted subject instructions\n"
    forged["public_record"]["subject_instruction_source"]["content_base64"] = (
        base64.b64encode(replacement).decode()
    )
    checks = verify(forged)
    assert checks["valid"] is False
    assert checks["instruction_blob_sha_matches"] is False
    assert checks["instruction_bytes_sha256_matches"] is False


def test_outsider_reveal_prefix_is_ignored(monkeypatch, tmp_path):
    forged = make_bundle(monkeypatch, tmp_path)
    forged["public_record"]["comments"].append(
        {
            "id": 999,
            "created_at": "t999",
            "user": {"login": "outsider"},
            "body": 'SAIS_RCL_REVEAL {"forged":true}',
        }
    )
    assert verify(forged)["valid"] is True


def test_duplicate_frozen_controller_phase_is_rejected(monkeypatch, tmp_path):
    forged = make_bundle(monkeypatch, tmp_path)
    forged["public_record"]["comments"].append(
        {
            "id": 999,
            "created_at": "t999",
            "user": {"login": "github-actions[bot]"},
            "body": 'SAIS_RCL_COMMIT {"forged":true}',
        }
    )
    assert verify(forged)["valid"] is False


def test_expected_controller_code_is_enforced(monkeypatch, tmp_path):
    bundle = make_bundle(monkeypatch, tmp_path)
    checks = evidence.verify_public_trial(bundle, expected_controller_code_sha="0" * 40)
    assert checks["valid"] is False
    assert checks["controller_code_matches_expected"] is False


def test_expected_configuration_commit_is_enforced(monkeypatch, tmp_path):
    bundle = make_bundle(monkeypatch, tmp_path)
    checks = evidence.verify_public_trial(
        bundle, expected_configuration_commit="0" * 40
    )
    assert checks["valid"] is False
    assert checks["configuration_commit_matches_expected"] is False


def test_expected_configuration_path_and_block_are_enforced(monkeypatch, tmp_path):
    bundle = make_bundle(monkeypatch, tmp_path)
    checks = evidence.verify_public_trial(
        bundle,
        expected_configuration_path="other/config.json",
        expected_block_id="OTHER-BLOCK",
    )
    assert checks["valid"] is False
    assert checks["configuration_path_matches_expected"] is False
    assert checks["configuration_block_matches_expected"] is False


def test_live_collector_round_trips_three_exact_git_sources(monkeypatch, tmp_path):
    bundle = make_bundle(monkeypatch, tmp_path)
    public = bundle["public_record"]
    monkeypatch.setattr(
        evidence,
        "_fetch_comments",
        lambda repository, issue_number, token: public["comments"],
    )

    def fake_api_get(url, token=None):
        if "rcl-controller" in url:
            source = public["ledger_source"]
        elif "CONFIG.json" in url:
            source = public["configuration_source"]
        else:
            source = public["subject_instruction_source"]
        return {
            "type": "file",
            "encoding": "base64",
            "content": source["content_base64"],
            "sha": source["api_blob_sha"],
        }

    monkeypatch.setattr(evidence, "_api_get", fake_api_get)
    collected = evidence.collect_public_trial(
        REPOSITORY,
        88,
        controller_actor="github-actions[bot]",
        expected_subject_actor="subject",
        expected_controller_code_sha=CODE_SHA,
        expected_configuration_commit=CONFIG_COMMIT,
        expected_configuration_path=CONFIG_PATH,
        expected_block_id="RCL-VAL-001",
    )
    assert collected["public_verification"]["valid"] is True
    assert collected["configuration"]["block_id"] == "RCL-VAL-001"


def test_collector_rejects_unsafe_repository_before_network(monkeypatch):
    called = False

    def should_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network should not be reached")

    monkeypatch.setattr(evidence, "_fetch_comments", should_not_run)
    with pytest.raises(ValueError, match="owner/name"):
        evidence.collect_public_trial("owner/repo/../../other", 1)
    assert called is False


def test_invalid_expected_commit_is_rejected_before_network(monkeypatch):
    called = False

    def should_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network should not be reached")

    monkeypatch.setattr(evidence, "_fetch_comments", should_not_run)
    with pytest.raises(ValueError, match="expected configuration commit"):
        evidence.collect_public_trial(
            REPOSITORY, 1, expected_configuration_commit="not-a-commit"
        )
    assert called is False
