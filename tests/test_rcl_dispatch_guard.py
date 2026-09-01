from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import sais.rcl_dispatch_guard as guard
from sais.rcl_dispatch_guard import (
    append_record_event,
    assert_dispatch_order,
    discover_new_run,
    load_dispatch_plan,
    make_reservation_record,
    record_state,
    validate_dispatch_record,
    verify_issue_surface,
    verify_operator_confirmations,
)
from sais.rcl_pc_analysis import load_study_spec
from sais.rcl_registry import issue_title, load_registry, render_issue_body

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json"
REGISTRY = ROOT / "experiments/007-rcl-pc-execution-readiness/TRIAL_REGISTRY.json"
HANDOFFS = ROOT / "experiments/008b-subject-isolation/HANDOFF_MANIFEST.json"
PLAN = ROOT / "experiments/008c-dispatch-guard/DISPATCH_PLAN.json"


def _inputs():
    spec = load_study_spec(MANIFEST, root=ROOT)
    registry = load_registry(REGISTRY)
    plan = load_dispatch_plan(PLAN, spec, REGISTRY, HANDOFFS)
    return spec, registry, plan


def _reservation(plan, trial_id="PC-RCL-001"):
    return make_reservation_record(
        plan,
        trial_id,
        [3, 1, 3],
        reservation_id="a" * 64,
        reserved_at_utc="2026-09-01T16:10:00Z",
    )


def test_dispatch_plan_matches_frozen_registry_and_handoffs() -> None:
    spec, registry, plan = _inputs()
    assert plan["trial_order"] == list(spec.expected_ids)
    assert len(plan["trials"]) == 32
    assert plan["trials"][0]["issue_number"] == 18
    assert plan["trials"][-1]["issue_number"] == 49
    assert plan["registry_snapshot_sha256"] == guard.sha256_bytes(REGISTRY.read_bytes())
    assert registry["included_trials_started"] == 0


def test_plan_trial_mapping_tamper_is_rejected(tmp_path: Path) -> None:
    spec, _, _ = _inputs()
    value = json.loads(PLAN.read_text(encoding="utf-8"))
    value["trials"][0]["issue_number"] = 999
    forged = tmp_path / "plan.json"
    forged.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="trial record mismatch"):
        load_dispatch_plan(forged, spec, REGISTRY, HANDOFFS)


def test_reservation_is_assignment_free_and_deduplicates_baseline() -> None:
    _, _, plan = _inputs()
    record = _reservation(plan)
    validate_dispatch_record(record, plan)
    assert record_state(record) == "RESERVED"
    assert record["baseline_run_ids"] == [1, 3]
    rendered = json.dumps(record)
    for forbidden in ("condition", "legibility", "trial_key", "payload_hash"):
        assert f'"{forbidden}"' not in rendered


def test_record_state_machine_rejects_skip() -> None:
    _, _, plan = _inputs()
    record = _reservation(plan)
    with pytest.raises(ValueError, match="invalid dispatch state transition"):
        append_record_event(record, "REVEALED")
    record = append_record_event(
        record, "DISPATCH_SUBMITTED", at_utc="2026-09-01T16:10:01Z"
    )
    record = append_record_event(
        record,
        "RUN_IDENTIFIED",
        at_utc="2026-09-01T16:10:02Z",
        run_id=42,
    )
    record = append_record_event(
        record, "REVEALED", at_utc="2026-09-01T16:10:03Z"
    )
    validate_dispatch_record(record, plan)
    assert record_state(record) == "REVEALED"


def _run_row(run_id: int, plan: dict, *, status: str = "queued") -> dict:
    return {
        "databaseId": run_id,
        "event": "workflow_dispatch",
        "headBranch": plan["controller_tag"],
        "headSha": plan["controller_commit"],
        "createdAt": "2026-09-01T16:11:00Z",
        "status": status,
        "conclusion": None,
        "url": f"https://github.com/x/actions/runs/{run_id}",
        "displayTitle": "rcl-bound-controller",
    }


def test_run_discovery_requires_exactly_one_new_matching_run() -> None:
    _, _, plan = _inputs()
    old = _run_row(10, plan, status="completed")
    new = _run_row(11, plan)
    other = dict(_run_row(12, plan))
    other["headSha"] = "0" * 40
    identified = discover_new_run([10], [old, new, other], plan)
    assert identified["status"] == "RUN_IDENTIFIED"
    assert identified["run"]["databaseId"] == 11
    assert discover_new_run([10], [old], plan)["status"] == "RUN_UNRESOLVED"
    ambiguous = discover_new_run([10], [old, new, _run_row(13, plan)], plan)
    assert ambiguous["status"] == "RUN_AMBIGUOUS"


def test_fixed_order_requires_prior_terminal_record() -> None:
    _, _, plan = _inputs()
    assert_dispatch_order(plan, "PC-RCL-001", {})
    with pytest.raises(RuntimeError, match="predecessor"):
        assert_dispatch_order(plan, "PC-RCL-002", {})
    first = _reservation(plan)
    first = append_record_event(
        first, "DISPATCH_SUBMITTED", at_utc="2026-09-01T16:10:01Z"
    )
    first = append_record_event(
        first, "RUN_IDENTIFIED", at_utc="2026-09-01T16:10:02Z", run_id=42
    )
    with pytest.raises(RuntimeError, match="nonterminal"):
        assert_dispatch_order(plan, "PC-RCL-002", {"PC-RCL-001": first})
    first = append_record_event(
        first, "ABORTED", at_utc="2026-09-01T16:10:03Z", reason="test"
    )
    assert_dispatch_order(plan, "PC-RCL-002", {"PC-RCL-001": first})
    with pytest.raises(RuntimeError, match="already reserved"):
        assert_dispatch_order(plan, "PC-RCL-001", {"PC-RCL-001": first})


def test_issue_preflight_requires_exact_empty_surface() -> None:
    spec, registry, plan = _inputs()
    trial = plan["trials"][0]
    registered = dict(registry["trials"][0])
    registered["status"] = "NOT_CREATED"
    issue = {
        "number": trial["issue_number"],
        "url": trial["issue_url"],
        "title": issue_title(trial["trial_id"]),
        "body": render_issue_body(registered, registry),
        "state": "OPEN",
        "comments": [],
    }
    verify_issue_surface(issue, trial, registry, spec)
    contaminated = dict(issue)
    contaminated["comments"] = [{"body": "unexpected"}]
    with pytest.raises(RuntimeError, match="zero_comments"):
        verify_issue_surface(contaminated, trial, registry, spec)


def test_operator_confirmations_are_exact() -> None:
    spec, _, _ = _inputs()
    config = json.loads((ROOT / spec.config_path).read_text(encoding="utf-8"))
    verify_operator_confirmations(
        config,
        freeze=spec.freeze_tag,
        trial="PC-RCL-001",
        trial_id="PC-RCL-001",
        model="GPT-5.6 Sol",
        client="ChatGPT/1.2026.230; iOS 26.6.1",
        memory="enabled",
        customization="present",
        spec=spec,
    )
    with pytest.raises(RuntimeError, match="model"):
        verify_operator_confirmations(
            config,
            freeze=spec.freeze_tag,
            trial="PC-RCL-001",
            trial_id="PC-RCL-001",
            model="GPT-5.6 Pro",
            client="ChatGPT/1.2026.230; iOS 26.6.1",
            memory="enabled",
            customization="present",
            spec=spec,
        )


def _exact_issue(spec, registry, plan):
    trial = plan["trials"][0]
    body_trial = dict(registry["trials"][0])
    body_trial["status"] = "NOT_CREATED"
    return {
        "number": trial["issue_number"],
        "url": trial["issue_url"],
        "title": issue_title(trial["trial_id"]),
        "body": render_issue_body(body_trial, registry),
        "state": "OPEN",
        "comments": [],
    }


def test_dispatch_apply_persists_reservation_before_external_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, registry, plan = _inputs()
    order: list[str] = []
    monkeypatch.setattr(guard, "preflight", lambda **kwargs: {"ready": True})
    monkeypatch.setattr(guard, "_gh", lambda value=None: "gh")
    monkeypatch.setattr(guard, "prepare_dispatch_ledger", lambda *a, **k: tmp_path)
    monkeypatch.setattr(guard, "load_dispatch_records", lambda *a, **k: {})
    monkeypatch.setattr(guard, "_issue_from_gh", lambda *a, **k: _exact_issue(spec, registry, plan))
    monkeypatch.setattr(guard, "_controller_runs", lambda *a, **k: [])

    def fake_persist(ledger, record, plan_value, *, action):
        order.append("persist:" + record_state(record))
        return "d" * 40

    def fake_dispatch(*args, **kwargs):
        assert order == ["persist:RESERVED"]
        order.append("dispatch")
        return subprocess.CompletedProcess(["gh"], 0, stdout="", stderr="")

    monkeypatch.setattr(guard, "persist_dispatch_record", fake_persist)
    monkeypatch.setattr(guard, "_dispatch_command", fake_dispatch)
    monkeypatch.setattr(
        guard,
        "_poll_for_new_run",
        lambda *a, **k: {
            "status": "RUN_IDENTIFIED",
            "run": _run_row(77, plan),
            "candidates": [_run_row(77, plan)],
        },
    )
    report = guard.dispatch_once(
        trial_id="PC-RCL-001",
        repo_root=ROOT,
        ledger_dir=tmp_path,
        plan_path=PLAN,
        manifest_path=MANIFEST,
        registry_path=REGISTRY,
        handoff_manifest_path=HANDOFFS,
        apply=True,
        confirm_freeze=spec.freeze_tag,
        confirm_trial="PC-RCL-001",
        confirm_model="GPT-5.6 Sol",
        confirm_client="ChatGPT/1.2026.230; iOS 26.6.1",
        confirm_memory="enabled",
        confirm_customization="present",
    )
    assert order == [
        "persist:RESERVED",
        "dispatch",
        "persist:DISPATCH_SUBMITTED",
        "persist:RUN_IDENTIFIED",
    ]
    assert report["run_discovery"]["run"]["databaseId"] == 77
    assert report["automatic_retry_allowed"] is False


def test_dispatch_dry_run_has_no_reservation_or_external_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        guard,
        "preflight",
        lambda **kwargs: {
            "ready": True,
            "trial_id": "PC-RCL-001",
            "issue_number": 18,
            "included_registry_started": 0,
        },
    )
    monkeypatch.setattr(
        guard,
        "prepare_dispatch_ledger",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not reserve")),
    )
    monkeypatch.setattr(
        guard,
        "_dispatch_command",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not dispatch")),
    )
    report = guard.dispatch_once(
        trial_id="PC-RCL-001",
        repo_root=ROOT,
        ledger_dir=tmp_path,
        plan_path=PLAN,
        manifest_path=MANIFEST,
        registry_path=REGISTRY,
        handoff_manifest_path=HANDOFFS,
        apply=False,
    )
    assert report["mode"] == "DRY_RUN"
    assert report["included_registry_started"] == 0


def test_failed_dispatch_command_is_consumed_and_never_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, registry, plan = _inputs()
    states: list[str] = []
    dispatch_count = 0
    monkeypatch.setattr(guard, "preflight", lambda **kwargs: {"ready": True})
    monkeypatch.setattr(guard, "_gh", lambda value=None: "gh")
    monkeypatch.setattr(guard, "prepare_dispatch_ledger", lambda *a, **k: tmp_path)
    monkeypatch.setattr(guard, "load_dispatch_records", lambda *a, **k: {})
    monkeypatch.setattr(guard, "_issue_from_gh", lambda *a, **k: _exact_issue(spec, registry, plan))
    monkeypatch.setattr(guard, "_controller_runs", lambda *a, **k: [])
    monkeypatch.setattr(
        guard,
        "persist_dispatch_record",
        lambda ledger, record, plan_value, *, action: states.append(record_state(record)) or "d" * 40,
    )

    def failed(*args, **kwargs):
        nonlocal dispatch_count
        dispatch_count += 1
        return subprocess.CompletedProcess(["gh"], 1, stdout="", stderr="network uncertain")

    monkeypatch.setattr(guard, "_dispatch_command", failed)
    monkeypatch.setattr(
        guard,
        "_poll_for_new_run",
        lambda *a, **k: {"status": "RUN_UNRESOLVED", "run": None, "candidates": []},
    )
    report = guard.dispatch_once(
        trial_id="PC-RCL-001", repo_root=ROOT, ledger_dir=tmp_path,
        plan_path=PLAN, manifest_path=MANIFEST, registry_path=REGISTRY,
        handoff_manifest_path=HANDOFFS, apply=True,
        confirm_freeze=spec.freeze_tag, confirm_trial="PC-RCL-001",
        confirm_model="GPT-5.6 Sol",
        confirm_client="ChatGPT/1.2026.230; iOS 26.6.1",
        confirm_memory="enabled", confirm_customization="present", poll_seconds=0,
    )
    assert dispatch_count == 1
    assert states == ["RESERVED", "DISPATCH_COMMAND_FAILED_UNCERTAIN", "RUN_UNRESOLVED"]
    assert report["automatic_retry_allowed"] is False


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def test_dispatch_ledger_initialization_and_reservation_are_durable(
    tmp_path: Path,
) -> None:
    _, _, plan = _inputs()
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    admin = tmp_path / "admin"
    subprocess.run(["git", "clone", str(bare), str(admin)], check=True, capture_output=True)
    _git(admin, "config", "user.name", "test")
    _git(admin, "config", "user.email", "test@example.com")
    (admin / "README.md").write_text("base\n", encoding="utf-8")
    _git(admin, "add", "README.md")
    _git(admin, "commit", "-m", "base")
    _git(admin, "branch", "-M", "main")
    _git(admin, "push", "-u", "origin", "main")

    ledger = tmp_path / "ledger"
    prepared = guard.prepare_dispatch_ledger(admin, ledger, PLAN, plan)
    assert prepared == ledger.resolve()
    heads = _git(admin, "ls-remote", "--heads", "origin", "refs/heads/rcl-dispatch-ledger")
    assert "refs/heads/rcl-dispatch-ledger" in heads
    assert (ledger / "rcl-dispatch/MANIFEST.json").is_file()

    record = _reservation(plan)
    commit = guard.persist_dispatch_record(ledger, record, plan, action="reserve")
    assert len(commit) == 40
    assert (ledger / "rcl-dispatch/PC-RCL-001.json").is_file()

    second = tmp_path / "ledger-second"
    guard.prepare_dispatch_ledger(admin, second, PLAN, plan)
    records = guard.load_dispatch_records(second, plan)
    assert record_state(records["PC-RCL-001"]) == "RESERVED"
    assert records["PC-RCL-001"]["reservation_id"] == "a" * 64
    recovered = append_record_event(
        records["PC-RCL-001"],
        "DISPATCH_SUBMITTED",
        at_utc="2026-09-01T16:10:01Z",
        returncode=0,
    )
    second_commit = guard.persist_dispatch_record(
        second, recovered, plan, action="recover-submit"
    )
    assert len(second_commit) == 40
    third = tmp_path / "ledger-third"
    guard.prepare_dispatch_ledger(admin, third, PLAN, plan)
    latest = guard.load_dispatch_records(third, plan)["PC-RCL-001"]
    assert record_state(latest) == "DISPATCH_SUBMITTED"


def test_dispatch_events_forbid_hidden_assignment_material() -> None:
    _, _, plan = _inputs()
    record = _reservation(plan)
    with pytest.raises(ValueError, match="hidden assignment"):
        append_record_event(record, "DISPATCH_SUBMITTED", condition="available")


def _identified_record(plan):
    record = _reservation(plan)
    record = append_record_event(
        record, "DISPATCH_SUBMITTED", at_utc="2026-09-01T16:10:01Z"
    )
    return append_record_event(
        record,
        "RUN_IDENTIFIED",
        at_utc="2026-09-01T16:10:02Z",
        run_id=77,
        run_url="https://github.com/x/actions/runs/77",
    )


def test_reconcile_marks_reveal_without_touching_behavioral_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, registry, plan = _inputs()
    record = _identified_record(plan)
    monkeypatch.setattr(guard, "_gh", lambda value=None: "gh")
    monkeypatch.setattr(guard, "prepare_dispatch_ledger", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        guard, "load_dispatch_records", lambda *a, **k: {"PC-RCL-001": record}
    )
    monkeypatch.setattr(
        guard,
        "_run_view",
        lambda *a, **k: {
            "databaseId": 77,
            "event": "workflow_dispatch",
            "headBranch": plan["controller_tag"],
            "headSha": plan["controller_commit"],
            "status": "completed",
            "conclusion": "success",
            "url": "https://github.com/x/actions/runs/77",
        },
    )
    issue = _exact_issue(spec, registry, plan)
    issue["comments"] = [
        {"body": "SAIS_RCL_READY {}"},
        {"body": "SAIS_RCL_REVEAL {}"},
    ]
    monkeypatch.setattr(guard, "_issue_from_gh", lambda *a, **k: issue)
    seen = {}

    def persist(ledger, updated, plan_value, *, action):
        seen["record"] = updated
        return "e" * 40

    monkeypatch.setattr(guard, "persist_dispatch_record", persist)
    report = guard.reconcile_trial(
        trial_id="PC-RCL-001", repo_root=ROOT, ledger_dir=tmp_path,
        plan_path=PLAN, manifest_path=MANIFEST, registry_path=REGISTRY,
        handoff_manifest_path=HANDOFFS,
    )
    assert report["state"] == "REVEALED"
    assert record_state(seen["record"]) == "REVEALED"
    assert not guard.FORBIDDEN_DISPATCH_KEYS.intersection(json.loads(json.dumps(seen["record"])))


def test_post_reservation_run_race_blocks_local_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, registry, plan = _inputs()
    persisted: list[str] = []
    run_calls = 0
    monkeypatch.setattr(guard, "preflight", lambda **kwargs: {"ready": True})
    monkeypatch.setattr(guard, "_gh", lambda value=None: "gh")
    monkeypatch.setattr(guard, "prepare_dispatch_ledger", lambda *a, **k: tmp_path)
    monkeypatch.setattr(guard, "load_dispatch_records", lambda *a, **k: {})
    monkeypatch.setattr(guard, "_issue_from_gh", lambda *a, **k: _exact_issue(spec, registry, plan))

    def runs(*args, **kwargs):
        nonlocal run_calls
        run_calls += 1
        return [] if run_calls == 1 else [_run_row(88, plan)]

    monkeypatch.setattr(guard, "_controller_runs", runs)
    monkeypatch.setattr(
        guard,
        "persist_dispatch_record",
        lambda ledger, record, plan_value, *, action: persisted.append(record_state(record)) or "f" * 40,
    )
    monkeypatch.setattr(
        guard,
        "_dispatch_command",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("dispatch must be blocked")),
    )
    report = guard.dispatch_once(
        trial_id="PC-RCL-001", repo_root=ROOT, ledger_dir=tmp_path,
        plan_path=PLAN, manifest_path=MANIFEST, registry_path=REGISTRY,
        handoff_manifest_path=HANDOFFS, apply=True,
        confirm_freeze=spec.freeze_tag, confirm_trial="PC-RCL-001",
        confirm_model="GPT-5.6 Sol",
        confirm_client="ChatGPT/1.2026.230; iOS 26.6.1",
        confirm_memory="enabled", confirm_customization="present",
    )
    assert report["mode"] == "APPLY_BLOCKED_PRE_DISPATCH"
    assert report["external_dispatch_performed"] is False
    assert persisted == ["RESERVED", "RUN_AMBIGUOUS"]


def test_post_reservation_issue_change_aborts_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, registry, plan = _inputs()
    calls = 0
    monkeypatch.setattr(guard, "preflight", lambda **kwargs: {"ready": True})
    monkeypatch.setattr(guard, "_gh", lambda value=None: "gh")
    monkeypatch.setattr(guard, "prepare_dispatch_ledger", lambda *a, **k: tmp_path)
    monkeypatch.setattr(guard, "load_dispatch_records", lambda *a, **k: {})

    def issue(*args, **kwargs):
        nonlocal calls
        calls += 1
        value = _exact_issue(spec, registry, plan)
        if calls > 1:
            value["comments"] = [{"body": "changed"}]
        return value

    monkeypatch.setattr(guard, "_issue_from_gh", issue)
    monkeypatch.setattr(guard, "_controller_runs", lambda *a, **k: [])
    states: list[str] = []
    monkeypatch.setattr(
        guard,
        "persist_dispatch_record",
        lambda ledger, record, plan_value, *, action: states.append(record_state(record)) or "f" * 40,
    )
    monkeypatch.setattr(
        guard,
        "_dispatch_command",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("dispatch must be blocked")),
    )
    report = guard.dispatch_once(
        trial_id="PC-RCL-001", repo_root=ROOT, ledger_dir=tmp_path,
        plan_path=PLAN, manifest_path=MANIFEST, registry_path=REGISTRY,
        handoff_manifest_path=HANDOFFS, apply=True,
        confirm_freeze=spec.freeze_tag, confirm_trial="PC-RCL-001",
        confirm_model="GPT-5.6 Sol",
        confirm_client="ChatGPT/1.2026.230; iOS 26.6.1",
        confirm_memory="enabled", confirm_customization="present",
    )
    assert report["mode"] == "APPLY_ABORTED_PRE_DISPATCH"
    assert states == ["RESERVED", "ABORTED"]
