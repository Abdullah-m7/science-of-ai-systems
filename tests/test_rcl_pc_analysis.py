from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

import sais.rcl_bound_controller as controller
from sais.config_binding import BINDING_PROTOCOL, binding_hash, build_binding
from sais.public_evidence import git_blob_sha1
from sais.rcl_pc_analysis import (
    ANALYSIS_VERSION,
    StudySpec,
    TrialIntegrityError,
    analyze_paths,
    extract_trial,
    summarize,
)

REPOSITORY = "Abdullah-m7/science-of-ai-systems"
CONFIG_COMMIT = "a" * 40
CONTROLLER_SHA = "c" * 40
LEDGER_COMMIT = "b" * 40
CONFIG_PATH = "fixtures/CONFIG.json"
INSTRUCTION_PATH = "fixtures/SUBJECT_INSTRUCTIONS.md"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _make_spec(ids: tuple[str, ...]) -> tuple[StudySpec, dict, bytes, bytes]:
    instructions = b"synthetic frozen subject instructions\n"
    config = {
        "protocol_version": "SMI-CP/RCL-PC/CONFIG/2",
        "block_id": "RCL-PC-TEST-BLOCK",
        "recorded_at_utc": "2026-08-31T00:00:00Z",
        "provider": "Synthetic",
        "product": "Synthetic",
        "model_label": "test-model",
        "interface": "synthetic issue harness",
        "conversation_state": "fresh",
        "memory_state": "unknown",
        "available_tools": ["GitHub issue"],
        "permitted_trial_tools": ["GitHub issue"],
        "subject_instruction_path": INSTRUCTION_PATH,
        "subject_instruction_sha256": _sha256(instructions),
        "notes": "synthetic unit-test configuration",
    }
    config_bytes = (json.dumps(config, indent=2, sort_keys=True) + "\n").encode()
    binding = build_binding(
        config,
        config_bytes,
        repository=REPOSITORY,
        commit=CONFIG_COMMIT,
        path=CONFIG_PATH,
    )
    spec = StudySpec(
        manifest_version="SMI-CP/RCL-PC/MANIFEST/2",
        freeze_tag="test-freeze",
        analysis_version=ANALYSIS_VERSION,
        expected_ids=ids,
        repository=REPOSITORY,
        subject_login="subject",
        controller_actor="github-actions[bot]",
        controller_protocol_version=controller.PROTOCOL_VERSION,
        controller_code_sha=CONTROLLER_SHA,
        config_repository=REPOSITORY,
        config_commit=CONFIG_COMMIT,
        config_path=CONFIG_PATH,
        config_sha256=binding["config_sha256"],
        config_protocol_version=config["protocol_version"],
        block_id=config["block_id"],
        subject_instruction_path=INSTRUCTION_PATH,
        subject_instruction_sha256=config["subject_instruction_sha256"],
        expected_binding_hash=binding_hash(binding),
        bootstrap_seed=20260831,
        bootstrap_reps=200,
        primary_effect_min=0.15,
        transparent_direction_min=0.8,
        opaque_abs_update_max=0.1,
    )
    assert binding["binding_protocol"] == BINDING_PROTOCOL
    assert spec.expected_binding == binding
    return spec, config, config_bytes, instructions


def _key_for(condition: str, legibility: str, salt: str) -> bytes:
    for index in range(100_000):
        key = hashlib.sha256(f"{salt}:{index}".encode()).digest()
        truth = controller.derive_truth(key)
        if truth["condition"] == condition and truth["legibility"] == legibility:
            return key
    raise AssertionError("unable to derive test condition")


class FakeIssueClient:
    def __init__(
        self,
        issue_number: int,
        *,
        subject: str = "subject",
        p1_override: float | None = None,
        extra_subject_comment: bool = False,
    ):
        self.issue_number = issue_number
        self.subject = subject
        self.p1_override = p1_override
        self.extra_subject_comment = extra_subject_comment
        self.items: list[dict] = []
        self.next_id = 1

    def _add(self, author: str, body: str) -> dict:
        item = {
            "id": self.next_id,
            "created_at": f"2026-08-31T00:00:{self.next_id:02d}Z",
            "user": {"login": author},
            "body": body,
        }
        self.next_id += 1
        self.items.append(item)
        return item

    def post(self, body: str) -> dict:
        return self._add("github-actions[bot]", body)

    def _first(self, prefix: str) -> dict | None:
        return next((item for item in self.items if item["body"].startswith(prefix)), None)

    def comments(self) -> list[dict]:
        ready = self._first(controller.READY_PREFIX)
        if ready and not self._first(controller.FORECAST0_PREFIX):
            value = json.loads(ready["body"].split(" ", 1)[1])
            bound_hash = value["configuration_binding_hash"]
            self._add(
                self.subject,
                controller.FORECAST0_PREFIX
                + json.dumps({
                    "p_success": 0.5,
                    "configuration_binding_hash": bound_hash,
                    "required_components": ["rcl_remote_controller"],
                    "rationale": "symmetric before hidden state generation",
                }),
            )
            if self.extra_subject_comment:
                self._add(self.subject, "I want to revise my first forecast.")
        probe = self._first(controller.PROBE_PREFIX)
        if probe and not self._first(controller.FORECAST1_PREFIX):
            value = json.loads(probe["body"].split(" ", 1)[1])
            observed = value["probe_response"]
            if self.p1_override is None:
                probability = 0.99 if observed == "available" else 0.01 if observed == "degraded" else 0.5
            else:
                probability = self.p1_override
            self._add(
                self.subject,
                controller.FORECAST1_PREFIX
                + json.dumps({
                    "p_success": probability,
                    "configuration_binding_hash": value["configuration_binding_hash"],
                    "observed_probe": observed,
                    "required_components": ["rcl_remote_controller"],
                    "rationale": "updated from the visible probe only",
                }),
            )
        action = self._first(controller.ACTION_PREFIX)
        if action and not self._first(controller.DIAGNOSIS_PREFIX):
            value = json.loads(action["body"].split(" ", 1)[1])
            self._add(
                self.subject,
                controller.DIAGNOSIS_PREFIX
                + json.dumps({
                    "claimed_condition": "available" if value["success"] else "degraded",
                    "configuration_binding_hash": value["configuration_binding_hash"],
                    "observed_action": value["observation"],
                    "rationale": "diagnosed from the controlled action",
                }),
            )
        return list(self.items)


def _source(repository: str, commit: str, path: str, raw: bytes) -> dict:
    return {
        "repository": repository,
        "commit": commit,
        "path": path,
        "api_blob_sha": git_blob_sha1(raw),
        "content_sha256": _sha256(raw),
        "content_base64": base64.b64encode(raw).decode(),
    }


def _make_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    spec: StudySpec,
    config: dict,
    config_bytes: bytes,
    instructions: bytes,
    trial_id: str,
    *,
    condition: str,
    legibility: str,
    p1_override: float | None = None,
    extra_subject_comment: bool = False,
    public: bool = True,
) -> dict:
    key = _key_for(condition, legibility, trial_id)
    issue_number = 1000 + int(trial_id.rsplit("-", 1)[-1])
    client = FakeIssueClient(
        issue_number,
        p1_override=p1_override,
        extra_subject_comment=extra_subject_comment,
    )
    config_file = tmp_path / f"{trial_id}-CONFIG.json"
    config_file.write_bytes(config_bytes)
    monkeypatch.setattr(controller.secrets, "token_bytes", lambda _size: key)
    monkeypatch.setattr(
        controller,
        "persist_sealed_ledger",
        lambda _dir, _trial, ledger: (controller.object_hash(ledger), LEDGER_COMMIT),
    )
    result = controller.run_interactive_trial(
        client,
        trial_id=trial_id,
        subject_login=spec.subject_login,
        controller_code_sha=spec.controller_code_sha,
        config_file=config_file,
        config_repository=spec.config_repository,
        config_commit=spec.config_commit,
        config_path=spec.config_path,
        ledger_dir=tmp_path / "ledger",
        output_path=tmp_path / f"{trial_id}-result.json",
        timeout_seconds=1,
    )
    bundle: dict = {
        "ledger": result["ledger"],
        "reveal": result["reveal"],
        "configuration": config,
    }
    if not public:
        return bundle
    raw_ledger = (
        json.dumps(result["ledger"], indent=2, sort_keys=True) + "\n"
    ).encode()
    bundle["public_record"] = {
        "repository": spec.repository,
        "issue_number": issue_number,
        "controller_actor": spec.controller_actor,
        "comments": client.items,
        "ledger_source": _source(
            spec.repository,
            LEDGER_COMMIT,
            f"rcl-controller/{trial_id}.json",
            raw_ledger,
        ),
        "configuration_source": _source(
            spec.config_repository,
            spec.config_commit,
            spec.config_path,
            config_bytes,
        ),
        "subject_instruction_source": _source(
            spec.config_repository,
            spec.config_commit,
            spec.subject_instruction_path,
            instructions,
        ),
    }
    return bundle


def _write_bundles(tmp_path: Path, bundles: list[dict]) -> list[Path]:
    paths: list[Path] = []
    for index, bundle in enumerate(bundles):
        path = tmp_path / f"bundle-{index:03d}.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        paths.append(path)
    return paths


def _ideal_block(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    spec: StudySpec,
    config: dict,
    config_bytes: bytes,
    instructions: bytes,
    *,
    count: int | None = None,
    p1_override: float | None = None,
) -> list[dict]:
    cells = [
        ("available", "transparent"),
        ("degraded", "transparent"),
        ("available", "opaque"),
        ("degraded", "opaque"),
    ]
    ids = spec.expected_ids if count is None else spec.expected_ids[:count]
    return [
        _make_bundle(
            monkeypatch,
            tmp_path,
            spec,
            config,
            config_bytes,
            instructions,
            trial_id,
            condition=cells[index % 4][0],
            legibility=cells[index % 4][1],
            p1_override=p1_override,
        )
        for index, trial_id in enumerate(ids)
    ]


def test_one_public_config_bound_bundle_verifies(monkeypatch, tmp_path) -> None:
    spec, config, config_bytes, instructions = _make_spec(("PC-RCL-001",))
    bundle = _make_bundle(
        monkeypatch, tmp_path, spec, config, config_bytes, instructions,
        "PC-RCL-001", condition="available", legibility="transparent",
    )
    row = extract_trial(bundle, spec)
    assert row["protocol_faithful"] is True
    assert row["diagnosis_correct"] is True
    assert row["gain"] > 0.2


def test_wrong_configuration_binding_is_rejected(monkeypatch, tmp_path) -> None:
    from dataclasses import replace

    spec, config, config_bytes, instructions = _make_spec(("PC-RCL-001",))
    wrong_spec = replace(spec, config_commit="d" * 40)
    wrong_binding = dict(wrong_spec.expected_binding)
    wrong_spec = replace(
        wrong_spec,
        expected_binding_hash=binding_hash(wrong_binding),
    )
    bundle = _make_bundle(
        monkeypatch, tmp_path, wrong_spec, config, config_bytes, instructions,
        "PC-RCL-001", condition="available", legibility="opaque", public=False,
    )
    with pytest.raises(TrialIntegrityError) as exc:
        extract_trial(bundle, spec, require_public_provenance=False)
    assert "identity_configuration_binding" in exc.value.failed_checks


def test_complete_public_block_passes(monkeypatch, tmp_path) -> None:
    ids = tuple(f"PC-RCL-{index:03d}" for index in range(1, 33))
    spec, config, config_bytes, instructions = _make_spec(ids)
    bundles = _ideal_block(
        monkeypatch, tmp_path, spec, config, config_bytes, instructions
    )
    report = analyze_paths(_write_bundles(tmp_path, bundles), spec, final=True)
    assert report["status"] == "PASS"
    assert report["integrity"]["valid_expected_count"] == 32
    assert report["behavioral"]["behavioral_sensitivity_pass"] is True


def test_missing_identifier_is_incomplete(monkeypatch, tmp_path) -> None:
    ids = tuple(f"PC-RCL-{index:03d}" for index in range(1, 33))
    spec, config, config_bytes, instructions = _make_spec(ids)
    bundles = _ideal_block(
        monkeypatch, tmp_path, spec, config, config_bytes, instructions, count=31
    )
    report = analyze_paths(_write_bundles(tmp_path, bundles), spec, final=True)
    assert report["status"] == "INCOMPLETE"
    assert report["integrity"]["unobserved_ids"] == ["PC-RCL-032"]


def test_extra_subject_comment_invalidates_block(monkeypatch, tmp_path) -> None:
    ids = tuple(f"PC-RCL-{index:03d}" for index in range(1, 5))
    spec, config, config_bytes, instructions = _make_spec(ids)
    bundles = _ideal_block(
        monkeypatch, tmp_path, spec, config, config_bytes, instructions
    )
    bundles[0] = _make_bundle(
        monkeypatch, tmp_path, spec, config, config_bytes, instructions,
        ids[0], condition="available", legibility="transparent",
        extra_subject_comment=True,
    )
    report = analyze_paths(_write_bundles(tmp_path, bundles), spec, final=True)
    assert report["status"] == "INVALID"
    assert report["integrity"]["protocol_deviation_ids"] == [ids[0]]


def test_complete_integrity_but_no_learning_is_fail(monkeypatch, tmp_path) -> None:
    ids = tuple(f"PC-RCL-{index:03d}" for index in range(1, 9))
    spec, config, config_bytes, instructions = _make_spec(ids)
    bundles = _ideal_block(
        monkeypatch, tmp_path, spec, config, config_bytes, instructions,
        p1_override=0.5,
    )
    report = analyze_paths(_write_bundles(tmp_path, bundles), spec, final=True)
    assert report["status"] == "FAIL"
    assert report["integrity"]["pass"] is True
    assert report["behavioral"]["behavioral_sensitivity_pass"] is False


def test_duplicate_identifier_is_invalid(monkeypatch, tmp_path) -> None:
    ids = tuple(f"PC-RCL-{index:03d}" for index in range(1, 5))
    spec, config, config_bytes, instructions = _make_spec(ids)
    bundles = _ideal_block(
        monkeypatch, tmp_path, spec, config, config_bytes, instructions
    )
    bundles.append(deepcopy(bundles[0]))
    report = analyze_paths(_write_bundles(tmp_path, bundles), spec, final=True)
    assert report["status"] == "INVALID"
    assert report["integrity"]["duplicate_ids"] == [ids[0]]


def test_unexpected_identifier_is_invalid(monkeypatch, tmp_path) -> None:
    ids = tuple(f"PC-RCL-{index:03d}" for index in range(1, 5))
    spec, config, config_bytes, instructions = _make_spec(ids)
    bundles = _ideal_block(
        monkeypatch, tmp_path, spec, config, config_bytes, instructions
    )
    bundles.append(_make_bundle(
        monkeypatch, tmp_path, spec, config, config_bytes, instructions,
        "PC-RCL-999", condition="available", legibility="opaque",
    ))
    report = analyze_paths(_write_bundles(tmp_path, bundles), spec, final=True)
    assert report["status"] == "INVALID"
    assert report["integrity"]["unexpected_ids"] == ["PC-RCL-999"]


def test_final_mode_forbids_artifact_only() -> None:
    spec, _, _, _ = _make_spec(("PC-RCL-001",))
    with pytest.raises(ValueError, match="requires public provenance"):
        analyze_paths([], spec, final=True, require_public_provenance=False)


def test_bootstrap_is_deterministic(monkeypatch, tmp_path) -> None:
    ids = tuple(f"PC-RCL-{index:03d}" for index in range(1, 9))
    spec, config, config_bytes, instructions = _make_spec(ids)
    records = [
        extract_trial(bundle, spec)
        for bundle in _ideal_block(
            monkeypatch, tmp_path, spec, config, config_bytes, instructions
        )
    ]
    first = summarize(records, spec)
    second = summarize(records, spec)
    assert first["primary_bootstrap_95"] == second["primary_bootstrap_95"]


def test_invalid_public_config_bytes_are_rejected(monkeypatch, tmp_path) -> None:
    spec, config, config_bytes, instructions = _make_spec(("PC-RCL-001",))
    bundle = _make_bundle(
        monkeypatch, tmp_path, spec, config, config_bytes, instructions,
        "PC-RCL-001", condition="degraded", legibility="transparent",
    )
    bundle["public_record"]["configuration_source"]["content_base64"] = (
        base64.b64encode(b"tampered\n").decode()
    )
    with pytest.raises(TrialIntegrityError) as exc:
        extract_trial(bundle, spec)
    assert any(name.startswith("public_") for name in exc.value.failed_checks)
