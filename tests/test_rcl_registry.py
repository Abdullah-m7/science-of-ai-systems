from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from sais.rcl_pc_analysis import load_study_spec
from sais.rcl_registry import (
    issue_title,
    new_registry,
    planned_issues,
    transition_trial,
    validate_registry,
)

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json"


def _spec():
    return load_study_spec(MANIFEST, root=ROOT)


def test_new_registry_has_exact_frozen_denominator() -> None:
    spec = _spec()
    registry = new_registry(
        spec,
        freeze_commit="f" * 40,
        created_at_utc="2026-08-31T09:00:00Z",
    )
    assert [item["trial_id"] for item in registry["trials"]] == list(
        spec.expected_ids
    )
    assert {item["status"] for item in registry["trials"]} == {"NOT_CREATED"}
    assert registry["included_trials_started"] == 0
    assert registry["controller_commit"] == spec.controller_code_sha
    assert registry["configuration_path"] == spec.config_path
    assert validate_registry(registry, spec)


def test_issue_creation_is_not_a_trial_start() -> None:
    spec = _spec()
    registry = new_registry(spec, freeze_commit="f" * 40)
    updated = transition_trial(
        registry,
        spec,
        "PC-RCL-001",
        "ISSUE_CREATED",
        at_utc="2026-08-31T09:01:00Z",
        fields={
            "issue_number": 101,
            "issue_url": (
                "https://github.com/Abdullah-m7/"
                "science-of-ai-systems/issues/101"
            ),
        },
    )
    assert updated["included_trials_started"] == 0
    assert updated["events"][0]["to_status"] == "ISSUE_CREATED"


def test_dispatch_attempt_consumes_identifier() -> None:
    spec = _spec()
    registry = new_registry(spec, freeze_commit="f" * 40)
    registry = transition_trial(
        registry,
        spec,
        "PC-RCL-001",
        "ISSUE_CREATED",
        fields={
            "issue_number": 101,
            "issue_url": (
                "https://github.com/Abdullah-m7/"
                "science-of-ai-systems/issues/101"
            ),
        },
    )
    registry = transition_trial(
        registry,
        spec,
        "PC-RCL-001",
        "DISPATCH_ATTEMPTED",
        fields={"controller_run_id": 999},
    )
    assert registry["included_trials_started"] == 1
    with pytest.raises(ValueError, match="forbidden transition"):
        transition_trial(
            registry,
            spec,
            "PC-RCL-001",
            "ISSUE_CREATED",
        )


def test_registry_rejects_hidden_assignment_material() -> None:
    spec = _spec()
    registry = new_registry(spec, freeze_commit="f" * 40)
    registry["trials"][0]["condition"] = "available"
    with pytest.raises(ValueError, match="trial_records_valid"):
        validate_registry(registry, spec)
    clean = new_registry(spec, freeze_commit="f" * 40)
    with pytest.raises(ValueError, match="hidden assignment"):
        transition_trial(
            clean,
            spec,
            "PC-RCL-001",
            "ISSUE_CREATED",
            fields={"condition": "available"},
        )


def test_duplicate_issue_number_is_rejected() -> None:
    spec = _spec()
    registry = new_registry(spec, freeze_commit="f" * 40)
    for trial_id in ("PC-RCL-001", "PC-RCL-002"):
        registry = transition_trial(
            registry,
            spec,
            trial_id,
            "ISSUE_CREATED",
            fields={
                "issue_number": 101 if trial_id.endswith("001") else 102,
                "issue_url": (
                    "https://github.com/Abdullah-m7/"
                    f"science-of-ai-systems/issues/{101 if trial_id.endswith('001') else 102}"
                ),
            },
        )
    forged = deepcopy(registry)
    forged["trials"][1]["issue_number"] = 101
    forged["trials"][1]["issue_url"] = (
        "https://github.com/Abdullah-m7/science-of-ai-systems/issues/101"
    )
    with pytest.raises(ValueError, match="issue_numbers_unique"):
        validate_registry(forged, spec)


def test_issue_plan_is_deterministic_and_assignment_free() -> None:
    spec = _spec()
    registry = new_registry(spec, freeze_commit="f" * 40)
    first = planned_issues(registry, spec)
    second = planned_issues(registry, spec)
    assert first == second
    assert len(first) == 32
    assert first[0]["title"] == issue_title("PC-RCL-001")
    assert "NOT STARTED" in first[0]["body"]
    assert registry["configuration_binding_hash"] in first[0]["body"]
    assert "condition\":" not in first[0]["body"]
    assert "legibility\":" not in first[0]["body"]


def test_static_execution_registry_is_valid_and_unstarted() -> None:
    spec = _spec()
    path = ROOT / (
        "experiments/007-rcl-pc-execution-readiness/TRIAL_REGISTRY.json"
    )
    import json

    registry = json.loads(path.read_text(encoding="utf-8"))
    validate_registry(registry, spec)
    assert registry["included_trials_started"] == 0
    assert all(item["status"] == "ISSUE_CREATED" for item in registry["trials"])
    numbers = [item["issue_number"] for item in registry["trials"]]
    assert len(numbers) == len(set(numbers)) == 32
    assert numbers[0] == 18
    assert numbers[-1] == 49


def test_event_history_replay_detects_tampering() -> None:
    spec = _spec()
    registry = new_registry(spec, freeze_commit="f" * 40)
    registry = transition_trial(
        registry,
        spec,
        "PC-RCL-001",
        "ISSUE_CREATED",
        fields={
            "issue_number": 101,
            "issue_url": (
                "https://github.com/Abdullah-m7/"
                "science-of-ai-systems/issues/101"
            ),
        },
    )
    forged = deepcopy(registry)
    forged["events"][0]["from_status"] = "ISSUE_CREATED"
    with pytest.raises(ValueError, match="event_replay_valid"):
        validate_registry(forged, spec)


def test_issue_url_must_match_frozen_repository() -> None:
    spec = _spec()
    registry = new_registry(spec, freeze_commit="f" * 40)
    forged = deepcopy(registry)
    forged["trials"][0].update({
        "status": "ISSUE_CREATED",
        "issue_number": 101,
        "issue_url": "https://github.com/other/repo/issues/101",
        "last_transition_at_utc": "2026-09-01T15:30:00Z",
    })
    with pytest.raises(ValueError, match="trial_records_valid"):
        validate_registry(forged, spec)


def test_registry_rejects_controller_or_config_anchor_tamper() -> None:
    spec = _spec()
    registry = new_registry(spec, freeze_commit="f" * 40)
    forged = deepcopy(registry)
    forged["controller_commit"] = "0" * 40
    with pytest.raises(ValueError, match="controller_commit"):
        validate_registry(forged, spec)
    forged = deepcopy(registry)
    forged["configuration_path"] = "other/CONFIG.json"
    with pytest.raises(ValueError, match="configuration_path"):
        validate_registry(forged, spec)
