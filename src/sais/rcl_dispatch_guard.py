"""Fail-closed single-trial dispatcher for the frozen RCL-PC v2 block."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
from typing import Any, Callable, Mapping, Sequence

from .rcl_pc_analysis import DEFAULT_MANIFEST, StudySpec, load_study_spec
from .rcl_registry import issue_title, load_registry, render_issue_body, validate_registry

DISPATCH_PROTOCOL = "SMI-CP/RCL-PC/DISPATCH/1"
PLAN_VERSION = "SMI-CP/RCL-PC/DISPATCH-PLAN/1"
RECORD_VERSION = "SMI-CP/RCL-PC/DISPATCH-RECORD/1"
LEDGER_BRANCH = "rcl-dispatch-ledger"
DEFAULT_PLAN = (
    Path(__file__).resolve().parents[2]
    / "experiments/008c-dispatch-guard/DISPATCH_PLAN.json"
)
DEFAULT_REGISTRY = (
    Path(__file__).resolve().parents[2]
    / "experiments/007-rcl-pc-execution-readiness/TRIAL_REGISTRY.json"
)
DEFAULT_HANDOFF_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "experiments/008b-subject-isolation/HANDOFF_MANIFEST.json"
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_DISPATCH_KEYS = {
    "condition", "legibility", "key", "trial_key", "assignment", "payload_hash",
}
TERMINAL_STATES = {"REVEALED", "COLLECTED", "ABORTED"}
RECORD_TRANSITIONS = {
    "RESERVED": {
        "DISPATCH_SUBMITTED", "DISPATCH_COMMAND_FAILED_UNCERTAIN",
        "RUN_IDENTIFIED", "RUN_UNRESOLVED", "RUN_AMBIGUOUS", "ABORTED",
    },
    "DISPATCH_SUBMITTED": {"RUN_IDENTIFIED", "RUN_UNRESOLVED", "RUN_AMBIGUOUS"},
    "DISPATCH_COMMAND_FAILED_UNCERTAIN": {"RUN_IDENTIFIED", "RUN_UNRESOLVED", "RUN_AMBIGUOUS"},
    "RUN_UNRESOLVED": {"RUN_IDENTIFIED", "RUN_AMBIGUOUS", "ABORTED"},
    "RUN_AMBIGUOUS": {"RUN_IDENTIFIED", "ABORTED"},
    "RUN_IDENTIFIED": {"READY_OBSERVED", "REVEALED", "ABORTED"},
    "READY_OBSERVED": {"REVEALED", "ABORTED"},
    "REVEALED": {"COLLECTED"},
    "COLLECTED": set(),
    "ABORTED": set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run(command: Sequence[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        list(command), cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _gh(executable: str | None = None) -> str:
    value = executable or shutil.which("gh")
    if not value:
        raise RuntimeError("GitHub CLI `gh` is required")
    return value


def _json_file(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_dispatch_plan(
    plan_path: Path,
    spec: StudySpec,
    registry_path: Path,
    handoff_manifest_path: Path,
) -> dict[str, Any]:
    plan = _json_file(plan_path)
    registry = load_registry(registry_path)
    validate_registry(registry, spec)
    handoff = _json_file(handoff_manifest_path)
    checks = {
        "plan_version": plan.get("plan_version") == PLAN_VERSION,
        "prepared_before_first_dispatch": plan.get("prepared_before_first_dispatch") is True,
        "freeze_tag": plan.get("freeze_tag") == spec.freeze_tag,
        "controller_commit": plan.get("controller_commit") == spec.controller_code_sha,
        "configuration_commit": plan.get("configuration_commit") == spec.config_commit,
        "configuration_path": plan.get("configuration_path") == spec.config_path,
        "configuration_binding_hash": (
            plan.get("configuration_binding_hash") == spec.expected_binding_hash
        ),
        "subject_login": plan.get("subject_login") == spec.subject_login,
        "trial_order": tuple(plan.get("trial_order", [])) == spec.expected_ids,
        "max_concurrent": plan.get("max_concurrent_dispatches") == 1,
        "reservation_first": plan.get("reservation_precedes_dispatch") is True,
        "no_blind_retry": plan.get("blind_retry_after_reservation_allowed") is False,
        "ledger_branch": plan.get("dispatch_ledger_branch") == LEDGER_BRANCH,
        "registry_snapshot": plan.get("registry_snapshot_sha256")
        == sha256_bytes(registry_path.read_bytes()),
        "handoff_manifest": plan.get("handoff_manifest_sha256")
        == sha256_bytes(handoff_manifest_path.read_bytes()),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError("invalid dispatch plan: " + ", ".join(failed))

    registry_by = {row["trial_id"]: row for row in registry["trials"]}
    handoff_by = {row["trial_id"]: row for row in handoff.get("handoffs", [])}
    plan_trials = plan.get("trials")
    if not isinstance(plan_trials, list) or len(plan_trials) != len(spec.expected_ids):
        raise ValueError("dispatch plan must contain exactly 32 trial records")
    for row in plan_trials:
        trial_id = row.get("trial_id") if isinstance(row, dict) else None
        if trial_id not in registry_by or trial_id not in handoff_by:
            raise ValueError(f"dispatch plan trial mapping invalid: {trial_id}")
        registered = registry_by[trial_id]
        frozen_handoff = handoff_by[trial_id]
        expected = {
            "trial_id": trial_id,
            "issue_number": registered["issue_number"],
            "issue_url": registered["issue_url"],
            "handoff_path": frozen_handoff["path"],
            "handoff_sha256": frozen_handoff["sha256"],
        }
        if row != expected:
            raise ValueError(f"dispatch plan trial record mismatch: {trial_id}")
    return plan


def _plan_trial(plan: Mapping[str, Any], trial_id: str) -> dict[str, Any]:
    matches = [
        row for row in plan["trials"]
        if isinstance(row, dict) and row.get("trial_id") == trial_id
    ]
    if len(matches) != 1:
        raise ValueError(f"trial is not uniquely planned: {trial_id}")
    return matches[0]


def _issue_from_gh(gh: str, repository: str, issue_number: int) -> dict[str, Any]:
    raw = _run([
        gh, "issue", "view", str(issue_number), "--repo", repository,
        "--json", "number,title,url,body,state,comments",
    ])
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("GitHub issue view returned non-object")
    return value


def _zero_comments(issue: Mapping[str, Any]) -> bool:
    comments = issue.get("comments")
    if comments is None:
        return True
    if isinstance(comments, list):
        return len(comments) == 0
    if isinstance(comments, int) and not isinstance(comments, bool):
        return comments == 0
    return False


def verify_issue_surface(
    issue: Mapping[str, Any],
    trial: Mapping[str, Any],
    registry: Mapping[str, Any],
    spec: StudySpec,
) -> None:
    expected_trial = next(
        row for row in registry["trials"] if row["trial_id"] == trial["trial_id"]
    )
    body_trial = deepcopy(expected_trial)
    body_trial["status"] = "NOT_CREATED"
    expected_body = render_issue_body(body_trial, registry)
    checks = {
        "number": issue.get("number") == trial["issue_number"],
        "url": issue.get("url") == trial["issue_url"],
        "title": issue.get("title") == issue_title(str(trial["trial_id"])),
        "body": str(issue.get("body") or "") == expected_body,
        "open": str(issue.get("state", "")).upper() == "OPEN",
        "zero_comments": _zero_comments(issue),
        "registry_status": expected_trial.get("status") == "ISSUE_CREATED",
        "repository": str(trial["issue_url"]).startswith(
            f"https://github.com/{spec.repository}/issues/"
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError("issue preflight failed: " + ", ".join(failed))


def _controller_runs(
    gh: str, repository: str, workflow: str
) -> list[dict[str, Any]]:
    raw = _run([
        gh, "run", "list", "--repo", repository,
        "--workflow", workflow, "--event", "workflow_dispatch",
        "--limit", "1000",
        "--json", (
            "databaseId,event,headBranch,headSha,createdAt,status,"
            "conclusion,url,displayTitle"
        ),
    ])
    value = json.loads(raw or "[]")
    if not isinstance(value, list):
        raise RuntimeError("GitHub run list returned non-list")
    return [row for row in value if isinstance(row, dict)]


def matching_runs(
    rows: Sequence[Mapping[str, Any]], plan: Mapping[str, Any]
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in rows
        if row.get("event") == "workflow_dispatch"
        and row.get("headBranch") == plan["controller_tag"]
        and row.get("headSha") == plan["controller_commit"]
        and isinstance(row.get("databaseId"), int)
    ]


def discover_new_run(
    baseline_ids: Sequence[int],
    rows: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    baseline = set(int(value) for value in baseline_ids)
    new_rows = [
        row for row in matching_runs(rows, plan)
        if int(row["databaseId"]) not in baseline
    ]
    if len(new_rows) == 1:
        row = new_rows[0]
        return {"status": "RUN_IDENTIFIED", "run": row, "candidates": [row]}
    if not new_rows:
        return {"status": "RUN_UNRESOLVED", "run": None, "candidates": []}
    return {"status": "RUN_AMBIGUOUS", "run": None, "candidates": new_rows}


def _utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    offset = parsed.utcoffset()
    return offset is not None and offset.total_seconds() == 0


def record_state(record: Mapping[str, Any]) -> str:
    events = record.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("dispatch record has no events")
    state = events[-1].get("state")
    if not isinstance(state, str):
        raise ValueError("dispatch record has invalid terminal state")
    return state


def validate_dispatch_record(
    record: Mapping[str, Any], plan: Mapping[str, Any]
) -> None:
    trial_id = record.get("trial_id")
    trial = _plan_trial(plan, str(trial_id))
    checks = {
        "record_version": record.get("record_version") == RECORD_VERSION,
        "protocol": record.get("protocol") == DISPATCH_PROTOCOL,
        "trial_id": trial_id == trial["trial_id"],
        "issue_number": record.get("issue_number") == trial["issue_number"],
        "handoff_sha256": record.get("handoff_sha256") == trial["handoff_sha256"],
        "freeze_tag": record.get("freeze_tag") == plan["freeze_tag"],
        "controller_commit": record.get("controller_commit") == plan["controller_commit"],
        "config_commit": record.get("configuration_commit")
        == plan["configuration_commit"],
        "reservation_id": isinstance(record.get("reservation_id"), str)
        and bool(HEX64.fullmatch(str(record.get("reservation_id")))),
        "baseline_ids": isinstance(record.get("baseline_run_ids"), list)
        and all(isinstance(value, int) for value in record.get("baseline_run_ids", [])),
    }
    checks["top_level_assignment_free"] = not FORBIDDEN_DISPATCH_KEYS.intersection(record)
    events = record.get("events")
    checks["events"] = isinstance(events, list) and bool(events)
    if isinstance(events, list):
        checks["event_sequence"] = all(
            isinstance(event, dict)
            and event.get("sequence") == index
            and isinstance(event.get("state"), str)
            and _utc_timestamp(event.get("at_utc"))
            for index, event in enumerate(events, start=1)
        )
        checks["first_reserved"] = bool(events and events[0].get("state") == "RESERVED")
        checks["events_assignment_free"] = all(
            not FORBIDDEN_DISPATCH_KEYS.intersection(event)
            for event in events if isinstance(event, dict)
        )
        transitions_ok = True
        for previous, current in zip(events, events[1:]):
            if current.get("state") not in RECORD_TRANSITIONS.get(str(previous.get("state")), set()):
                transitions_ok = False
        checks["event_transitions"] = transitions_ok
        checks["updated_at"] = bool(events and record.get("updated_at_utc") == events[-1].get("at_utc"))
    else:
        checks["event_sequence"] = False
        checks["first_reserved"] = False
        checks["events_assignment_free"] = False
        checks["event_transitions"] = False
        checks["updated_at"] = False
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError("invalid dispatch record: " + ", ".join(failed))


def append_record_event(
    record: Mapping[str, Any], state: str, *, at_utc: str | None = None, **fields: Any
) -> dict[str, Any]:
    if FORBIDDEN_DISPATCH_KEYS.intersection(fields):
        raise ValueError("hidden assignment material is forbidden in dispatch events")
    current_state = record_state(record)
    if state not in RECORD_TRANSITIONS.get(current_state, set()):
        raise ValueError(f"invalid dispatch state transition: {current_state} -> {state}")
    updated = deepcopy(dict(record))
    events = updated.setdefault("events", [])
    event = {
        "sequence": len(events) + 1,
        "at_utc": at_utc or utc_now(),
        "state": state,
        **fields,
    }
    events.append(event)
    updated["updated_at_utc"] = event["at_utc"]
    return updated


def make_reservation_record(
    plan: Mapping[str, Any],
    trial_id: str,
    baseline_run_ids: Sequence[int],
    *,
    reservation_id: str | None = None,
    reserved_at_utc: str | None = None,
) -> dict[str, Any]:
    trial = _plan_trial(plan, trial_id)
    nonce = reservation_id or hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    if not HEX64.fullmatch(nonce):
        raise ValueError("reservation_id must be a lowercase SHA-256 hex string")
    at = reserved_at_utc or utc_now()
    record = {
        "record_version": RECORD_VERSION,
        "protocol": DISPATCH_PROTOCOL,
        "trial_id": trial_id,
        "issue_number": trial["issue_number"],
        "issue_url": trial["issue_url"],
        "handoff_path": trial["handoff_path"],
        "handoff_sha256": trial["handoff_sha256"],
        "freeze_tag": plan["freeze_tag"],
        "freeze_commit": plan["freeze_commit"],
        "controller_tag": plan["controller_tag"],
        "controller_commit": plan["controller_commit"],
        "configuration_commit": plan["configuration_commit"],
        "configuration_path": plan["configuration_path"],
        "configuration_binding_hash": plan["configuration_binding_hash"],
        "reservation_id": nonce,
        "baseline_run_ids": sorted(set(int(value) for value in baseline_run_ids)),
        "created_at_utc": at,
        "updated_at_utc": at,
        "events": [{"sequence": 1, "at_utc": at, "state": "RESERVED"}],
    }
    validate_dispatch_record(record, plan)
    return record


def _remote_branch_exists(repo_root: Path, branch: str) -> bool:
    remote = _run(["git", "remote", "get-url", "origin"], cwd=repo_root)
    result = subprocess.run(
        ["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 2}:
        raise RuntimeError("could not query dispatch-ledger branch")
    return bool(result.stdout.strip())


def validate_ledger_manifest(
    value: Mapping[str, Any], plan_path: Path, plan: Mapping[str, Any]
) -> None:
    checks = {
        "ledger_version": value.get("ledger_version") == "SMI-CP/RCL-PC/DISPATCH-LEDGER/1",
        "dispatch_protocol": value.get("dispatch_protocol") == DISPATCH_PROTOCOL,
        "plan_sha256": value.get("plan_sha256") == sha256_bytes(plan_path.read_bytes()),
        "freeze_tag": value.get("freeze_tag") == plan["freeze_tag"],
        "freeze_commit": value.get("freeze_commit") == plan["freeze_commit"],
        "controller_tag": value.get("controller_tag") == plan["controller_tag"],
        "controller_commit": value.get("controller_commit") == plan["controller_commit"],
        "configuration_commit": value.get("configuration_commit") == plan["configuration_commit"],
        "configuration_path": value.get("configuration_path") == plan["configuration_path"],
        "reservation_rule": value.get("rule") == "reservation_commit_must_precede_workflow_dispatch",
        "created_at": _utc_timestamp(value.get("created_at_utc")),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError("dispatch ledger manifest mismatch: " + ", ".join(failed))


def _configure_ledger_identity(ledger_dir: Path) -> None:
    _run(["git", "config", "user.name", "sais-rcl-dispatch-guard"], cwd=ledger_dir)
    _run([
        "git", "config", "user.email", "actions@users.noreply.github.com"
    ], cwd=ledger_dir)


def prepare_dispatch_ledger(
    repo_root: Path,
    ledger_dir: Path,
    plan_path: Path,
    plan: Mapping[str, Any],
) -> Path:
    repo_root = repo_root.resolve()
    ledger_dir = ledger_dir.resolve()
    branch = str(plan["dispatch_ledger_branch"])
    origin = _run(["git", "remote", "get-url", "origin"], cwd=repo_root)
    exists = _remote_branch_exists(repo_root, branch)

    if ledger_dir.exists():
        if not (ledger_dir / ".git").exists():
            raise RuntimeError("dispatch ledger directory exists but is not a Git checkout")
        if _run(["git", "status", "--porcelain"], cwd=ledger_dir):
            raise RuntimeError("dispatch ledger checkout is dirty")
        if not exists:
            raise RuntimeError("local dispatch ledger exists but remote branch does not")
        _run(["git", "fetch", "origin", branch], cwd=ledger_dir)
        _run(["git", "reset", "--hard", f"origin/{branch}"], cwd=ledger_dir)
        _configure_ledger_identity(ledger_dir)
        validate_ledger_manifest(_json_file(ledger_dir / "rcl-dispatch/MANIFEST.json"), plan_path, plan)
        return ledger_dir

    if exists:
        _run([
            "git", "clone", "--branch", branch, "--single-branch",
            origin, str(ledger_dir),
        ], cwd=repo_root)
        _configure_ledger_identity(ledger_dir)
        validate_ledger_manifest(_json_file(ledger_dir / "rcl-dispatch/MANIFEST.json"), plan_path, plan)
        return ledger_dir

    _run(["git", "clone", "--no-checkout", origin, str(ledger_dir)], cwd=repo_root)
    _run(["git", "switch", "--orphan", branch], cwd=ledger_dir)
    _configure_ledger_identity(ledger_dir)
    manifest = {
        "ledger_version": "SMI-CP/RCL-PC/DISPATCH-LEDGER/1",
        "created_at_utc": utc_now(),
        "dispatch_protocol": DISPATCH_PROTOCOL,
        "plan_sha256": sha256_bytes(plan_path.read_bytes()),
        "freeze_tag": plan["freeze_tag"],
        "freeze_commit": plan["freeze_commit"],
        "controller_tag": plan["controller_tag"],
        "controller_commit": plan["controller_commit"],
        "configuration_commit": plan["configuration_commit"],
        "configuration_path": plan["configuration_path"],
        "rule": "reservation_commit_must_precede_workflow_dispatch",
    }
    target = ledger_dir / "rcl-dispatch" / "MANIFEST.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _run(["git", "add", "rcl-dispatch/MANIFEST.json"], cwd=ledger_dir)
    _run(["git", "commit", "-m", "rcl-dispatch: initialize ledger"], cwd=ledger_dir)
    _run(["git", "push", "origin", f"HEAD:refs/heads/{branch}"], cwd=ledger_dir)
    validate_ledger_manifest(manifest, plan_path, plan)
    return ledger_dir


def load_dispatch_records(
    ledger_dir: Path, plan: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    root = ledger_dir / "rcl-dispatch"
    records: dict[str, dict[str, Any]] = {}
    if not root.exists():
        return records
    for path in sorted(root.glob("PC-RCL-*.json")):
        value = _json_file(path)
        validate_dispatch_record(value, plan)
        trial_id = str(value["trial_id"])
        if trial_id in records:
            raise ValueError(f"duplicate dispatch record: {trial_id}")
        records[trial_id] = value
    return records


def assert_dispatch_order(
    plan: Mapping[str, Any],
    trial_id: str,
    records: Mapping[str, Mapping[str, Any]],
) -> None:
    order = list(plan["trial_order"])
    if trial_id not in order:
        raise ValueError(f"trial is not in fixed dispatch order: {trial_id}")
    if trial_id in records:
        raise RuntimeError(f"trial is already reserved and may not be retried: {trial_id}")
    active = [
        key for key, record in records.items()
        if record_state(record) not in TERMINAL_STATES
    ]
    if active:
        raise RuntimeError("nonterminal prior dispatch record exists: " + ", ".join(sorted(active)))
    index = order.index(trial_id)
    missing_prior = [
        key for key in order[:index]
        if key not in records or record_state(records[key]) not in TERMINAL_STATES
    ]
    if missing_prior:
        raise RuntimeError(
            "fixed-order predecessor is not terminal: " + ", ".join(missing_prior)
        )


def persist_dispatch_record(
    ledger_dir: Path,
    record: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    action: str,
) -> str:
    validate_dispatch_record(record, plan)
    if _run(["git", "status", "--porcelain"], cwd=ledger_dir):
        raise RuntimeError("dispatch ledger checkout is dirty before persistence")
    trial_id = str(record["trial_id"])
    target = ledger_dir / "rcl-dispatch" / f"{trial_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _run(["git", "add", str(target.relative_to(ledger_dir))], cwd=ledger_dir)
    _run(["git", "commit", "-m", f"rcl-dispatch: {action} {trial_id}"], cwd=ledger_dir)
    branch = str(plan["dispatch_ledger_branch"])
    _run(["git", "push", "origin", f"HEAD:refs/heads/{branch}"], cwd=ledger_dir)
    return _run(["git", "rev-parse", "HEAD"], cwd=ledger_dir)


def load_remote_dispatch_records(
    repo_root: Path, plan: Mapping[str, Any], plan_path: Path = DEFAULT_PLAN
) -> dict[str, dict[str, Any]]:
    branch = str(plan["dispatch_ledger_branch"])
    if not _remote_branch_exists(repo_root, branch):
        return {}
    _run([
        "git", "fetch", "origin",
        f"refs/heads/{branch}:refs/remotes/origin/{branch}",
    ], cwd=repo_root)
    manifest_raw = _run([
        "git", "show", f"origin/{branch}:rcl-dispatch/MANIFEST.json"
    ], cwd=repo_root)
    manifest = json.loads(manifest_raw)
    if not isinstance(manifest, dict):
        raise RuntimeError("remote dispatch ledger manifest is not an object")
    validate_ledger_manifest(manifest, plan_path, plan)
    tree = _run([
        "git", "ls-tree", "-r", "--name-only", f"origin/{branch}",
        "--", "rcl-dispatch",
    ], cwd=repo_root)
    records: dict[str, dict[str, Any]] = {}
    for relative in tree.splitlines():
        if not re.fullmatch(r"rcl-dispatch/PC-RCL-[0-9]{3}\.json", relative):
            continue
        raw = _run(["git", "show", f"origin/{branch}:{relative}"], cwd=repo_root)
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"remote dispatch record is not an object: {relative}")
        validate_dispatch_record(value, plan)
        records[str(value["trial_id"])] = value
    return records


def verify_git_anchors(repo_root: Path, plan: Mapping[str, Any]) -> None:
    freeze = _run(["git", "rev-list", "-n", "1", plan["freeze_tag"]], cwd=repo_root)
    controller = _run(
        ["git", "rev-list", "-n", "1", plan["controller_tag"]], cwd=repo_root
    )
    if freeze != plan["freeze_commit"]:
        raise RuntimeError("freeze tag target does not match dispatch plan")
    if controller != plan["controller_commit"]:
        raise RuntimeError("controller tag target does not match dispatch plan")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", plan["configuration_commit"], freeze],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("configuration commit is not an ancestor of freeze commit")


def _verify_handoff(root: Path, trial: Mapping[str, Any]) -> None:
    path = root / str(trial["handoff_path"])
    if not path.is_file():
        raise RuntimeError("precommitted subject handoff is missing")
    actual = sha256_bytes(path.read_bytes())
    if actual != trial["handoff_sha256"]:
        raise RuntimeError("precommitted subject handoff bytes do not match plan")


def preflight(
    *,
    trial_id: str,
    repo_root: Path,
    plan_path: Path = DEFAULT_PLAN,
    manifest_path: Path = DEFAULT_MANIFEST,
    registry_path: Path = DEFAULT_REGISTRY,
    handoff_manifest_path: Path = DEFAULT_HANDOFF_MANIFEST,
    gh_executable: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    spec = load_study_spec(manifest_path, root=repo_root)
    registry = load_registry(registry_path)
    validate_registry(registry, spec)
    plan = load_dispatch_plan(plan_path, spec, registry_path, handoff_manifest_path)
    trial = _plan_trial(plan, trial_id)
    verify_git_anchors(repo_root, plan)
    _verify_handoff(repo_root, trial)
    records = load_remote_dispatch_records(repo_root, plan, plan_path)
    assert_dispatch_order(plan, trial_id, records)

    gh = _gh(gh_executable)
    issue = _issue_from_gh(gh, spec.repository, int(trial["issue_number"]))
    verify_issue_surface(issue, trial, registry, spec)
    all_runs = _controller_runs(gh, spec.repository, str(plan["controller_workflow"]))
    matched = matching_runs(all_runs, plan)
    active = [row for row in matched if row.get("status") != "completed"]
    if active:
        raise RuntimeError("a matching frozen controller workflow run is already active")
    baseline_ids = sorted(int(row["databaseId"]) for row in matched)
    return {
        "ready": True,
        "trial_id": trial_id,
        "issue_number": trial["issue_number"],
        "issue_url": trial["issue_url"],
        "handoff_path": trial["handoff_path"],
        "handoff_sha256": trial["handoff_sha256"],
        "baseline_run_ids": baseline_ids,
        "prior_dispatch_records": sorted(records),
        "included_registry_started": registry["included_trials_started"],
    }


def verify_operator_confirmations(
    config: Mapping[str, Any],
    *,
    freeze: str | None,
    trial: str | None,
    trial_id: str,
    model: str | None,
    client: str | None,
    memory: str | None,
    customization: str | None,
    spec: StudySpec,
) -> None:
    expected = {
        "freeze": spec.freeze_tag,
        "trial": trial_id,
        "model": config.get("model_label"),
        "client": config.get("interface_build"),
        "memory": config.get("memory_state"),
        "customization": config.get("customization_state"),
    }
    actual = {
        "freeze": freeze,
        "trial": trial,
        "model": model,
        "client": client,
        "memory": memory,
        "customization": customization,
    }
    failed = [name for name in expected if actual[name] != expected[name]]
    if failed:
        raise RuntimeError(
            "operator product-state confirmation mismatch: " + ", ".join(failed)
        )


def _dispatch_command(
    gh: str,
    spec: StudySpec,
    plan: Mapping[str, Any],
    trial: Mapping[str, Any],
) -> subprocess.CompletedProcess[str]:
    command = [
        gh, "workflow", "run", str(plan["controller_workflow"]),
        "--repo", spec.repository,
        "--ref", str(plan["controller_tag"]),
        "-f", f"trial_id={trial['trial_id']}",
        "-f", f"issue_number={trial['issue_number']}",
        "-f", f"subject_login={spec.subject_login}",
        "-f", f"config_commit={plan['configuration_commit']}",
        "-f", f"config_path={plan['configuration_path']}",
    ]
    return subprocess.run(command, capture_output=True, text=True)


def _poll_for_new_run(
    gh: str,
    spec: StudySpec,
    plan: Mapping[str, Any],
    baseline_ids: Sequence[int],
    *,
    poll_seconds: int,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0, poll_seconds)
    last = {"status": "RUN_UNRESOLVED", "run": None, "candidates": []}
    while True:
        rows = _controller_runs(gh, spec.repository, str(plan["controller_workflow"]))
        last = discover_new_run(baseline_ids, rows, plan)
        if last["status"] != "RUN_UNRESOLVED":
            return last
        if time.monotonic() >= deadline:
            return last
        sleep(min(2.0, max(0.0, deadline - time.monotonic())))


def dispatch_once(
    *,
    trial_id: str,
    repo_root: Path,
    ledger_dir: Path,
    plan_path: Path = DEFAULT_PLAN,
    manifest_path: Path = DEFAULT_MANIFEST,
    registry_path: Path = DEFAULT_REGISTRY,
    handoff_manifest_path: Path = DEFAULT_HANDOFF_MANIFEST,
    gh_executable: str | None = None,
    apply: bool = False,
    confirm_freeze: str | None = None,
    confirm_trial: str | None = None,
    confirm_model: str | None = None,
    confirm_client: str | None = None,
    confirm_memory: str | None = None,
    confirm_customization: str | None = None,
    poll_seconds: int = 90,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    pre = preflight(
        trial_id=trial_id,
        repo_root=repo_root,
        plan_path=plan_path,
        manifest_path=manifest_path,
        registry_path=registry_path,
        handoff_manifest_path=handoff_manifest_path,
        gh_executable=gh_executable,
    )
    if not apply:
        return {"mode": "DRY_RUN", **pre}

    spec = load_study_spec(manifest_path, root=repo_root)
    registry = load_registry(registry_path)
    validate_registry(registry, spec)
    plan = load_dispatch_plan(plan_path, spec, registry_path, handoff_manifest_path)
    trial = _plan_trial(plan, trial_id)
    config = _json_file(repo_root / spec.config_path)
    verify_operator_confirmations(
        config,
        freeze=confirm_freeze,
        trial=confirm_trial,
        trial_id=trial_id,
        model=confirm_model,
        client=confirm_client,
        memory=confirm_memory,
        customization=confirm_customization,
        spec=spec,
    )
    gh = _gh(gh_executable)

    ledger = prepare_dispatch_ledger(repo_root, ledger_dir, plan_path, plan)
    records = load_dispatch_records(ledger, plan)
    assert_dispatch_order(plan, trial_id, records)
    issue = _issue_from_gh(gh, spec.repository, int(trial["issue_number"]))
    verify_issue_surface(issue, trial, registry, spec)
    run_rows = _controller_runs(gh, spec.repository, str(plan["controller_workflow"]))
    matched = matching_runs(run_rows, plan)
    if any(row.get("status") != "completed" for row in matched):
        raise RuntimeError("matching frozen controller run became active before reservation")
    baseline_ids = sorted(int(row["databaseId"]) for row in matched)

    reservation = make_reservation_record(plan, trial_id, baseline_ids)
    reserve_commit = persist_dispatch_record(
        ledger, reservation, plan, action="reserve"
    )

    # Re-check the mutable public/runtime surfaces after the durable reservation.
    # Nothing external is dispatched if either changed during the reservation push.
    post_issue = _issue_from_gh(gh, spec.repository, int(trial["issue_number"]))
    try:
        verify_issue_surface(post_issue, trial, registry, spec)
    except RuntimeError as error:
        record = append_record_event(
            reservation,
            "ABORTED",
            reason="issue_changed_after_reservation_before_dispatch",
            detail_sha256=sha256_bytes(str(error).encode("utf-8")),
        )
        abort_commit = persist_dispatch_record(
            ledger, record, plan, action="abort-before-dispatch"
        )
        return {
            "mode": "APPLY_ABORTED_PRE_DISPATCH",
            "trial_id": trial_id,
            "reservation_commit": reserve_commit,
            "dispatch_record_commit": abort_commit,
            "reason": "issue_changed_after_reservation_before_dispatch",
            "external_dispatch_performed": False,
            "automatic_retry_allowed": False,
        }

    post_rows = _controller_runs(gh, spec.repository, str(plan["controller_workflow"]))
    external = discover_new_run(baseline_ids, post_rows, plan)
    if external["status"] != "RUN_UNRESOLVED":
        record = append_record_event(
            reservation,
            "RUN_AMBIGUOUS",
            candidate_run_ids=[row["databaseId"] for row in external["candidates"]],
            reason="matching_run_appeared_after_reservation_before_local_dispatch",
        )
        ambiguity_commit = persist_dispatch_record(
            ledger, record, plan, action="record-pre-dispatch-run-race"
        )
        return {
            "mode": "APPLY_BLOCKED_PRE_DISPATCH",
            "trial_id": trial_id,
            "reservation_commit": reserve_commit,
            "dispatch_record_commit": ambiguity_commit,
            "run_discovery": external,
            "external_dispatch_performed": False,
            "automatic_retry_allowed": False,
        }

    command_result = _dispatch_command(gh, spec, plan, trial)
    command_state = (
        "DISPATCH_SUBMITTED"
        if command_result.returncode == 0
        else "DISPATCH_COMMAND_FAILED_UNCERTAIN"
    )
    stdout_bytes = (command_result.stdout or "").encode("utf-8")
    stderr_bytes = (command_result.stderr or "").encode("utf-8")
    record = append_record_event(
        reservation,
        command_state,
        returncode=command_result.returncode,
        stdout_sha256=sha256_bytes(stdout_bytes),
        stdout_bytes=len(stdout_bytes),
        stderr_sha256=sha256_bytes(stderr_bytes),
        stderr_bytes=len(stderr_bytes),
    )
    command_commit = persist_dispatch_record(
        ledger, record, plan, action="submit"
    )

    discovery = _poll_for_new_run(
        gh, spec, plan, baseline_ids, poll_seconds=poll_seconds
    )
    if discovery["status"] == "RUN_IDENTIFIED":
        run = discovery["run"]
        record = append_record_event(
            record,
            "RUN_IDENTIFIED",
            run_id=run["databaseId"],
            run_url=run.get("url"),
            run_created_at=run.get("createdAt"),
            run_status=run.get("status"),
        )
        final_action = "identify-run"
    else:
        record = append_record_event(
            record,
            discovery["status"],
            candidate_run_ids=[row["databaseId"] for row in discovery["candidates"]],
        )
        final_action = "record-unresolved-run"
    final_commit = persist_dispatch_record(
        ledger, record, plan, action=final_action
    )
    return {
        "mode": "APPLY",
        "trial_id": trial_id,
        "issue_url": trial["issue_url"],
        "handoff_path": trial["handoff_path"],
        "handoff_sha256": trial["handoff_sha256"],
        "reservation_commit": reserve_commit,
        "dispatch_command_commit": command_commit,
        "dispatch_record_commit": final_commit,
        "dispatch_command_returncode": command_result.returncode,
        "run_discovery": discovery,
        "automatic_retry_allowed": False,
    }


def _record_run_id(record: Mapping[str, Any]) -> int | None:
    for event in reversed(record.get("events", [])):
        if event.get("state") == "RUN_IDENTIFIED" and isinstance(event.get("run_id"), int):
            return int(event["run_id"])
    return None


def recover_run(
    *,
    trial_id: str,
    repo_root: Path,
    ledger_dir: Path,
    plan_path: Path = DEFAULT_PLAN,
    manifest_path: Path = DEFAULT_MANIFEST,
    registry_path: Path = DEFAULT_REGISTRY,
    handoff_manifest_path: Path = DEFAULT_HANDOFF_MANIFEST,
    gh_executable: str | None = None,
) -> dict[str, Any]:
    spec = load_study_spec(manifest_path, root=repo_root)
    plan = load_dispatch_plan(plan_path, spec, registry_path, handoff_manifest_path)
    gh = _gh(gh_executable)
    ledger = prepare_dispatch_ledger(repo_root, ledger_dir, plan_path, plan)
    records = load_dispatch_records(ledger, plan)
    if trial_id not in records:
        raise RuntimeError("no durable reservation exists for this trial")
    record = records[trial_id]
    state = record_state(record)
    if state in {"RUN_IDENTIFIED", "READY_OBSERVED", "REVEALED", "COLLECTED", "ABORTED"}:
        return {"trial_id": trial_id, "state": state, "run_id": _record_run_id(record)}
    rows = _controller_runs(gh, spec.repository, str(plan["controller_workflow"]))
    discovery = discover_new_run(record["baseline_run_ids"], rows, plan)
    new_state = discovery["status"]
    if state == new_state:
        return {"trial_id": trial_id, "state": state, "run_discovery": discovery}
    if new_state == "RUN_IDENTIFIED":
        run = discovery["run"]
        updated = append_record_event(
            record,
            "RUN_IDENTIFIED",
            run_id=run["databaseId"],
            run_url=run.get("url"),
            run_created_at=run.get("createdAt"),
            run_status=run.get("status"),
            recovery=True,
        )
        action = "recover-run"
    else:
        updated = append_record_event(
            record,
            new_state,
            candidate_run_ids=[row["databaseId"] for row in discovery["candidates"]],
            recovery=True,
        )
        action = "record-recovery-state"
    commit = persist_dispatch_record(ledger, updated, plan, action=action)
    return {
        "trial_id": trial_id,
        "state": record_state(updated),
        "dispatch_record_commit": commit,
        "run_discovery": discovery,
    }


def _issue_phase_presence(issue: Mapping[str, Any]) -> dict[str, bool]:
    comments = issue.get("comments")
    if not isinstance(comments, list):
        comments = []
    bodies = [str(row.get("body") or "") for row in comments if isinstance(row, dict)]
    return {
        "ready": any(body.startswith("SAIS_RCL_READY ") for body in bodies),
        "forecast0": any(body.startswith("SAIS_RCL_FORECAST0 ") for body in bodies),
        "probe": any(body.startswith("SAIS_RCL_PROBE ") for body in bodies),
        "forecast1": any(body.startswith("SAIS_RCL_FORECAST1 ") for body in bodies),
        "action": any(body.startswith("SAIS_RCL_ACTION ") for body in bodies),
        "diagnosis": any(body.startswith("SAIS_RCL_DIAGNOSIS ") for body in bodies),
        "reveal": any(body.startswith("SAIS_RCL_REVEAL ") for body in bodies),
    }


def _run_view(gh: str, repository: str, run_id: int) -> dict[str, Any]:
    raw = _run([
        gh, "run", "view", str(run_id), "--repo", repository,
        "--json", (
            "databaseId,workflowName,event,headBranch,headSha,createdAt,"
            "startedAt,status,conclusion,url,displayTitle"
        ),
    ])
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("GitHub run view returned non-object")
    return value


def reconcile_trial(
    *,
    trial_id: str,
    repo_root: Path,
    ledger_dir: Path,
    plan_path: Path = DEFAULT_PLAN,
    manifest_path: Path = DEFAULT_MANIFEST,
    registry_path: Path = DEFAULT_REGISTRY,
    handoff_manifest_path: Path = DEFAULT_HANDOFF_MANIFEST,
    gh_executable: str | None = None,
) -> dict[str, Any]:
    spec = load_study_spec(manifest_path, root=repo_root)
    registry = load_registry(registry_path)
    validate_registry(registry, spec)
    plan = load_dispatch_plan(plan_path, spec, registry_path, handoff_manifest_path)
    trial = _plan_trial(plan, trial_id)
    gh = _gh(gh_executable)
    ledger = prepare_dispatch_ledger(repo_root, ledger_dir, plan_path, plan)
    records = load_dispatch_records(ledger, plan)
    if trial_id not in records:
        raise RuntimeError("trial has no durable dispatch reservation")
    record = records[trial_id]
    state = record_state(record)
    if state in TERMINAL_STATES:
        return {"trial_id": trial_id, "state": state, "run_id": _record_run_id(record)}
    run_id = _record_run_id(record)
    if run_id is None:
        raise RuntimeError("run identity is unresolved; use recover-run first")
    run = _run_view(gh, spec.repository, run_id)
    if (
        run.get("event") != "workflow_dispatch"
        or run.get("headBranch") != plan["controller_tag"]
        or run.get("headSha") != plan["controller_commit"]
    ):
        raise RuntimeError("recorded run no longer matches the frozen controller identity")
    issue = _issue_from_gh(gh, spec.repository, int(trial["issue_number"]))
    phases = _issue_phase_presence(issue)
    updated = record
    actions: list[str] = []
    if phases["reveal"] and state in {"RUN_IDENTIFIED", "READY_OBSERVED"}:
        updated = append_record_event(
            updated, "REVEALED", run_id=run_id, run_url=run.get("url")
        )
        actions.append("reveal")
    elif phases["ready"] and state == "RUN_IDENTIFIED":
        updated = append_record_event(
            updated, "READY_OBSERVED", run_id=run_id, run_url=run.get("url")
        )
        actions.append("ready")
    state_after = record_state(updated)
    if (
        state_after not in TERMINAL_STATES
        and run.get("status") == "completed"
        and run.get("conclusion") != "success"
        and not phases["reveal"]
    ):
        updated = append_record_event(
            updated,
            "ABORTED",
            run_id=run_id,
            run_url=run.get("url"),
            run_conclusion=run.get("conclusion"),
            reason="controller_run_completed_without_reveal",
        )
        actions.append("abort")
    commit = None
    if updated != record:
        commit = persist_dispatch_record(
            ledger, updated, plan, action="reconcile-" + "-".join(actions)
        )
    return {
        "trial_id": trial_id,
        "state": record_state(updated),
        "run": run,
        "issue_phases": phases,
        "dispatch_record_commit": commit,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail-closed dispatcher for one frozen RCL-PC trial"
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--handoff-manifest", type=Path, default=DEFAULT_HANDOFF_MANIFEST)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--ledger-dir", type=Path, default=Path("/tmp/sais-rcl-dispatch-ledger"))
    parser.add_argument("--gh-executable")
    sub = parser.add_subparsers(dest="command", required=True)

    pre = sub.add_parser("preflight")
    pre.add_argument("trial_id")

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("trial_id")
    dispatch.add_argument("--apply", action="store_true")
    dispatch.add_argument("--confirm-freeze")
    dispatch.add_argument("--confirm-trial")
    dispatch.add_argument("--confirm-model")
    dispatch.add_argument("--confirm-client")
    dispatch.add_argument("--confirm-memory")
    dispatch.add_argument("--confirm-customization")
    dispatch.add_argument("--poll-seconds", type=int, default=90)

    recover = sub.add_parser("recover-run")
    recover.add_argument("trial_id")

    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("trial_id")

    args = parser.parse_args()
    common = {
        "repo_root": args.repo_root,
        "manifest_path": args.manifest,
        "registry_path": args.registry,
        "handoff_manifest_path": args.handoff_manifest,
        "gh_executable": args.gh_executable,
    }
    if args.command == "preflight":
        report = preflight(trial_id=args.trial_id, plan_path=args.plan, **common)
    elif args.command == "dispatch":
        report = dispatch_once(
            trial_id=args.trial_id,
            ledger_dir=args.ledger_dir,
            plan_path=args.plan,
            apply=args.apply,
            confirm_freeze=args.confirm_freeze,
            confirm_trial=args.confirm_trial,
            confirm_model=args.confirm_model,
            confirm_client=args.confirm_client,
            confirm_memory=args.confirm_memory,
            confirm_customization=args.confirm_customization,
            poll_seconds=args.poll_seconds,
            **common,
        )
    elif args.command == "recover-run":
        report = recover_run(
            trial_id=args.trial_id,
            ledger_dir=args.ledger_dir,
            plan_path=args.plan,
            **common,
        )
    else:
        report = reconcile_trial(
            trial_id=args.trial_id,
            ledger_dir=args.ledger_dir,
            plan_path=args.plan,
            **common,
        )
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
