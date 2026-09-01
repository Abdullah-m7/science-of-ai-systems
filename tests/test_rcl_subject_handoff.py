from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from sais.rcl_pc_analysis import load_study_spec
from sais.rcl_registry import load_registry, transition_trial
from sais.rcl_subject_handoff import build_handoff

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json"
REGISTRY = ROOT / "experiments/007-rcl-pc-execution-readiness/TRIAL_REGISTRY.json"


def _inputs():
    spec = load_study_spec(MANIFEST, root=ROOT)
    registry = load_registry(REGISTRY)
    return spec, registry


def test_handoff_uses_exact_v2_product_and_issue() -> None:
    spec, registry = _inputs()
    packet = build_handoff(registry, spec, "PC-RCL-001", root=ROOT)
    assert "PC-RCL-001" in packet
    assert "https://github.com/Abdullah-m7/science-of-ai-systems/issues/18" in packet
    assert "GPT-5.6 Sol" in packet
    assert "ChatGPT/1.2026.230; iOS 26.6.1" in packet
    assert "Expected memory state: `enabled`" in packet
    assert "Frozen Subject Instructions" in packet
    assert "issues/19" not in packet


def test_handoff_is_byte_deterministic() -> None:
    spec, registry = _inputs()
    first = build_handoff(registry, spec, "PC-RCL-001", root=ROOT).encode()
    second = build_handoff(registry, spec, "PC-RCL-001", root=ROOT).encode()
    assert first == second
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


def test_handoff_rejects_started_identifier() -> None:
    spec, registry = _inputs()
    started = transition_trial(
        registry,
        spec,
        "PC-RCL-001",
        "DISPATCH_ATTEMPTED",
        fields={"controller_run_id": 12345},
    )
    with pytest.raises(ValueError, match="requires ISSUE_CREATED"):
        build_handoff(started, spec, "PC-RCL-001", root=ROOT)


def test_handoff_rejects_unknown_identifier() -> None:
    spec, registry = _inputs()
    with pytest.raises(ValueError, match="not uniquely registered"):
        build_handoff(registry, spec, "PC-RCL-999", root=ROOT)


def test_handoff_rejects_tampered_subject_instruction_bytes(tmp_path: Path) -> None:
    spec, registry = _inputs()
    config_source = ROOT / spec.config_path
    instruction_source = ROOT / spec.subject_instruction_path
    config_target = tmp_path / spec.config_path
    instruction_target = tmp_path / spec.subject_instruction_path
    config_target.parent.mkdir(parents=True, exist_ok=True)
    instruction_target.parent.mkdir(parents=True, exist_ok=True)
    config_target.write_bytes(config_source.read_bytes())
    instruction_target.write_bytes(instruction_source.read_bytes() + b"\nforged\n")
    with pytest.raises(ValueError, match="subject instructions"):
        build_handoff(registry, spec, "PC-RCL-001", root=tmp_path)


def test_static_handoff_manifest_precommits_all_32_packets() -> None:
    import json

    spec, registry = _inputs()
    manifest_path = ROOT / "experiments/008b-subject-isolation/HANDOFF_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "SMI-CP/RCL-PC/HANDOFFS/1"
    assert manifest["prepared_before_first_dispatch"] is True
    assert manifest["freeze_tag"] == spec.freeze_tag
    assert manifest["block_id"] == spec.block_id
    assert manifest["included_trials_started"] == 0
    assert manifest["handoff_count"] == 32
    assert [row["trial_id"] for row in manifest["handoffs"]] == list(spec.expected_ids)
    registry_hash = hashlib.sha256(REGISTRY.read_bytes()).hexdigest()
    assert manifest["registry_sha256"] == registry_hash

    by_trial = {row["trial_id"]: row for row in registry["trials"]}
    for row in manifest["handoffs"]:
        trial_id = row["trial_id"]
        path = ROOT / row["path"]
        packet = path.read_bytes()
        expected = build_handoff(registry, spec, trial_id, root=ROOT).encode()
        assert packet == expected
        assert hashlib.sha256(packet).hexdigest() == row["sha256"]
        assert row["issue_number"] == by_trial[trial_id]["issue_number"]
        assert row["issue_url"] == by_trial[trial_id]["issue_url"]
        assert spec.expected_binding_hash not in packet.decode("utf-8")
