from __future__ import annotations

from pathlib import Path

import pytest

import sais.rcl_issue_provision as provisioner
from sais.rcl_pc_analysis import load_study_spec
from sais.rcl_registry import (
    issue_title,
    load_registry,
    new_registry,
    render_issue_body,
    save_registry,
    validate_registry,
)

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json"


def _registry_file(tmp_path: Path):
    spec = load_study_spec(MANIFEST, root=ROOT)
    registry = new_registry(spec, freeze_commit="f" * 40)
    path = tmp_path / "registry.json"
    save_registry(path, registry)
    return spec, path


def test_dry_run_plans_all_issues_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, path = _registry_file(tmp_path)
    before = path.read_bytes()
    monkeypatch.setattr(provisioner, "_verify_local_anchor", lambda registry: None)
    report = provisioner.provision(
        path,
        MANIFEST,
        apply=False,
        confirmation=None,
    )
    assert report["mode"] == "DRY_RUN"
    assert report["planned_count"] == 32
    assert report["included_trials_started"] == 0
    assert path.read_bytes() == before


def test_apply_creates_all_surfaces_but_starts_no_trial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, path = _registry_file(tmp_path)
    counter = iter(range(201, 233))
    monkeypatch.setattr(provisioner, "_verify_local_anchor", lambda registry: None)
    monkeypatch.setattr(provisioner, "_gh", lambda executable: "gh")
    monkeypatch.setattr(provisioner, "_run", lambda command: "")
    monkeypatch.setattr(provisioner, "_existing_issues", lambda gh, repo: [])

    def fake_create(gh: str, repository: str, title: str, body: str):
        number = next(counter)
        assert "NOT STARTED" in body
        return number, f"https://github.com/{repository}/issues/{number}"

    monkeypatch.setattr(provisioner, "_create_issue", fake_create)
    report = provisioner.provision(
        path,
        MANIFEST,
        apply=True,
        confirmation=spec.freeze_tag,
    )
    registry = load_registry(path)
    validate_registry(registry, spec)
    assert report["created"] == 32
    assert report["reconciled"] == 0
    assert report["included_trials_started"] == 0
    assert registry["included_trials_started"] == 0
    assert all(item["status"] == "ISSUE_CREATED" for item in registry["trials"])
    assert len(registry["events"]) == 32


def test_existing_exact_surface_is_reconciled_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, path = _registry_file(tmp_path)
    registry = load_registry(path)
    first = registry["trials"][0]
    existing = {
        "number": 301,
        "title": issue_title(first["trial_id"]),
        "url": f"https://github.com/{spec.repository}/issues/301",
        "body": render_issue_body(first, registry),
        "comments": [],
    }
    counter = iter(range(302, 333))
    monkeypatch.setattr(provisioner, "_verify_local_anchor", lambda value: None)
    monkeypatch.setattr(provisioner, "_gh", lambda executable: "gh")
    monkeypatch.setattr(provisioner, "_run", lambda command: "")
    monkeypatch.setattr(
        provisioner,
        "_existing_issues",
        lambda gh, repo: [existing],
    )
    monkeypatch.setattr(
        provisioner,
        "_create_issue",
        lambda gh, repository, title, body: (
            (number := next(counter)),
            f"https://github.com/{repository}/issues/{number}",
        ),
    )
    report = provisioner.provision(
        path,
        MANIFEST,
        apply=True,
        confirmation=spec.freeze_tag,
    )
    assert report["reconciled"] == 1
    assert report["created"] == 31
    assert report["included_trials_started"] == 0
    assert load_registry(path)["trials"][0]["issue_number"] == 301


def test_wrong_confirmation_fails_before_github(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, path = _registry_file(tmp_path)
    monkeypatch.setattr(provisioner, "_verify_local_anchor", lambda registry: None)
    with pytest.raises(RuntimeError, match="confirm-freeze-tag"):
        provisioner.provision(
            path,
            MANIFEST,
            apply=True,
            confirmation="wrong-tag",
        )


def test_existing_surface_with_comment_is_rejected() -> None:
    spec = load_study_spec(MANIFEST, root=ROOT)
    registry = new_registry(spec, freeze_commit="f" * 40)
    first = registry["trials"][0]
    issue = {
        "number": 401,
        "title": issue_title(first["trial_id"]),
        "url": f"https://github.com/{spec.repository}/issues/401",
        "body": render_issue_body(first, registry),
        "comments": [{"body": "manual contamination"}],
    }
    with pytest.raises(RuntimeError, match="unexpected comments"):
        provisioner._validate_existing_issue(issue, first["trial_id"], registry)


def test_unexpected_trial_marker_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, path = _registry_file(tmp_path)
    monkeypatch.setattr(provisioner, "_verify_local_anchor", lambda registry: None)
    monkeypatch.setattr(provisioner, "_gh", lambda executable: "gh")
    monkeypatch.setattr(provisioner, "_run", lambda command: "")
    monkeypatch.setattr(
        provisioner,
        "_existing_issues",
        lambda gh, repo: [{
            "number": 999,
            "title": "unexpected",
            "url": f"https://github.com/{spec.repository}/issues/999",
            "body": "<!-- sais-rcl-pc-trial:PC-RCL-999 -->",
            "comments": [],
        }],
    )
    with pytest.raises(RuntimeError, match="unexpected RCL-PC issue markers"):
        provisioner.provision(
            path,
            MANIFEST,
            apply=True,
            confirmation=spec.freeze_tag,
        )


def test_provisioner_refuses_after_trial_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sais.rcl_registry import transition_trial

    spec, path = _registry_file(tmp_path)
    registry = load_registry(path)
    registry = transition_trial(
        registry,
        spec,
        "PC-RCL-001",
        "ISSUE_CREATED",
        fields={
            "issue_number": 501,
            "issue_url": f"https://github.com/{spec.repository}/issues/501",
        },
    )
    registry = transition_trial(
        registry,
        spec,
        "PC-RCL-001",
        "DISPATCH_ATTEMPTED",
        fields={"controller_run_id": 77},
    )
    save_registry(path, registry)
    monkeypatch.setattr(provisioner, "_verify_local_anchor", lambda value: None)
    with pytest.raises(RuntimeError, match="forbidden after any trial start"):
        provisioner.provision(path, MANIFEST, apply=False)
