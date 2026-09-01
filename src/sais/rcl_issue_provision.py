"""Provision empty public GitHub issue surfaces for frozen RCL-PC trials.

This module intentionally cannot dispatch the controller. Issue creation is
execution preparation only and must keep included_trials_started == 0.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping, Sequence

from .rcl_pc_analysis import DEFAULT_MANIFEST, load_study_spec
from .rcl_registry import (
    issue_title,
    load_registry,
    render_issue_body,
    save_registry,
    transition_trial,
    validate_registry,
)

ISSUE_MARKER_RE = re.compile(r"<!-- sais-rcl-pc-trial:(PC-RCL-[0-9]{3}) -->")


def _run(command: Sequence[str]) -> str:
    result = subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _gh(executable: str | None = None) -> str:
    value = executable or shutil.which("gh")
    if not value:
        raise RuntimeError("GitHub CLI `gh` is required for --apply")
    return value


def _verify_local_anchor(registry: Mapping[str, Any]) -> None:
    tag = str(registry["freeze_tag"])
    expected = str(registry["freeze_commit"])
    actual = _run(["git", "rev-list", "-n", "1", tag])
    if actual != expected:
        raise RuntimeError(
            f"freeze tag {tag} resolves to {actual}, expected {expected}"
        )
    controller_tag = str(registry["controller_tag"])
    expected_controller = str(registry["controller_commit"])
    actual_controller = _run(["git", "rev-list", "-n", "1", controller_tag])
    if actual_controller != expected_controller:
        raise RuntimeError(
            f"controller tag {controller_tag} resolves to {actual_controller}, "
            f"expected {expected_controller}"
        )
    config_commit = str(registry["configuration_commit"])
    try:
        _run(["git", "merge-base", "--is-ancestor", config_commit, expected])
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            "configuration source commit is not an ancestor of the frozen study"
        ) from error


def _existing_issues(gh: str, repository: str) -> list[dict[str, Any]]:
    raw = _run([
        gh, "issue", "list", "--repo", repository,
        "--state", "all", "--limit", "1000",
        "--json", "number,title,url,body,comments",
    ])
    value = json.loads(raw or "[]")
    if not isinstance(value, list):
        raise RuntimeError("GitHub issue listing returned a non-list value")
    return [item for item in value if isinstance(item, dict)]


def _issue_trial_id(issue: Mapping[str, Any]) -> str | None:
    body = str(issue.get("body") or "")
    match = ISSUE_MARKER_RE.search(body)
    return match.group(1) if match else None


def _comments_empty(issue: Mapping[str, Any]) -> bool:
    comments = issue.get("comments")
    if comments is None:
        return True
    if isinstance(comments, int) and not isinstance(comments, bool):
        return comments == 0
    if isinstance(comments, list):
        return len(comments) == 0
    if isinstance(comments, Mapping):
        nodes = comments.get("nodes")
        if isinstance(nodes, list):
            return len(nodes) == 0
        total = comments.get("totalCount")
        if isinstance(total, int):
            return total == 0
    return False


def _validate_existing_issue(
    issue: Mapping[str, Any],
    trial_id: str,
    registry: Mapping[str, Any],
) -> tuple[int, str]:
    expected_title = issue_title(trial_id)
    trial = next(item for item in registry["trials"] if item["trial_id"] == trial_id)
    body_trial = dict(trial)
    body_trial["status"] = "NOT_CREATED"
    expected_body = render_issue_body(body_trial, registry)
    if issue.get("title") != expected_title:
        raise RuntimeError(f"existing surface {trial_id} has unexpected title")
    if str(issue.get("body") or "") != expected_body:
        raise RuntimeError(f"existing surface {trial_id} has unexpected body")
    if not _comments_empty(issue):
        raise RuntimeError(f"existing surface {trial_id} has unexpected comments")
    number = issue.get("number")
    url = issue.get("url")
    if not isinstance(number, int) or number < 1 or not isinstance(url, str):
        raise RuntimeError(f"existing surface {trial_id} lacks valid GitHub identity")
    return number, url


def _create_issue(
    gh: str,
    repository: str,
    title: str,
    body: str,
) -> tuple[int, str]:
    url = _run([
        gh, "issue", "create", "--repo", repository,
        "--title", title, "--body", body,
    ])
    match = re.search(r"/issues/([0-9]+)$", url)
    if not match:
        raise RuntimeError(f"could not parse issue number from GitHub output: {url}")
    return int(match.group(1)), url


def provision(
    registry_path: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    apply: bool = False,
    confirmation: str | None = None,
    gh_executable: str | None = None,
) -> dict[str, Any]:
    spec = load_study_spec(manifest_path)
    registry = load_registry(registry_path)
    validate_registry(registry, spec)
    _verify_local_anchor(registry)
    if registry["included_trials_started"] != 0:
        raise RuntimeError("issue provisioning is forbidden after any trial start")

    planned = [
        item for item in registry["trials"] if item["status"] == "NOT_CREATED"
    ]
    if not apply:
        return {
            "mode": "DRY_RUN",
            "planned_count": len(planned),
            "planned_ids": [item["trial_id"] for item in planned],
            "included_trials_started": registry["included_trials_started"],
        }

    if confirmation != spec.freeze_tag:
        raise RuntimeError(
            "--apply requires --confirm-freeze-tag equal to the frozen tag"
        )
    gh = _gh(gh_executable)
    _run([gh, "auth", "status", "--hostname", "github.com"])
    issues = _existing_issues(gh, spec.repository)
    by_trial: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        trial_id = _issue_trial_id(issue)
        if trial_id is not None:
            by_trial.setdefault(trial_id, []).append(issue)
    expected_ids = {item["trial_id"] for item in registry["trials"]}
    unexpected_markers = sorted(set(by_trial) - expected_ids)
    if unexpected_markers:
        raise RuntimeError(
            "unexpected RCL-PC issue markers: " + ", ".join(unexpected_markers)
        )
    duplicate_markers = sorted(
        trial_id for trial_id, rows in by_trial.items() if len(rows) > 1
    )
    if duplicate_markers:
        raise RuntimeError(
            "multiple existing issue surfaces for: " + ", ".join(duplicate_markers)
        )
    for trial in registry["trials"]:
        if trial["status"] != "ISSUE_CREATED":
            continue
        trial_id = str(trial["trial_id"])
        matches = by_trial.get(trial_id, [])
        if len(matches) != 1:
            raise RuntimeError(f"registered issue surface missing for {trial_id}")
        number, url = _validate_existing_issue(matches[0], trial_id, registry)
        if number != trial["issue_number"] or url != trial["issue_url"]:
            raise RuntimeError(f"registered issue identity mismatch for {trial_id}")
    created = 0
    reconciled = 0
    for trial in list(planned):
        trial_id = str(trial["trial_id"])
        matches = by_trial.get(trial_id, [])
        if matches:
            number, url = _validate_existing_issue(matches[0], trial_id, registry)
            reconciled += 1
        else:
            number, url = _create_issue(
                gh,
                spec.repository,
                issue_title(trial_id),
                render_issue_body(trial, registry),
            )
            created += 1
        registry = transition_trial(
            registry,
            spec,
            trial_id,
            "ISSUE_CREATED",
            fields={"issue_number": number, "issue_url": url},
        )
        save_registry(registry_path, registry)

    validate_registry(registry, spec)
    if registry["included_trials_started"] != 0:
        raise RuntimeError("issue provisioning must not start included trials")
    return {
        "mode": "APPLY",
        "created": created,
        "reconciled": reconciled,
        "included_trials_started": registry["included_trials_started"],
        "registry": str(registry_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision empty GitHub issue surfaces for frozen RCL-PC trials"
    )
    parser.add_argument("registry", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-freeze-tag")
    parser.add_argument("--gh-executable")
    args = parser.parse_args()
    report = provision(
        args.registry,
        args.manifest,
        apply=args.apply,
        confirmation=args.confirm_freeze_tag,
        gh_executable=args.gh_executable,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
