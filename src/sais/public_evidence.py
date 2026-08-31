"""Collect and verify public GitHub evidence for sealed controller trials."""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from .ephemeral_controller import object_hash, verify_sealed_trial

READY_PREFIX = "SAIS_CONTROLLER_READY "
FORECAST0_PREFIX = "SAIS_FORECAST0 "
COMMIT_PREFIX = "SAIS_COMMIT "
PROBE_PREFIX = "SAIS_PROBE "
FORECAST1_PREFIX = "SAIS_FORECAST1 "
ACTION_PREFIX = "SAIS_ACTION "
DIAGNOSIS_PREFIX = "SAIS_DIAGNOSIS "
SEAL_PREFIX = "SAIS_SEAL "
REVEAL_PREFIX = "SAIS_REVEAL "

PREFIXES = (
    READY_PREFIX,
    FORECAST0_PREFIX,
    COMMIT_PREFIX,
    PROBE_PREFIX,
    FORECAST1_PREFIX,
    ACTION_PREFIX,
    DIAGNOSIS_PREFIX,
    SEAL_PREFIX,
    REVEAL_PREFIX,
)
CONTROLLER_PREFIXES = (
    READY_PREFIX,
    COMMIT_PREFIX,
    PROBE_PREFIX,
    ACTION_PREFIX,
    SEAL_PREFIX,
    REVEAL_PREFIX,
)


class PublicEvidenceError(RuntimeError):
    pass


def git_blob_sha1(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()


def decode_github_base64(value: Any, *, source: str) -> bytes:
    """Decode GitHub Contents API base64 while accepting only ASCII wrapping."""
    if not isinstance(value, str):
        raise PublicEvidenceError(f"{source} had no string base64 content")
    normalized = value.translate(str.maketrans("", "", " \t\r\n"))
    try:
        return base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError) as error:
        raise PublicEvidenceError(f"{source} was not valid base64") from error


def _payload(comment: dict[str, Any], prefix: str) -> dict[str, Any]:
    body = str(comment.get("body", ""))
    if not body.startswith(prefix):
        raise ValueError(f"comment does not start with {prefix.strip()}")
    value = json.loads(body[len(prefix):])
    if not isinstance(value, dict):
        raise ValueError("comment payload must be an object")
    return value


def _indexed_controller_comments(
    comments: list[dict[str, Any]],
    controller_actor: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Select the single controller-authored phase record for each phase.

    Subject comments are selected later by the exact source-comment IDs sealed in
    the ledger. This preserves the controller's "first subsequent valid" rule:
    malformed or later alternative subject comments remain public but are not
    mistaken for the binding record.
    """
    found: dict[str, dict[str, Any]] = {}
    for prefix in CONTROLLER_PREFIXES:
        matches = [
            item
            for item in comments
            if str(item.get("body", "")).startswith(prefix)
            and (controller_actor is None or _author(item) == controller_actor)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected one controller {prefix.strip()} comment, found {len(matches)}"
            )
        found[prefix] = matches[0]
    return found


def _comment_by_id(comments: list[dict[str, Any]], comment_id: Any) -> dict[str, Any]:
    target = int(comment_id)
    matches = [item for item in comments if int(item.get("id", -1)) == target]
    if len(matches) != 1:
        raise ValueError(f"expected one comment id {target}, found {len(matches)}")
    return matches[0]


def _author(comment: dict[str, Any]) -> str | None:
    user = comment.get("user")
    return user.get("login") if isinstance(user, dict) else comment.get("author")


def _source_matches(comment: dict[str, Any], source: dict[str, Any]) -> bool:
    return (
        int(comment.get("id", -1)) == int(source.get("id", -2))
        and _author(comment) == source.get("author")
        and comment.get("created_at") == source.get("created_at")
    )


def verify_public_trial(
    bundle: dict[str, Any],
    *,
    expected_repository: str | None = None,
    expected_controller_actor: str | None = None,
) -> dict[str, bool]:
    """Verify retained public evidence and the sealed trial offline.

    A PASS establishes internal consistency of the retained bundle. Independent
    live recollection is still required to confirm that the referenced GitHub
    issue and Git object exist in the frozen repository.
    """
    try:
        ledger = bundle["ledger"]
        reveal = bundle["reveal"]
        public = bundle["public_record"]
        comments = public["comments"]
        controller_actor = str(public["controller_actor"])
        indexed = _indexed_controller_comments(comments, controller_actor)
        raw_ledger = base64.b64decode(
            public["ledger_source"]["content_base64"], validate=True
        )
        parsed_raw_ledger = json.loads(raw_ledger)
        history = ledger["history"]
        commit_event, probe_event, perform_event, diagnosis_event = history
        commit_payload = commit_event["payload"]
        probe_payload = probe_event["payload"]
        perform_payload = perform_event["payload"]
        diagnosis_payload = diagnosis_event["payload"]

        ready_c = indexed[READY_PREFIX]
        commit_c = indexed[COMMIT_PREFIX]
        probe_c = indexed[PROBE_PREFIX]
        action_c = indexed[ACTION_PREFIX]
        seal_c = indexed[SEAL_PREFIX]
        reveal_c = indexed[REVEAL_PREFIX]
        forecast0_c = _comment_by_id(
            comments, commit_payload["source_comment"]["id"]
        )
        forecast1_c = _comment_by_id(
            comments, perform_payload["source_comment"]["id"]
        )
        diagnosis_c = _comment_by_id(
            comments, diagnosis_payload["source_comment"]["id"]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        binascii.Error,
    ):
        return {"public_structure_valid": False, "valid": False}

    try:
        ready = _payload(ready_c, PREFIXES[0])
        forecast0 = _payload(forecast0_c, PREFIXES[1])
        commit = _payload(commit_c, PREFIXES[2])
        probe = _payload(probe_c, PREFIXES[3])
        forecast1 = _payload(forecast1_c, PREFIXES[4])
        action = _payload(action_c, PREFIXES[5])
        diagnosis = _payload(diagnosis_c, PREFIXES[6])
        seal = _payload(seal_c, PREFIXES[7])
        reveal_comment = _payload(reveal_c, PREFIXES[8])
    except (ValueError, json.JSONDecodeError):
        return {"public_structure_valid": False, "valid": False}

    trial_id = str(ledger["trial_id"])
    code_sha = str(ledger["controller_code_sha"])
    subject = str(ledger["subject_login"])
    repository = public.get("repository")
    comment_ids = [int(item["id"]) for item in comments]
    positions = {comment_id: index for index, comment_id in enumerate(comment_ids)}
    selected = {
        READY_PREFIX: ready_c,
        FORECAST0_PREFIX: forecast0_c,
        COMMIT_PREFIX: commit_c,
        PROBE_PREFIX: probe_c,
        FORECAST1_PREFIX: forecast1_c,
        ACTION_PREFIX: action_c,
        DIAGNOSIS_PREFIX: diagnosis_c,
        SEAL_PREFIX: seal_c,
        REVEAL_PREFIX: reveal_c,
    }
    ordered_ids = [int(selected[prefix]["id"]) for prefix in PREFIXES]

    source = public["ledger_source"]

    expected_commit_comment = {
        "commitment": commit_payload["commitment"],
        "controller_code_sha": code_sha,
        "event_hash": commit_event["event_hash"],
        "forecast0_hash": commit_payload["forecast0_hash"],
    }
    expected_probe_comment = {
        "probe_response": probe_payload["probe_response"],
        "trial_id": trial_id,
    }
    expected_action_comment = {
        **perform_payload["action"],
        "trial_id": trial_id,
    }
    expected_seal_comment = {
        "controller_code_sha": code_sha,
        "ledger_commit": reveal["ledger_commit"],
        "ledger_hash": reveal["ledger_hash"],
        "trial_id": trial_id,
    }

    crypto = verify_sealed_trial(ledger, reveal)
    checks: dict[str, bool] = {
        f"crypto_{name}": bool(value)
        for name, value in crypto.items()
        if name != "valid"
    }
    checks.update({
        "public_structure_valid": True,
        "cryptographic_trial_valid": bool(crypto.get("valid")),
        "repository_present": isinstance(repository, str) and repository.count("/") == 1,
        "repository_matches_expected": (
            expected_repository is None or repository == expected_repository
        ),
        "controller_actor_present": bool(controller_actor),
        "controller_actor_matches_expected": (
            expected_controller_actor is None
            or controller_actor == expected_controller_actor
        ),
        "controller_subject_distinct": controller_actor != subject,
        "all_public_comment_ids_unique": len(comment_ids) == len(set(comment_ids)),
        "selected_comment_ids_unique": len(ordered_ids) == len(set(ordered_ids)),
        "protocol_comment_ids_increase": ordered_ids == sorted(ordered_ids),
        "public_protocol_order": [positions[item] for item in ordered_ids] == sorted(
            positions[item] for item in ordered_ids
        ),
        "controller_actor_consistent": all(
            _author(item) == controller_actor
            for item in (ready_c, commit_c, probe_c, action_c, seal_c, reveal_c)
        ),
        "subject_actor_consistent": all(
            _author(item) == subject
            for item in (forecast0_c, forecast1_c, diagnosis_c)
        ),
        "ready_comment_matches": ready == {
            "controller_code_sha": code_sha,
            "next": "SAIS_FORECAST0",
            "protocol_version": ledger["protocol_version"],
            "trial_id": trial_id,
        },
        "ready_comment_id_matches": int(ready_c["id"]) == int(
            commit_payload["ready_comment_id"]
        ),
        "forecast0_body_matches": forecast0 == commit_payload["forecast0"],
        "forecast0_source_matches": _source_matches(
            forecast0_c, commit_payload["source_comment"]
        ),
        "commit_body_matches": commit == expected_commit_comment,
        "probe_body_matches": probe == expected_probe_comment,
        "probe_source_matches": _source_matches(
            probe_c, probe_payload["controller_comment"]
        ),
        "forecast1_body_matches": forecast1 == perform_payload["forecast1"],
        "forecast1_source_matches": _source_matches(
            forecast1_c, perform_payload["source_comment"]
        ),
        "forecast1_probe_id_matches": int(probe_c["id"]) == int(
            perform_payload["probe_comment_id"]
        ),
        "action_body_matches": action == expected_action_comment,
        "action_comment_id_matches": int(action_c["id"]) == int(
            diagnosis_payload["action_comment_id"]
        ),
        "diagnosis_body_matches": diagnosis == diagnosis_payload["diagnosis"],
        "diagnosis_source_matches": _source_matches(
            diagnosis_c, diagnosis_payload["source_comment"]
        ),
        "seal_body_matches": seal == expected_seal_comment,
        "seal_comment_id_matches": int(seal_c["id"]) == int(
            reveal["seal_comment_id"]
        ),
        "seal_precedes_reveal": positions[int(seal_c["id"])] < positions[int(reveal_c["id"])],
        "reveal_body_matches": reveal_comment == reveal,
        "ledger_issue_matches": int(ledger["issue_number"]) == int(public["issue_number"]),
        "ledger_raw_json_matches": parsed_raw_ledger == ledger,
        "ledger_source_commit_matches": source.get("commit") == reveal["ledger_commit"],
        "ledger_source_path_matches": source.get("path") == f"controller/{trial_id}.json",
        "ledger_blob_sha_matches": source.get("api_blob_sha") == git_blob_sha1(raw_ledger),
        "ledger_bytes_sha256_matches": source.get("content_sha256") == hashlib.sha256(
            raw_ledger
        ).hexdigest(),
        "ledger_object_hash_matches": object_hash(parsed_raw_ledger) == reveal["ledger_hash"],
    })
    checks["valid"] = all(checks.values())
    return checks


def _api_get(url: str, token: str | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "science-of-ai-systems-public-evidence/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def _fetch_comments(repository: str, issue_number: int, token: str | None) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    page = 1
    while True:
        url = (
            f"https://api.github.com/repos/{repository}/issues/{issue_number}/comments"
            f"?per_page=100&page={page}"
        )
        batch = _api_get(url, token)
        if not isinstance(batch, list):
            raise PublicEvidenceError("GitHub comments response was not a list")
        comments.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return comments


def collect_public_trial(
    repository: str,
    issue_number: int,
    token: str | None = None,
    *,
    controller_actor: str = "github-actions[bot]",
) -> dict[str, Any]:
    if repository.count("/") != 1:
        raise ValueError("repository must be owner/name")
    raw_comments = _fetch_comments(repository, issue_number, token)
    comments = [
        {
            "id": int(item["id"]),
            "created_at": item.get("created_at"),
            "user": {"login": item.get("user", {}).get("login")},
            "body": item.get("body", ""),
        }
        for item in raw_comments
        if str(item.get("body", "")).startswith("SAIS_")
    ]
    try:
        indexed = _indexed_controller_comments(comments, controller_actor)
        reveal = _payload(indexed[REVEAL_PREFIX], REVEAL_PREFIX)
        trial_id = str(reveal["trial_id"])
        ledger_commit = str(reveal["ledger_commit"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise PublicEvidenceError(f"cannot identify sealed trial: {error}") from error

    ledger_path = f"controller/{trial_id}.json"
    encoded_path = quote(ledger_path, safe="/")
    content_url = (
        f"https://api.github.com/repos/{repository}/contents/{encoded_path}"
        f"?ref={quote(ledger_commit, safe='')}"
    )
    content_record = _api_get(content_url, token)
    if content_record.get("type") != "file" or content_record.get("encoding") != "base64":
        raise PublicEvidenceError("ledger source was not a base64 GitHub file response")
    raw_ledger = decode_github_base64(
        content_record.get("content"), source="ledger source"
    )
    ledger = json.loads(raw_ledger)

    bundle = {
        "ledger": ledger,
        "reveal": reveal,
        "public_record": {
            "repository": repository,
            "issue_number": issue_number,
            "controller_actor": controller_actor,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "comments": comments,
            "ledger_source": {
                "commit": ledger_commit,
                "path": ledger_path,
                "api_blob_sha": content_record["sha"],
                "content_sha256": hashlib.sha256(raw_ledger).hexdigest(),
                "content_base64": base64.b64encode(raw_ledger).decode(),
            },
        },
    }
    verification = verify_public_trial(
        bundle,
        expected_repository=repository,
        expected_controller_actor=controller_actor,
    )
    bundle["public_verification"] = verification
    if not verification.get("valid", False):
        failed = sorted(name for name, passed in verification.items() if not passed)
        raise PublicEvidenceError("public verification failed: " + ", ".join(failed))
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect a sealed SAIS trial from public GitHub history")
    parser.add_argument("repository", help="owner/name")
    parser.add_argument("issue_number", type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--controller-actor",
        default="github-actions[bot]",
        help="frozen GitHub login expected for controller comments",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or None
    bundle = collect_public_trial(
        args.repository,
        args.issue_number,
        token,
        controller_actor=args.controller_actor,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({
        "trial_id": bundle["ledger"]["trial_id"],
        "valid": bundle["public_verification"]["valid"],
        "output": str(args.output),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
