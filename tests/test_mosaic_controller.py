from __future__ import annotations

from copy import deepcopy
import json

import pytest

import sais.mosaic_controller as controller
from sais.mosaic import bayes_update, canonical_hash, make_design_matrix

STUDY_BINDING = "a" * 64
DESIGN_HASH = canonical_hash(make_design_matrix())
SUBJECT = "subject"


def _core_rows() -> list[dict]:
    rows = make_design_matrix()
    core_id = rows[0]["core_id"]
    return [row for row in rows if row["core_id"] == core_id]


class SharedTrace:
    def __init__(self):
        self.events: list[tuple[str, str, str]] = []

    def add(self, trial_id: str, author: str, body: str) -> None:
        prefix = body.split(" ", 1)[0]
        self.events.append((trial_id, author, prefix))


class FakeIssueClient:
    def __init__(
        self,
        row: dict,
        issue_number: int,
        trace: SharedTrace,
        *,
        malformed_p0: bool = False,
        duplicate_p1: bool = False,
        unexpected_after_p0: bool = False,
    ):
        self.row = row
        self.issue_number = issue_number
        self.trace = trace
        self.malformed_p0 = malformed_p0
        self.duplicate_p1 = duplicate_p1
        self.unexpected_after_p0 = unexpected_after_p0
        self.items: list[dict] = []
        self.next_id = 1
        self.visible_cues: list[dict] = []

    def _add(self, author: str, body: str) -> dict:
        item = {
            "id": self.next_id,
            "created_at": f"2026-09-01T00:00:{self.next_id:02d}Z",
            "user": {"login": author},
            "body": body,
        }
        self.next_id += 1
        self.items.append(item)
        self.trace.add(self.row["trial_id"], author, body)
        return item

    def post(self, body: str) -> dict:
        if body.startswith(controller.CUE1_PREFIX) or body.startswith(controller.CUE2_PREFIX):
            self.visible_cues.append(json.loads(body.split(" ", 1)[1]))
        return self._add("controller", body)

    def _first(self, prefix: str) -> dict | None:
        return next((item for item in self.items if item["body"].startswith(prefix)), None)

    def _subject_record(self, prefix: str, value: dict) -> None:
        self._add(SUBJECT, prefix + json.dumps(value, sort_keys=True))

    def comments(self) -> list[dict]:
        ready = self._first(controller.READY_PREFIX)
        if ready and not self._first(controller.P0_PREFIX):
            base = {
                "protocol_version": controller.SUBJECT_PROTOCOL,
                "trial_id": self.row["trial_id"],
                "core_id": self.row["core_id"],
                "study_binding_hash": STUDY_BINDING,
                "p_available": 0.5,
                "rationale": "symmetric disclosed prior",
            }
            if self.malformed_p0:
                self._add(SUBJECT, controller.P0_PREFIX + "{bad-json")
            self._subject_record(controller.P0_PREFIX, base)
            if self.unexpected_after_p0:
                self._add(SUBJECT, "unstructured alternative commentary")

        cue1 = self._first(controller.CUE1_PREFIX)
        if cue1 and not self._first(controller.P1_PREFIX):
            value = json.loads(cue1["body"].split(" ", 1)[1])
            p1 = bayes_update(0.5, value["claim"], value["stated_reliability"])
            record = {
                "protocol_version": controller.SUBJECT_PROTOCOL,
                "trial_id": self.row["trial_id"],
                "core_id": self.row["core_id"],
                "study_binding_hash": STUDY_BINDING,
                "p_available": p1,
                "observed_cue_hash": value["cue_hash"],
                "rationale": "updated from first disclosed cue",
            }
            self._subject_record(controller.P1_PREFIX, record)
            if self.duplicate_p1:
                duplicate = dict(record)
                duplicate["rationale"] = "alternative duplicate response"
                self._subject_record(controller.P1_PREFIX, duplicate)

        cue2 = self._first(controller.CUE2_PREFIX)
        if cue2 and not self._first(controller.P2_PREFIX):
            first = dict(self.visible_cues[0])
            second = dict(self.visible_cues[1])
            first.pop("cue_hash", None)
            second.pop("cue_hash", None)
            p = 0.5
            for cue in (first, second):
                p = bayes_update(p, cue["claim"], cue["stated_reliability"])
            record = {
                "protocol_version": controller.SUBJECT_PROTOCOL,
                "trial_id": self.row["trial_id"],
                "core_id": self.row["core_id"],
                "study_binding_hash": STUDY_BINDING,
                "p_available": p,
                "observed_evidence_hash": canonical_hash([first, second]),
                "rationale": "integrated both disclosed cues",
            }
            self._subject_record(controller.P2_PREFIX, record)

        action = self._first(controller.ACTION_PREFIX)
        if action and not self._first(controller.DIAGNOSIS_PREFIX):
            value = json.loads(action["body"].split(" ", 1)[1])
            record = {
                "protocol_version": controller.SUBJECT_PROTOCOL,
                "trial_id": self.row["trial_id"],
                "core_id": self.row["core_id"],
                "study_binding_hash": STUDY_BINDING,
                "claimed_condition": "available" if value["success"] else "degraded",
                "observed_action": value["observation"],
                "rationale": "diagnosed from controlled action",
            }
            self._subject_record(controller.DIAGNOSIS_PREFIX, record)
        return list(self.items)


def _clients(
    rows: list[dict],
    *,
    malformed_trial: str | None = None,
    duplicate_p1_trial: str | None = None,
    unexpected_after_p0_trial: str | None = None,
) -> tuple[dict[str, FakeIssueClient], SharedTrace]:
    trace = SharedTrace()
    clients = {
        row["trial_id"]: FakeIssueClient(
            row,
            100 + index,
            trace,
            malformed_p0=row["trial_id"] == malformed_trial,
            duplicate_p1=row["trial_id"] == duplicate_p1_trial,
            unexpected_after_p0=row["trial_id"] == unexpected_after_p0_trial,
        )
        for index, row in enumerate(rows, start=1)
    }
    return clients, trace


def _run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    malformed_trial: str | None = None,
    duplicate_p1_trial: str | None = None,
    seal_failure: bool = False,
):
    rows = _core_rows()
    clients, trace = _clients(
        rows,
        malformed_trial=malformed_trial,
        duplicate_p1_trial=duplicate_p1_trial,
    )
    key_calls: list[bool] = []

    def keygen(size: int) -> bytes:
        assert size == 32
        assert all(client._first(controller.P0_PREFIX) is not None for client in clients.values())
        assert all(client._first(controller.P0_SEAL_PREFIX) is not None for client in clients.values())
        trace.events.append(("CORE", "keygen", "KEYGEN"))
        key_calls.append(True)
        return bytes.fromhex("45" * 32)

    monkeypatch.setattr(controller.secrets, "token_bytes", keygen)

    sealed: list[dict] = []

    def baseline_seal(ledger: dict) -> str:
        trace.events.append(("CORE", "baseline-seal", "BASELINE_SEAL_CALLBACK"))
        return "git:baseline-deadbeef"

    def seal(ledger: dict) -> str:
        trace.events.append(("CORE", "seal", "FINAL_SEAL_CALLBACK"))
        if seal_failure:
            raise RuntimeError("synthetic immutable store failure")
        sealed.append(deepcopy(ledger))
        return "git:deadbeef"

    def seal_envelope(envelope: dict) -> str:
        trace.events.append(("CORE", "seal-envelope", "SEAL_ENVELOPE_CALLBACK"))
        return "git:envelope-deadbeef"

    result = controller.run_quartet(
        clients,
        rows,
        subject_login=SUBJECT,
        study_binding_hash=STUDY_BINDING,
        design_hash=DESIGN_HASH,
        baseline_seal_callback=baseline_seal,
        seal_callback=seal,
        seal_envelope_callback=seal_envelope,
        timeout_seconds=0.1,
    )
    return rows, clients, trace, key_calls, sealed, result


def _event_positions(trace: SharedTrace, prefix: str, author: str | None = None) -> list[int]:
    return [
        index for index, (_trial, event_author, event_prefix) in enumerate(trace.events)
        if event_prefix == prefix and (author is None or event_author == author)
    ]


def test_successful_quartet_respects_all_global_barriers(monkeypatch) -> None:
    rows, clients, trace, key_calls, sealed, result = _run(monkeypatch)
    assert key_calls == [True]
    assert len(sealed) == 1
    assert result["verification"]["valid"] is True
    assert all(
        client._first(controller.REVEAL_PREFIX) is not None
        for client in clients.values()
    )

    p0 = _event_positions(trace, controller.P0_PREFIX.strip(), SUBJECT)
    baseline_callback = _event_positions(trace, "BASELINE_SEAL_CALLBACK", "baseline-seal")
    p0_seals = _event_positions(trace, controller.P0_SEAL_PREFIX.strip(), "controller")
    keygen = _event_positions(trace, "KEYGEN", "keygen")
    commits = _event_positions(trace, controller.COMMIT_PREFIX.strip(), "controller")
    p1 = _event_positions(trace, controller.P1_PREFIX.strip(), SUBJECT)
    cue2 = _event_positions(trace, controller.CUE2_PREFIX.strip(), "controller")
    p2 = _event_positions(trace, controller.P2_PREFIX.strip(), SUBJECT)
    actions = _event_positions(trace, controller.ACTION_PREFIX.strip(), "controller")
    diagnoses = _event_positions(trace, controller.DIAGNOSIS_PREFIX.strip(), SUBJECT)
    seals = _event_positions(trace, controller.SEAL_PREFIX.strip(), "controller")
    reveals = _event_positions(trace, controller.REVEAL_PREFIX.strip(), "controller")
    seal_callback = _event_positions(trace, "FINAL_SEAL_CALLBACK", "seal")
    envelope_callback = _event_positions(
        trace, "SEAL_ENVELOPE_CALLBACK", "seal-envelope"
    )

    assert len(p0) == len(p0_seals) == len(commits) == len(p1) == len(cue2) == 4
    assert len(p2) == len(actions) == len(diagnoses) == len(seals) == len(reveals) == 4
    assert len(baseline_callback) == len(keygen) == len(seal_callback) == len(envelope_callback) == 1
    assert max(p0) < baseline_callback[0] < min(p0_seals)
    assert max(p0_seals) < keygen[0] < min(commits)
    assert max(p1) < min(cue2)
    assert max(p2) < min(actions)
    assert max(diagnoses) < seal_callback[0] < envelope_callback[0] < min(seals)
    assert max(seals) < min(reveals)

    finals = [
        result["ledger"]["trials"][row["trial_id"]]["ideal_probability_path"][-1]
        for row in rows
    ]
    assert max(finals) - min(finals) < 1e-12


def test_malformed_first_p0_cannot_be_repaired_or_randomized(monkeypatch) -> None:
    rows = _core_rows()
    bad_id = rows[0]["trial_id"]
    clients, _trace = _clients(rows, malformed_trial=bad_id)
    key_called = False

    def forbidden_keygen(_size: int) -> bytes:
        nonlocal key_called
        key_called = True
        raise AssertionError("hidden entropy must not be generated")

    monkeypatch.setattr(controller.secrets, "token_bytes", forbidden_keygen)
    with pytest.raises(json.JSONDecodeError):
        controller.run_quartet(
            clients,
            rows,
            subject_login=SUBJECT,
            study_binding_hash=STUDY_BINDING,
            design_hash=DESIGN_HASH,
            baseline_seal_callback=lambda _ledger: "git:baseline-test",
            seal_callback=lambda _ledger: "never",
            seal_envelope_callback=lambda _envelope: "git:envelope-test",
            timeout_seconds=0.1,
        )
    assert key_called is False


def test_duplicate_p1_blocks_seal_and_reveal(monkeypatch) -> None:
    rows = _core_rows()
    duplicate_id = rows[1]["trial_id"]
    clients, _trace = _clients(rows, duplicate_p1_trial=duplicate_id)
    monkeypatch.setattr(
        controller.secrets, "token_bytes", lambda _size: bytes.fromhex("45" * 32)
    )
    sealed = False

    def forbidden_seal(_ledger: dict) -> str:
        nonlocal sealed
        sealed = True
        return "should-not-happen"

    with pytest.raises(ValueError, match="protocol violation"):
        controller.run_quartet(
            clients,
            rows,
            subject_login=SUBJECT,
            study_binding_hash=STUDY_BINDING,
            design_hash=DESIGN_HASH,
            baseline_seal_callback=lambda _ledger: "git:baseline-test",
            seal_callback=forbidden_seal,
            seal_envelope_callback=lambda _envelope: "git:envelope-test",
            timeout_seconds=0.1,
        )
    assert sealed is False
    assert all(
        client._first(controller.REVEAL_PREFIX) is None
        for client in clients.values()
    )


def test_seal_failure_prevents_any_reveal(monkeypatch) -> None:
    rows = _core_rows()
    clients, _trace = _clients(rows)
    monkeypatch.setattr(
        controller.secrets, "token_bytes", lambda _size: bytes.fromhex("45" * 32)
    )
    with pytest.raises(RuntimeError, match="immutable store failure"):
        controller.run_quartet(
            clients,
            rows,
            subject_login=SUBJECT,
            study_binding_hash=STUDY_BINDING,
            design_hash=DESIGN_HASH,
            baseline_seal_callback=lambda _ledger: "git:baseline-test",
            seal_callback=lambda _ledger: (_ for _ in ()).throw(
                RuntimeError("synthetic immutable store failure")
            ),
            seal_envelope_callback=lambda _envelope: "git:envelope-test",
            timeout_seconds=0.1,
        )
    assert all(client._first(controller.SEAL_PREFIX) is None for client in clients.values())
    assert all(client._first(controller.REVEAL_PREFIX) is None for client in clients.values())


def test_design_transform_tamper_is_rejected_before_any_post() -> None:
    rows = _core_rows()
    forged = deepcopy(rows)
    forged[0]["labels"] = {"X": "source_k", "Y": "source_m"}
    clients, trace = _clients(forged)
    with pytest.raises(ValueError, match="frozen design"):
        controller.run_quartet(
            clients,
            forged,
            subject_login=SUBJECT,
            study_binding_hash=STUDY_BINDING,
            design_hash=DESIGN_HASH,
            baseline_seal_callback=lambda _ledger: "git:baseline-test",
            seal_callback=lambda _ledger: "never",
            seal_envelope_callback=lambda _envelope: "git:envelope-test",
            timeout_seconds=0.1,
        )
    assert trace.events == []


def test_tampered_sealed_cue_fails_verification(monkeypatch) -> None:
    _rows, _clients_map, _trace, _calls, _sealed, result = _run(monkeypatch)
    forged_ledger = deepcopy(result["ledger"])
    trial_id = next(iter(forged_ledger["trials"]))
    cue = forged_ledger["trials"][trial_id]["cues"][0]
    cue["claim"] = "degraded" if cue["claim"] == "available" else "available"
    checks = controller.verify_sealed_quartet(forged_ledger, result["reveal"])
    assert checks["valid"] is False
    assert checks["ledger_hash"] is False or checks["trial_records_valid"] is False


def test_tampered_reveal_key_fails_verification(monkeypatch) -> None:
    _rows, _clients_map, _trace, _calls, _sealed, result = _run(monkeypatch)
    forged_reveal = deepcopy(result["reveal"])
    forged_reveal["core_key"] = "00" * 32
    checks = controller.verify_sealed_quartet(result["ledger"], forged_reveal)
    assert checks["valid"] is False
    assert checks["commitment"] is False or checks["realization"] is False


def test_baseline_seal_failure_prevents_randomization(monkeypatch) -> None:
    rows = _core_rows()
    clients, _trace = _clients(rows)
    key_called = False

    def forbidden_keygen(_size: int) -> bytes:
        nonlocal key_called
        key_called = True
        raise AssertionError("key generation must remain behind baseline seal")

    monkeypatch.setattr(controller.secrets, "token_bytes", forbidden_keygen)
    with pytest.raises(RuntimeError, match="baseline immutable store failure"):
        controller.run_quartet(
            clients,
            rows,
            subject_login=SUBJECT,
            study_binding_hash=STUDY_BINDING,
            design_hash=DESIGN_HASH,
            baseline_seal_callback=lambda _ledger: (_ for _ in ()).throw(
                RuntimeError("baseline immutable store failure")
            ),
            seal_callback=lambda _ledger: "never",
            seal_envelope_callback=lambda _envelope: "git:envelope-test",
            timeout_seconds=0.1,
        )
    assert key_called is False
    assert all(
        client._first(controller.P0_SEAL_PREFIX) is None
        for client in clients.values()
    )


def test_unstructured_subject_comment_blocks_randomization(monkeypatch) -> None:
    rows = _core_rows()
    bad_id = rows[2]["trial_id"]
    clients, _trace = _clients(rows, unexpected_after_p0_trial=bad_id)
    key_called = False

    def forbidden_keygen(_size: int) -> bytes:
        nonlocal key_called
        key_called = True
        raise AssertionError("unexpected subject commentary must block randomization")

    monkeypatch.setattr(controller.secrets, "token_bytes", forbidden_keygen)
    with pytest.raises(ValueError, match="pre-randomization subject protocol violation"):
        controller.run_quartet(
            clients,
            rows,
            subject_login=SUBJECT,
            study_binding_hash=STUDY_BINDING,
            design_hash=DESIGN_HASH,
            baseline_seal_callback=lambda _ledger: "never",
            seal_callback=lambda _ledger: "never",
            seal_envelope_callback=lambda _envelope: "git:envelope-test",
            timeout_seconds=0.1,
        )
    assert key_called is False
    assert all(client._first(controller.P0_SEAL_PREFIX) is None for client in clients.values())


def test_verifier_failure_after_seal_blocks_key_reveal(monkeypatch) -> None:
    rows = _core_rows()
    clients, _trace = _clients(rows)
    monkeypatch.setattr(
        controller.secrets, "token_bytes", lambda _size: bytes.fromhex("45" * 32)
    )
    monkeypatch.setattr(
        controller,
        "verify_sealed_quartet",
        lambda _ledger, _reveal: {"forced_failure": False, "valid": False},
    )
    with pytest.raises(RuntimeError, match="sealed quartet verification failed"):
        controller.run_quartet(
            clients,
            rows,
            subject_login=SUBJECT,
            study_binding_hash=STUDY_BINDING,
            design_hash=DESIGN_HASH,
            baseline_seal_callback=lambda _ledger: "git:baseline-test",
            seal_callback=lambda _ledger: "git:final-test",
            seal_envelope_callback=lambda _envelope: "git:envelope-test",
            timeout_seconds=0.1,
        )
    assert all(client._first(controller.SEAL_PREFIX) is not None for client in clients.values())
    assert all(client._first(controller.REVEAL_PREFIX) is None for client in clients.values())


def test_seal_callbacks_cannot_mutate_controller_state(monkeypatch) -> None:
    rows = _core_rows()
    clients, _trace = _clients(rows)
    monkeypatch.setattr(
        controller.secrets, "token_bytes", lambda _size: bytes.fromhex("45" * 32)
    )

    def destructive_baseline(value: dict) -> str:
        value.clear()
        return "git:baseline-isolated"

    def destructive_final(value: dict) -> str:
        value.clear()
        return "git:final-isolated"

    result = controller.run_quartet(
        clients,
        rows,
        subject_login=SUBJECT,
        study_binding_hash=STUDY_BINDING,
        design_hash=DESIGN_HASH,
        baseline_seal_callback=destructive_baseline,
        seal_callback=destructive_final,
        seal_envelope_callback=lambda _envelope: "git:envelope-test",
        timeout_seconds=0.1,
    )
    assert result["verification"]["valid"] is True
    assert result["ledger"]["trials"]
    assert result["reveal"]["realization"]


def test_design_hash_must_match_full_frozen_matrix_before_ready() -> None:
    rows = _core_rows()
    clients, trace = _clients(rows)
    with pytest.raises(ValueError, match="frozen 64-row design"):
        controller.run_quartet(
            clients,
            rows,
            subject_login=SUBJECT,
            study_binding_hash=STUDY_BINDING,
            design_hash="b" * 64,
            baseline_seal_callback=lambda _ledger: "never",
            seal_callback=lambda _ledger: "never",
            seal_envelope_callback=lambda _envelope: "git:envelope-test",
            timeout_seconds=0.1,
        )
    assert trace.events == []


def test_trial_variant_swap_is_rejected_against_frozen_design() -> None:
    rows = deepcopy(_core_rows())
    rows[0]["trial_id"], rows[1]["trial_id"] = rows[1]["trial_id"], rows[0]["trial_id"]
    with pytest.raises(ValueError, match="frozen design"):
        controller.validate_core_rows(rows)


def test_randomization_is_domain_separated_by_core_study_and_design() -> None:
    key = bytes.fromhex("45" * 32)
    base = controller.derive_core_realization(
        key,
        core_id="MOSAIC-CORE-01",
        study_binding_hash=STUDY_BINDING,
        design_hash=DESIGN_HASH,
        reliability_x=0.8,
        reliability_y=0.65,
    )
    other_core = controller.derive_core_realization(
        key,
        core_id="MOSAIC-CORE-02",
        study_binding_hash=STUDY_BINDING,
        design_hash=DESIGN_HASH,
        reliability_x=0.8,
        reliability_y=0.65,
    )
    other_study = controller.derive_core_realization(
        key,
        core_id="MOSAIC-CORE-01",
        study_binding_hash="c" * 64,
        design_hash=DESIGN_HASH,
        reliability_x=0.8,
        reliability_y=0.65,
    )
    assert base["payload"] != other_core["payload"]
    assert base["payload"] != other_study["payload"]


def test_commitment_binds_context_and_baseline_seal() -> None:
    key = bytes.fromhex("45" * 32)
    kwargs = {
        "core_id": "MOSAIC-CORE-01",
        "study_binding_hash": STUDY_BINDING,
        "design_hash": DESIGN_HASH,
        "p0_bundle_hash": "1" * 64,
        "baseline_hash": "2" * 64,
        "baseline_seal_reference": "git:baseline-a",
    }
    base = controller.make_quartet_commitment(key, **kwargs)
    assert base != controller.make_quartet_commitment(
        key, **{**kwargs, "core_id": "MOSAIC-CORE-02"}
    )
    assert base != controller.make_quartet_commitment(
        key, **{**kwargs, "study_binding_hash": "c" * 64}
    )
    assert base != controller.make_quartet_commitment(
        key, **{**kwargs, "baseline_seal_reference": "git:baseline-b"}
    )


def test_baseline_seal_reference_substitution_breaks_commitment(monkeypatch) -> None:
    _rows, _clients_map, _trace, _calls, _sealed, result = _run(monkeypatch)
    forged_ledger = deepcopy(result["ledger"])
    forged_reveal = deepcopy(result["reveal"])
    forged_ledger["baseline_seal_reference"] = "git:substituted-baseline"
    forged_reveal["baseline_seal_reference"] = "git:substituted-baseline"
    forged_reveal["ledger_hash"] = canonical_hash(forged_ledger)
    checks = controller.verify_sealed_quartet(forged_ledger, forged_reveal)
    assert checks["valid"] is False
    assert checks["commitment"] is False


def test_seal_envelope_failure_prevents_public_seal_and_reveal(monkeypatch) -> None:
    rows = _core_rows()
    clients, _trace = _clients(rows)
    monkeypatch.setattr(
        controller.secrets, "token_bytes", lambda _size: bytes.fromhex("45" * 32)
    )
    ledger_sealed = False

    def ledger_seal(_ledger: dict) -> str:
        nonlocal ledger_sealed
        ledger_sealed = True
        return "git:ledger-sealed"

    with pytest.raises(RuntimeError, match="envelope store failure"):
        controller.run_quartet(
            clients,
            rows,
            subject_login=SUBJECT,
            study_binding_hash=STUDY_BINDING,
            design_hash=DESIGN_HASH,
            baseline_seal_callback=lambda _ledger: "git:baseline-test",
            seal_callback=ledger_seal,
            seal_envelope_callback=lambda _envelope: (_ for _ in ()).throw(
                RuntimeError("synthetic envelope store failure")
            ),
            timeout_seconds=0.1,
        )
    assert ledger_sealed is True
    assert all(client._first(controller.SEAL_PREFIX) is None for client in clients.values())
    assert all(client._first(controller.REVEAL_PREFIX) is None for client in clients.values())


def test_seal_envelope_hash_detects_reveal_substitution(monkeypatch) -> None:
    _rows, _clients_map, _trace, _calls, _sealed, result = _run(monkeypatch)
    forged = deepcopy(result["reveal"])
    forged["seal_envelope"]["ledger_seal_reference"] = "git:other-ledger"
    checks = controller.verify_sealed_quartet(result["ledger"], forged)
    assert checks["valid"] is False
    assert checks["seal_envelope"] is False or checks["seal_envelope_hash"] is False
