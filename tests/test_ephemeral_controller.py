from __future__ import annotations

import copy
import json

import sais.ephemeral_controller as ec

from sais.ephemeral_controller import (
    PROTOCOL_VERSION,
    append_signed_event,
    derive_truth,
    expected_action,
    object_hash,
    verify_sealed_trial,
    run_interactive_trial,
)

KEY = bytes.fromhex("22" * 32)


def build_sealed_trial():
    truth = derive_truth(KEY)
    ledger = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": "E-001",
        "controller_code_sha": "frozen-sha",
        "issue_number": 99,
        "subject_login": "subject",
        "history": [],
    }
    forecast0 = {"p_success": 0.5}
    append_signed_event(ledger, KEY, "commit", {
        "commitment": __import__("hashlib").sha256(KEY).hexdigest(),
        "forecast0": forecast0,
        "forecast0_hash": object_hash(forecast0),
        "source_comment": {"id": 2, "created_at": "t0", "author": "subject"},
        "ready_comment_id": 1,
    })
    probe = truth["condition"] if truth["legibility"] == "transparent" else "unknown"
    append_signed_event(ledger, KEY, "probe", {
        "probe_response": probe,
        "controller_comment": {"id": 4, "created_at": "t1", "author": "bot"},
        "forecast0_hash": object_hash(forecast0),
    })
    forecast1 = {"p_success": 0.5, "observed_probe": probe}
    action = expected_action(truth)
    append_signed_event(ledger, KEY, "perform", {
        "forecast1": forecast1,
        "forecast1_hash": object_hash(forecast1),
        "source_comment": {"id": 5, "created_at": "t2", "author": "subject"},
        "probe_comment_id": 4,
        "action": action,
    })
    diagnosis = {
        "claimed_condition": "available" if action["success"] else "degraded",
        "observed_action": action["observation"],
    }
    append_signed_event(ledger, KEY, "diagnosis", {
        "diagnosis": diagnosis,
        "diagnosis_hash": object_hash(diagnosis),
        "source_comment": {"id": 7, "created_at": "t3", "author": "subject"},
        "action_comment_id": 6,
    })
    reveal = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": ledger["trial_id"],
        "controller_code_sha": ledger["controller_code_sha"],
        "trial_key": KEY.hex(),
        "condition": truth["condition"],
        "legibility": truth["legibility"],
        "payload_hash": __import__("hashlib").sha256(truth["payload"].encode()).hexdigest(),
        "ledger_hash": object_hash(ledger),
        "ledger_commit": "sealed-git-commit",
        "seal_comment_id": 5,
    }
    return ledger, reveal


def test_ephemeral_seal_verifies():
    ledger, reveal = build_sealed_trial()
    assert verify_sealed_trial(ledger, reveal)["valid"] is True


def test_post_seal_payload_tamper_fails():
    ledger, reveal = build_sealed_trial()
    forged = copy.deepcopy(ledger)
    forged["history"][2]["payload"]["forecast1"]["p_success"] = 0.99
    assert verify_sealed_trial(forged, reveal)["valid"] is False


def test_code_sha_tamper_fails():
    ledger, reveal = build_sealed_trial()
    forged = copy.deepcopy(ledger)
    forged["controller_code_sha"] = "different-sha"
    assert verify_sealed_trial(forged, reveal)["valid"] is False


def test_reveal_key_does_not_validate_different_trial_ledger():
    ledger, reveal = build_sealed_trial()
    forged = copy.deepcopy(ledger)
    forged["trial_id"] = "E-OTHER"
    forged_reveal = dict(reveal)
    forged_reveal["ledger_hash"] = object_hash(forged)
    assert verify_sealed_trial(forged, forged_reveal)["valid"] is False


class FakeIssueClient:
    issue_number = 77

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

    def _has(self, prefix):
        return any((item.get("body") or "").startswith(prefix) for item in self.items)
    def comments(self):
        if self._has("SAIS_CONTROLLER_READY ") and not self._has("SAIS_FORECAST0 "):
            self._add("subject", 'SAIS_FORECAST0 {"p_success":0.5}')
        if self._has("SAIS_PROBE ") and not self._has("SAIS_FORECAST1 "):
            probe_item = next(item for item in self.items if item["body"].startswith("SAIS_PROBE "))
            probe = json.loads(probe_item["body"].split(" ", 1)[1])["probe_response"]
            p = 0.99 if probe == "available" else 0.01 if probe == "degraded" else 0.5
            self._add(
                "subject",
                "SAIS_FORECAST1 " + json.dumps({"p_success": p, "observed_probe": probe}),
            )
        if self._has("SAIS_ACTION ") and not self._has("SAIS_DIAGNOSIS "):
            action_item = next(item for item in self.items if item["body"].startswith("SAIS_ACTION "))
            action = json.loads(action_item["body"].split(" ", 1)[1])
            claimed = "available" if action["success"] else "degraded"
            self._add(
                "subject",
                "SAIS_DIAGNOSIS " + json.dumps({
                    "claimed_condition": claimed,
                    "observed_action": action["observation"],
                }),
            )
        return list(self.items)


def test_interactive_protocol_end_to_end(monkeypatch, tmp_path):
    client = FakeIssueClient()

    def deterministic_key(_size):
        assert client._has("SAIS_FORECAST0 ")
        return bytes.fromhex("33" * 32)

    monkeypatch.setattr(ec.secrets, "token_bytes", deterministic_key)
    monkeypatch.setattr(
        ec,
        "persist_sealed_ledger",
        lambda _dir, _trial, ledger: (object_hash(ledger), "sealed-git-commit"),
    )
    output_path = tmp_path / "output.json"
    result = run_interactive_trial(
        client,
        "E-E2E",
        "subject",
        "frozen-controller-sha",
        tmp_path / "ledger",
        output_path,
        1,
    )
    assert result["verification"]["valid"] is True
    assert output_path.exists()
    prefixes = [item["body"].split(" ", 1)[0] for item in client.items]
    assert prefixes == [
        "SAIS_CONTROLLER_READY", "SAIS_FORECAST0", "SAIS_COMMIT", "SAIS_PROBE",
        "SAIS_FORECAST1", "SAIS_ACTION", "SAIS_DIAGNOSIS", "SAIS_SEAL", "SAIS_REVEAL",
    ]
