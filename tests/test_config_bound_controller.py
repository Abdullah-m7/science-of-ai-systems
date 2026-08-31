from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import sais.rcl_bound_controller as controller
from sais.config_binding import (
    binding_hash,
    build_binding,
    load_product_config,
    validate_reference,
)
from sais.rcl_bound_controller import run_interactive_trial, verify_sealed_trial

ROOT = Path(__file__).parents[1]
CONFIG = (
    ROOT / "experiments" / "005-config-bound-controller" / "validation" / "CONFIG.json"
)
CONFIG_COMMIT = "a" * 40
CONFIG_PATH = "experiments/005-config-bound-controller/validation/CONFIG.json"


class FakeIssueClient:
    issue_number = 88

    def __init__(self, subject: str = "subject", wrong_binding: bool = False):
        self.subject = subject
        self.wrong_binding = wrong_binding
        self.items: list[dict] = []
        self.next_id = 1

    def _add(self, author: str, body: str) -> dict:
        item = {
            "id": self.next_id,
            "created_at": f"t{self.next_id}",
            "user": {"login": author},
            "body": body,
        }
        self.next_id += 1
        self.items.append(item)
        return item

    def post(self, body: str) -> dict:
        return self._add("github-actions[bot]", body)

    def _first(self, prefix: str) -> dict | None:
        return next(
            (item for item in self.items if item["body"].startswith(prefix)), None
        )

    def comments(self) -> list[dict]:
        ready = self._first(controller.READY_PREFIX)
        if ready and not self._first(controller.FORECAST0_PREFIX):
            value = json.loads(ready["body"].split(" ", 1)[1])
            bound_hash = (
                "0" * 64 if self.wrong_binding else value["configuration_binding_hash"]
            )
            self._add(
                self.subject,
                controller.FORECAST0_PREFIX
                + json.dumps(
                    {
                        "p_success": 0.5,
                        "configuration_binding_hash": bound_hash,
                        "required_components": ["rcl_remote_controller"],
                        "rationale": "symmetric before hidden state generation",
                    }
                ),
            )
        probe = self._first(controller.PROBE_PREFIX)
        if probe and not self._first(controller.FORECAST1_PREFIX):
            value = json.loads(probe["body"].split(" ", 1)[1])
            observed = value["probe_response"]
            probability = (
                0.99
                if observed == "available"
                else 0.01
                if observed == "degraded"
                else 0.5
            )
            self._add(
                self.subject,
                controller.FORECAST1_PREFIX
                + json.dumps(
                    {
                        "p_success": probability,
                        "configuration_binding_hash": value[
                            "configuration_binding_hash"
                        ],
                        "observed_probe": observed,
                        "required_components": ["rcl_remote_controller"],
                        "rationale": "updated from the visible probe only",
                    }
                ),
            )
        action = self._first(controller.ACTION_PREFIX)
        if action and not self._first(controller.DIAGNOSIS_PREFIX):
            value = json.loads(action["body"].split(" ", 1)[1])
            self._add(
                self.subject,
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
                        "rationale": "diagnosed from the action result",
                    }
                ),
            )
        return list(self.items)


def run_fake(monkeypatch, tmp_path, *, wrong_binding: bool = False):
    client = FakeIssueClient(wrong_binding=wrong_binding)

    def deterministic_key(_size: int) -> bytes:
        assert client._first(controller.FORECAST0_PREFIX) is not None
        return bytes.fromhex("45" * 32)

    monkeypatch.setattr(controller.secrets, "token_bytes", deterministic_key)
    monkeypatch.setattr(
        controller,
        "persist_sealed_ledger",
        lambda _dir, _trial, ledger: (controller.object_hash(ledger), "b" * 40),
    )
    result = run_interactive_trial(
        client,
        trial_id="RCL-VAL-001",
        subject_login="subject",
        controller_code_sha="c" * 40,
        config_file=CONFIG,
        config_repository="Abdullah-m7/science-of-ai-systems",
        config_commit=CONFIG_COMMIT,
        config_path=CONFIG_PATH,
        ledger_dir=tmp_path / "ledger",
        output_path=tmp_path / "result.json",
        timeout_seconds=1,
    )
    return client, result


def test_validation_configuration_builds_byte_binding():
    config, raw = load_product_config(CONFIG)
    binding = build_binding(
        config,
        raw,
        repository="Abdullah-m7/science-of-ai-systems",
        commit=CONFIG_COMMIT,
        path=CONFIG_PATH,
    )
    assert binding["block_id"] == "RCL-VAL-001"
    assert len(binding["config_sha256"]) == 64
    assert len(binding_hash(binding)) == 64


def test_unsafe_configuration_reference_is_rejected():
    with pytest.raises(ValueError, match="unsafe configuration path"):
        validate_reference(
            "Abdullah-m7/science-of-ai-systems", CONFIG_COMMIT, "../secret.json"
        )


def test_configuration_bound_protocol_end_to_end(monkeypatch, tmp_path):
    client, result = run_fake(monkeypatch, tmp_path)
    assert result["verification"]["valid"] is True
    assert result["ledger"]["configuration_binding"]["commit"] == CONFIG_COMMIT
    assert (
        result["ledger"]["configuration_binding_hash"]
        == result["reveal"]["configuration_binding_hash"]
    )
    assert [item["body"].split(" ", 1)[0] for item in client.items] == [
        "SAIS_RCL_READY",
        "SAIS_RCL_FORECAST0",
        "SAIS_RCL_COMMIT",
        "SAIS_RCL_PROBE",
        "SAIS_RCL_FORECAST1",
        "SAIS_RCL_ACTION",
        "SAIS_RCL_DIAGNOSIS",
        "SAIS_RCL_SEAL",
        "SAIS_RCL_REVEAL",
    ]


def test_subject_cannot_echo_a_different_binding(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="does not echo"):
        run_fake(monkeypatch, tmp_path, wrong_binding=True)


def test_binding_tamper_breaks_signed_trial(monkeypatch, tmp_path):
    _client, result = run_fake(monkeypatch, tmp_path)
    forged_ledger = copy.deepcopy(result["ledger"])
    forged_reveal = copy.deepcopy(result["reveal"])
    forged_ledger["configuration_binding"]["path"] = "other/config.json"
    forged_ledger["configuration_binding_hash"] = binding_hash(
        forged_ledger["configuration_binding"]
    )
    forged_reveal["configuration_binding"] = forged_ledger["configuration_binding"]
    forged_reveal["configuration_binding_hash"] = forged_ledger[
        "configuration_binding_hash"
    ]
    forged_reveal["ledger_hash"] = controller.object_hash(forged_ledger)
    assert verify_sealed_trial(forged_ledger, forged_reveal)["valid"] is False


def test_unknown_configuration_field_is_rejected(tmp_path):
    value = json.loads(CONFIG.read_text(encoding="utf-8"))
    value["unfrozen_field"] = "surprise"
    forged = tmp_path / "config.json"
    forged.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown product configuration fields"):
        load_product_config(forged)


def test_naive_configuration_timestamp_is_rejected(tmp_path):
    value = json.loads(CONFIG.read_text(encoding="utf-8"))
    value["recorded_at_utc"] = "2026-08-31T07:11:25"
    forged = tmp_path / "config.json"
    forged.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="include a timezone"):
        load_product_config(forged)


def test_non_utc_configuration_timestamp_is_rejected(tmp_path):
    value = json.loads(CONFIG.read_text(encoding="utf-8"))
    value["recorded_at_utc"] = "2026-08-31T10:11:25+03:00"
    forged = tmp_path / "config.json"
    forged.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="must use UTC"):
        load_product_config(forged)


def test_instruction_path_traversal_is_rejected(tmp_path):
    value = json.loads(CONFIG.read_text(encoding="utf-8"))
    value["subject_instruction_path"] = "../SUBJECT_INSTRUCTIONS.md"
    forged = tmp_path / "config.json"
    forged.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="unsafe subject instruction path"):
        load_product_config(forged)


def test_symlinked_configuration_is_rejected(tmp_path):
    target = tmp_path / "target.json"
    target.write_bytes(CONFIG.read_bytes())
    link = tmp_path / "config.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="regular file"):
        load_product_config(link)


def test_forecast_fields_are_protocol_closed():
    value = {
        "p_success": 0.5,
        "configuration_binding_hash": "a" * 64,
        "required_components": ["controller"],
        "rationale": "baseline",
        "unfrozen_extra": True,
    }
    with pytest.raises(ValueError, match="fields do not match"):
        controller.validate_probability_record(value, "a" * 64)


def test_repository_dot_segment_is_rejected():
    with pytest.raises(ValueError, match="unsafe configuration repository"):
        validate_reference("../repo", CONFIG_COMMIT, CONFIG_PATH)


def test_noncanonical_repository_path_is_rejected():
    with pytest.raises(ValueError, match="unsafe configuration path"):
        validate_reference(
            "Abdullah-m7/science-of-ai-systems", CONFIG_COMMIT, "a//config.json"
        )
