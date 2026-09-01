"""Fail-closed execution registry for the frozen RCL-PC block."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .rcl_pc_analysis import DEFAULT_MANIFEST, StudySpec, load_study_spec

REGISTRY_VERSION = "SMI-CP/RCL-PC/REGISTRY/1"
CONTROLLER_TAG = "sais-rcl-bound-controller-v1"
NOT_STARTED_STATUSES = {"NOT_CREATED", "ISSUE_CREATED"}
STARTED_STATUSES = {
    "DISPATCH_ATTEMPTED",
    "READY_PUBLISHED",
    "REVEALED",
    "ABORTED",
    "COLLECTED",
}
ALL_STATUSES = NOT_STARTED_STATUSES | STARTED_STATUSES
ALLOWED_TRANSITIONS = {
    "NOT_CREATED": {"ISSUE_CREATED"},
    "ISSUE_CREATED": {"DISPATCH_ATTEMPTED"},
    "DISPATCH_ATTEMPTED": {"READY_PUBLISHED", "ABORTED"},
    "READY_PUBLISHED": {"REVEALED", "ABORTED"},
    "REVEALED": {"COLLECTED"},
    "ABORTED": set(),
    "COLLECTED": set(),
}
FORBIDDEN_TRIAL_KEYS = {
    "condition",
    "legibility",
    "key",
    "trial_key",
    "assignment",
    "payload_hash",
}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
TRANSITION_FIELDS = {
    "issue_number", "issue_url", "controller_run_id",
    "ready_comment_id", "reveal_comment_id", "public_bundle_path",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_registry(
    spec: StudySpec,
    *,
    freeze_commit: str,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    if not HEX40.fullmatch(freeze_commit):
        raise ValueError("freeze_commit must be a full lowercase Git SHA")
    created = created_at_utc or utc_now()
    trials = [
        {
            "trial_id": trial_id,
            "status": "NOT_CREATED",
            "issue_number": None,
            "issue_url": None,
            "controller_run_id": None,
            "ready_comment_id": None,
            "reveal_comment_id": None,
            "public_bundle_path": None,
            "last_transition_at_utc": None,
        }
        for trial_id in spec.expected_ids
    ]
    registry = {
        "registry_version": REGISTRY_VERSION,
        "study_id": "RCL-PC",
        "freeze_tag": spec.freeze_tag,
        "freeze_commit": freeze_commit,
        "controller_tag": CONTROLLER_TAG,
        "controller_commit": spec.controller_code_sha,
        "repository": spec.repository,
        "block_id": spec.block_id,
        "configuration_commit": spec.config_commit,
        "configuration_path": spec.config_path,
        "configuration_binding_hash": spec.expected_binding_hash,
        "created_at_utc": created,
        "updated_at_utc": created,
        "included_trials_started": 0,
        "trials": trials,
        "events": [],
    }
    validate_registry(registry, spec)
    return registry


def _trial_map(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    trials = registry.get("trials")
    if not isinstance(trials, list):
        raise ValueError("registry trials must be a list")
    out: dict[str, dict[str, Any]] = {}
    for item in trials:
        if not isinstance(item, dict) or not isinstance(item.get("trial_id"), str):
            raise ValueError("every trial must be an object with trial_id")
        trial_id = str(item["trial_id"])
        if trial_id in out:
            raise ValueError(f"duplicate trial id: {trial_id}")
        out[trial_id] = item
    return out


def _utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    offset = parsed.utcoffset()
    return offset is not None and offset.total_seconds() == 0


def _replay_events(
    registry: Mapping[str, Any], spec: StudySpec
) -> tuple[dict[str, dict[str, Any]], bool]:
    state = {
        trial_id: {
            "status": "NOT_CREATED",
            "issue_number": None,
            "issue_url": None,
            "controller_run_id": None,
            "ready_comment_id": None,
            "reveal_comment_id": None,
            "public_bundle_path": None,
            "last_transition_at_utc": None,
        }
        for trial_id in spec.expected_ids
    }
    events = registry.get("events")
    if not isinstance(events, list):
        return state, False
    valid = True
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            valid = False
            continue
        trial_id = event.get("trial_id")
        if trial_id not in state or not _utc_timestamp(event.get("at_utc")):
            valid = False
            continue
        current = state[str(trial_id)]
        old_status = current["status"]
        new_status = event.get("to_status")
        fields = event.get("fields")
        if event.get("from_status") != old_status:
            valid = False
        if new_status not in ALLOWED_TRANSITIONS.get(str(old_status), set()):
            valid = False
        if not isinstance(fields, dict):
            valid = False
            fields = {}
        if set(fields) - TRANSITION_FIELDS or FORBIDDEN_TRIAL_KEYS.intersection(fields):
            valid = False
        current.update(fields)
        current["status"] = new_status
        current["last_transition_at_utc"] = event.get("at_utc")
    return state, valid


def validate_registry(
    registry: Mapping[str, Any],
    spec: StudySpec,
) -> dict[str, bool]:
    trials = _trial_map(registry)
    expected_ids = tuple(spec.expected_ids)
    actual_ids = tuple(trials)
    issue_numbers = [
        item["issue_number"]
        for item in trials.values()
        if item.get("issue_number") is not None
    ]
    checks = {
        "registry_version": registry.get("registry_version") == REGISTRY_VERSION,
        "study_id": registry.get("study_id") == "RCL-PC",
        "freeze_tag": registry.get("freeze_tag") == spec.freeze_tag,
        "freeze_commit_format": bool(
            isinstance(registry.get("freeze_commit"), str)
            and HEX40.fullmatch(str(registry["freeze_commit"]))
        ),
        "controller_tag": registry.get("controller_tag") == CONTROLLER_TAG,
        "controller_commit": registry.get("controller_commit") == spec.controller_code_sha,
        "repository": registry.get("repository") == spec.repository,
        "block_id": registry.get("block_id") == spec.block_id,
        "configuration_commit": registry.get("configuration_commit") == spec.config_commit,
        "configuration_path": registry.get("configuration_path") == spec.config_path,
        "configuration_binding_hash": (
            registry.get("configuration_binding_hash") == spec.expected_binding_hash
        ),
        "created_at_utc": _utc_timestamp(registry.get("created_at_utc")),
        "updated_at_utc": _utc_timestamp(registry.get("updated_at_utc")),
        "trial_ids_exact": actual_ids == expected_ids,
        "issue_numbers_unique": len(issue_numbers) == len(set(issue_numbers)),
    }
    trial_checks = []
    started = 0
    for trial_id in expected_ids:
        item = trials[trial_id]
        status = item.get("status")
        valid = status in ALL_STATUSES and not FORBIDDEN_TRIAL_KEYS.intersection(item)
        issue_number = item.get("issue_number")
        issue_url = item.get("issue_url")
        if status == "NOT_CREATED":
            valid &= issue_number is None and issue_url is None
        else:
            valid &= isinstance(issue_number, int) and issue_number > 0
            valid &= issue_url == f"https://github.com/{spec.repository}/issues/{issue_number}"
        if status in STARTED_STATUSES:
            started += 1
        if status in NOT_STARTED_STATUSES:
            valid &= item.get("controller_run_id") is None
            valid &= item.get("ready_comment_id") is None
            valid &= item.get("reveal_comment_id") is None
            valid &= item.get("public_bundle_path") is None
        if status in STARTED_STATUSES:
            valid &= isinstance(item.get("controller_run_id"), int)
        if status in {"READY_PUBLISHED", "REVEALED", "COLLECTED"}:
            valid &= isinstance(item.get("ready_comment_id"), int)
        if status in {"REVEALED", "COLLECTED"}:
            valid &= isinstance(item.get("reveal_comment_id"), int)
        if status == "COLLECTED":
            valid &= isinstance(item.get("public_bundle_path"), str) and bool(item.get("public_bundle_path"))
        if item.get("last_transition_at_utc") is not None:
            valid &= _utc_timestamp(item.get("last_transition_at_utc"))
        trial_checks.append(bool(valid))
    checks["trial_records_valid"] = all(trial_checks)
    checks["started_count_exact"] = registry.get("included_trials_started") == started
    replayed, replay_valid = _replay_events(registry, spec)
    checks["event_replay_valid"] = replay_valid
    checks["event_replay_matches_trials"] = replay_valid and all(
        replayed[trial_id] == {
            key: trials[trial_id].get(key)
            for key in replayed[trial_id]
        }
        for trial_id in expected_ids
    )
    events = registry.get("events")
    checks["updated_at_matches_events"] = (
        isinstance(events, list)
        and (
            (not events and registry.get("updated_at_utc") == registry.get("created_at_utc"))
            or (events and registry.get("updated_at_utc") == events[-1].get("at_utc"))
        )
    )
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise ValueError("invalid registry: " + failed)
    return checks

def transition_trial(
    registry: Mapping[str, Any],
    spec: StudySpec,
    trial_id: str,
    new_status: str,
    *,
    at_utc: str | None = None,
    fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a validated registry copy with one append-only transition."""
    validate_registry(registry, spec)
    if new_status not in ALL_STATUSES:
        raise ValueError(f"unknown status: {new_status}")
    updated = deepcopy(dict(registry))
    trials = _trial_map(updated)
    if trial_id not in trials:
        raise ValueError(f"unexpected trial id: {trial_id}")
    item = trials[trial_id]
    old_status = str(item["status"])
    if new_status not in ALLOWED_TRANSITIONS[old_status]:
        raise ValueError(f"forbidden transition: {old_status} -> {new_status}")
    supplied = dict(fields or {})
    if FORBIDDEN_TRIAL_KEYS.intersection(supplied):
        raise ValueError("hidden assignment material is forbidden in the registry")
    unknown = set(supplied) - TRANSITION_FIELDS
    if unknown:
        raise ValueError("unknown transition fields: " + ", ".join(sorted(unknown)))
    item.update(supplied)
    item["status"] = new_status
    timestamp = at_utc or utc_now()
    item["last_transition_at_utc"] = timestamp
    event = {
        "sequence": len(updated["events"]) + 1,
        "at_utc": timestamp,
        "trial_id": trial_id,
        "from_status": old_status,
        "to_status": new_status,
        "fields": supplied,
    }
    updated["events"].append(event)
    updated["updated_at_utc"] = timestamp
    updated["included_trials_started"] = sum(
        trial["status"] in STARTED_STATUSES for trial in updated["trials"]
    )
    validate_registry(updated, spec)
    return updated


def issue_title(trial_id: str) -> str:
    return f"[RCL-PC] {trial_id} — NOT STARTED"


def render_issue_body(
    trial: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> str:
    trial_id = str(trial["trial_id"])
    if trial.get("status") != "NOT_CREATED":
        raise ValueError("issue body can be rendered only before issue creation")
    return (
        f"<!-- sais-rcl-pc-trial:{trial_id} -->\n"
        f"# RCL-PC included trial surface\n\n"
        f"**Trial identifier:** `{trial_id}`  \n"
        f"**Execution status:** `NOT STARTED`  \n"
        f"**Frozen block:** `{registry['block_id']}`\n\n"
        "Creating this issue does **not** start the trial. No controller has been "
        "dispatched, no runtime assignment exists, and no subject response has "
        "been requested.\n\n"
        "## Frozen references\n\n"
        f"- study freeze: `{registry['freeze_tag']}` at "
        f"`{registry['freeze_commit']}`\n"
        f"- controller freeze: `{registry['controller_tag']}` at "
        f"`{registry['controller_commit']}`\n"
        f"- configuration source: `{registry['configuration_commit']}`:"
        f"`{registry['configuration_path']}`\n"
        f"- configuration binding: `{registry['configuration_binding_hash']}`\n\n"
        "## Execution boundary\n\n"
        "This issue is an empty public observation surface. It must remain free "
        "of manual comments until the frozen runbook intentionally dispatches "
        "the controller and a fresh subject conversation is opened. This design "
        "conversation is not an eligible subject context.\n\n"
        "Randomization occurs only after the first forecast is publicly bound. "
        "The issue body contains no capability or legibility assignment.\n"
    )


def planned_issues(
    registry: Mapping[str, Any],
    spec: StudySpec,
) -> list[dict[str, str]]:
    validate_registry(registry, spec)
    return [
        {
            "trial_id": item["trial_id"],
            "title": issue_title(item["trial_id"]),
            "body": render_issue_body(item, registry),
        }
        for item in registry["trials"]
        if item["status"] == "NOT_CREATED"
    ]


def load_registry(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(path: Path, registry: Mapping[str, Any]) -> None:
    rendered = json.dumps(registry, indent=2, sort_keys=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the frozen RCL-PC registry")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--freeze-commit", required=True)
    init_parser.add_argument("--output", type=Path, required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("registry", type=Path)

    plan_parser = subparsers.add_parser("plan-issues")
    plan_parser.add_argument("registry", type=Path)
    plan_parser.add_argument("--output", type=Path)

    args = parser.parse_args()
    spec = load_study_spec(args.manifest)
    if args.command == "init":
        registry = new_registry(spec, freeze_commit=args.freeze_commit)
        save_registry(args.output, registry)
        print(json.dumps({"created": str(args.output), "trials": len(spec.expected_ids)}))
        return

    registry = load_registry(args.registry)
    validate_registry(registry, spec)
    if args.command == "validate":
        print(json.dumps({"valid": True, "trials": len(registry["trials"])}))
        return

    plan = planned_issues(registry, spec)
    rendered = json.dumps(plan, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
