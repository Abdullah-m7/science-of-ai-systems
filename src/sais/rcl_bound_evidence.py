"""Public GitHub collection and offline verification for config-bound RCL trials."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config_binding import (
    BLOCK_ID_RE,
    COMMIT_RE,
    binding_hash,
    validate_product_config,
    validate_reference,
    validate_repository_name,
    validate_repository_path,
    verify_binding_bytes,
)
from .ephemeral_controller import object_hash
from .public_evidence import (
    PublicEvidenceError,
    _api_get,
    _fetch_comments,
    decode_github_base64,
    git_blob_sha1,
)
from .rcl_bound_controller import (
    ACTION_PREFIX,
    COMMIT_PREFIX,
    DIAGNOSIS_PREFIX,
    FORECAST0_PREFIX,
    FORECAST1_PREFIX,
    PROBE_PREFIX,
    PROTOCOL_VERSION,
    READY_PREFIX,
    REVEAL_PREFIX,
    SEAL_PREFIX,
    SUBJECT_LOGIN_RE,
    TRIAL_ID_RE,
    verify_sealed_trial,
)

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


def _author(comment: dict[str, Any]) -> str | None:
    user = comment.get("user")
    return user.get("login") if isinstance(user, dict) else comment.get("author")


def _payload(comment: dict[str, Any], prefix: str) -> dict[str, Any]:
    body = str(comment.get("body", ""))
    if not body.startswith(prefix):
        raise ValueError("comment phase prefix mismatch")
    value = json.loads(body[len(prefix) :])
    if not isinstance(value, dict):
        raise ValueError("comment payload must be an object")
    return value


def _indexed_controller_comments(
    comments: list[dict[str, Any]], controller_actor: str
) -> dict[str, dict[str, Any]]:
    found = {}
    for prefix in CONTROLLER_PREFIXES:
        matches = [
            item
            for item in comments
            if str(item.get("body", "")).startswith(prefix)
            and _author(item) == controller_actor
        ]
        if len(matches) != 1:
            message = (
                f"expected one {prefix.strip()} from {controller_actor}, "
                f"found {len(matches)}"
            )
            raise ValueError(message)
        found[prefix] = matches[0]
    return found


def _comment_by_id(comments: list[dict[str, Any]], comment_id: Any) -> dict[str, Any]:
    target = int(comment_id)
    matches = [item for item in comments if int(item.get("id", -1)) == target]
    if len(matches) != 1:
        raise ValueError(f"expected one comment id {target}, found {len(matches)}")
    return matches[0]


def _source_matches(comment: dict[str, Any], source: dict[str, Any]) -> bool:
    return (
        int(comment.get("id", -1)) == int(source.get("id", -2))
        and _author(comment) == source.get("author")
        and comment.get("created_at") == source.get("created_at")
    )


def _decode_bytes(source: dict[str, Any]) -> bytes:
    return base64.b64decode(source["content_base64"], validate=True)


def _decode_json_source(source: dict[str, Any]) -> tuple[bytes, Any]:
    raw = _decode_bytes(source)
    return raw, json.loads(raw)


def verify_public_trial(
    bundle: dict[str, Any],
    *,
    expected_repository: str | None = None,
    expected_controller_actor: str | None = None,
    expected_subject_actor: str | None = None,
    expected_controller_code_sha: str | None = None,
    expected_configuration_commit: str | None = None,
    expected_configuration_path: str | None = None,
    expected_block_id: str | None = None,
) -> dict[str, bool]:
    try:
        ledger = bundle["ledger"]
        reveal = bundle["reveal"]
        config = bundle["configuration"]
        public = bundle["public_record"]
        controller_actor = str(public["controller_actor"])
        comments = public["comments"]
        indexed = _indexed_controller_comments(comments, controller_actor)
        history = ledger["history"]
        commit_event, probe_event, perform_event, diagnosis_event = history
        commit = commit_event["payload"]
        probe = probe_event["payload"]
        performed = perform_event["payload"]
        diagnosis = diagnosis_event["payload"]
        ready_c = indexed[READY_PREFIX]
        commit_c = indexed[COMMIT_PREFIX]
        probe_c = indexed[PROBE_PREFIX]
        action_c = indexed[ACTION_PREFIX]
        seal_c = indexed[SEAL_PREFIX]
        reveal_c = indexed[REVEAL_PREFIX]
        forecast0_c = _comment_by_id(comments, commit["source_comment"]["id"])
        forecast1_c = _comment_by_id(comments, performed["source_comment"]["id"])
        diagnosis_c = _comment_by_id(comments, diagnosis["source_comment"]["id"])
        raw_ledger, parsed_ledger = _decode_json_source(public["ledger_source"])
        raw_config, parsed_config = _decode_json_source(public["configuration_source"])
        raw_instructions = _decode_bytes(public["subject_instruction_source"])
        raw_instructions.decode("utf-8")
        validate_product_config(config)
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        binascii.Error,
    ):
        return {"public_structure_valid": False, "valid": False}

    try:
        ready = _payload(ready_c, READY_PREFIX)
        forecast0 = _payload(forecast0_c, FORECAST0_PREFIX)
        commit_comment = _payload(commit_c, COMMIT_PREFIX)
        probe_comment = _payload(probe_c, PROBE_PREFIX)
        forecast1 = _payload(forecast1_c, FORECAST1_PREFIX)
        action_comment = _payload(action_c, ACTION_PREFIX)
        diagnosis_comment = _payload(diagnosis_c, DIAGNOSIS_PREFIX)
        seal_comment = _payload(seal_c, SEAL_PREFIX)
        reveal_comment = _payload(reveal_c, REVEAL_PREFIX)
    except (ValueError, json.JSONDecodeError):
        return {"public_structure_valid": False, "valid": False}

    trial_id = str(ledger["trial_id"])
    code_sha = str(ledger["controller_code_sha"])
    subject = str(ledger["subject_login"])
    binding = ledger["configuration_binding"]
    bound_hash = binding_hash(binding)
    repository = public.get("repository")
    ledger_source = public["ledger_source"]
    config_source = public["configuration_source"]
    instruction_source = public["subject_instruction_source"]
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

    expected_ready = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": code_sha,
        "configuration_binding": binding,
        "configuration_binding_hash": bound_hash,
        "next": FORECAST0_PREFIX.strip(),
    }
    expected_commit = {
        "trial_id": trial_id,
        "commitment": commit["commitment"],
        "configuration_binding_hash": bound_hash,
        "forecast0_hash": commit["forecast0_hash"],
        "event_hash": commit_event["event_hash"],
        "controller_code_sha": code_sha,
    }
    expected_probe = {
        "trial_id": trial_id,
        "configuration_binding_hash": bound_hash,
        "probe_response": probe["probe_response"],
    }
    expected_action = {
        "trial_id": trial_id,
        "configuration_binding_hash": bound_hash,
        **performed["action"],
    }
    expected_seal = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": code_sha,
        "configuration_binding_hash": bound_hash,
        "config_sha256": binding["config_sha256"],
        "ledger_hash": reveal["ledger_hash"],
        "ledger_commit": reveal["ledger_commit"],
    }

    crypto = verify_sealed_trial(ledger, reveal)
    binding_checks = verify_binding_bytes(binding, config, raw_config)
    checks: dict[str, bool] = {
        **{
            f"crypto_{name}": bool(value)
            for name, value in crypto.items()
            if name != "valid"
        },
        **{
            f"config_{name}": bool(value)
            for name, value in binding_checks.items()
            if name != "valid"
        },
        "public_structure_valid": True,
        "trial_id_format_valid": bool(TRIAL_ID_RE.fullmatch(trial_id)),
        "controller_code_sha_format_valid": bool(COMMIT_RE.fullmatch(code_sha)),
        "ledger_commit_format_valid": bool(
            COMMIT_RE.fullmatch(str(reveal.get("ledger_commit", "")))
        ),
        "issue_number_positive": int(public["issue_number"]) > 0,
        "cryptographic_trial_valid": bool(crypto.get("valid")),
        "configuration_binding_valid": bool(binding_checks.get("valid")),
        "repository_present": isinstance(repository, str)
        and repository.count("/") == 1,
        "repository_matches_expected": expected_repository is None
        or repository == expected_repository,
        "binding_repository_matches_public": binding.get("repository") == repository,
        "controller_actor_matches_expected": expected_controller_actor is None
        or controller_actor == expected_controller_actor,
        "subject_actor_matches_expected": expected_subject_actor is None
        or subject == expected_subject_actor,
        "controller_code_matches_expected": expected_controller_code_sha is None
        or code_sha == expected_controller_code_sha,
        "configuration_commit_matches_expected": expected_configuration_commit is None
        or binding.get("commit") == expected_configuration_commit,
        "configuration_path_matches_expected": expected_configuration_path is None
        or binding.get("path") == expected_configuration_path,
        "configuration_block_matches_expected": expected_block_id is None
        or binding.get("block_id") == expected_block_id,
        "controller_subject_distinct": controller_actor != subject,
        "all_comment_ids_unique": len(comment_ids) == len(set(comment_ids)),
        "selected_comment_ids_unique": len(ordered_ids) == len(set(ordered_ids)),
        "protocol_comment_ids_increase": ordered_ids == sorted(ordered_ids),
        "public_protocol_order": [positions[item] for item in ordered_ids]
        == sorted(positions[item] for item in ordered_ids),
        "controller_actor_consistent": all(
            _author(item) == controller_actor
            for item in (ready_c, commit_c, probe_c, action_c, seal_c, reveal_c)
        ),
        "subject_actor_consistent": all(
            _author(item) == subject for item in (forecast0_c, forecast1_c, diagnosis_c)
        ),
        "ready_body_matches": ready == expected_ready,
        "ready_comment_id_matches": int(ready_c["id"])
        == int(commit["ready_comment_id"]),
        "forecast0_body_matches": forecast0 == commit["forecast0"],
        "forecast0_source_matches": _source_matches(
            forecast0_c, commit["source_comment"]
        ),
        "commit_body_matches": commit_comment == expected_commit,
        "probe_body_matches": probe_comment == expected_probe,
        "probe_source_matches": _source_matches(probe_c, probe["controller_comment"]),
        "forecast1_body_matches": forecast1 == performed["forecast1"],
        "forecast1_source_matches": _source_matches(
            forecast1_c, performed["source_comment"]
        ),
        "forecast1_probe_id_matches": int(probe_c["id"])
        == int(performed["probe_comment_id"]),
        "action_body_matches": action_comment == expected_action,
        "action_comment_id_matches": int(action_c["id"])
        == int(diagnosis["action_comment_id"]),
        "diagnosis_body_matches": diagnosis_comment == diagnosis["diagnosis"],
        "diagnosis_source_matches": _source_matches(
            diagnosis_c, diagnosis["source_comment"]
        ),
        "seal_body_matches": seal_comment == expected_seal,
        "seal_comment_id_matches": int(seal_c["id"]) == int(reveal["seal_comment_id"]),
        "seal_precedes_reveal": positions[int(seal_c["id"])]
        < positions[int(reveal_c["id"])],
        "reveal_body_matches": reveal_comment == reveal,
        "ledger_issue_matches": int(ledger["issue_number"])
        == int(public["issue_number"]),
        "ledger_raw_json_matches": parsed_ledger == ledger,
        "ledger_source_repository_matches": ledger_source.get("repository")
        == repository,
        "ledger_source_commit_matches": ledger_source.get("commit")
        == reveal["ledger_commit"],
        "ledger_source_path_matches": ledger_source.get("path")
        == f"rcl-controller/{trial_id}.json",
        "ledger_blob_sha_matches": ledger_source.get("api_blob_sha")
        == git_blob_sha1(raw_ledger),
        "ledger_bytes_sha256_matches": ledger_source.get("content_sha256")
        == hashlib.sha256(raw_ledger).hexdigest(),
        "ledger_object_hash_matches": object_hash(parsed_ledger)
        == reveal["ledger_hash"],
        "configuration_object_matches": parsed_config == config,
        "config_source_repository_matches": config_source.get("repository")
        == binding.get("repository"),
        "config_source_commit_matches": config_source.get("commit")
        == binding.get("commit"),
        "config_source_path_matches": config_source.get("path") == binding.get("path"),
        "config_blob_sha_matches": config_source.get("api_blob_sha")
        == git_blob_sha1(raw_config),
        "config_source_content_sha256_matches": config_source.get("content_sha256")
        == hashlib.sha256(raw_config).hexdigest(),
        "config_bytes_sha256_matches": config_source.get("content_sha256")
        == binding.get("config_sha256"),
        "instruction_source_repository_matches": instruction_source.get("repository")
        == binding.get("repository"),
        "instruction_source_commit_matches": instruction_source.get("commit")
        == binding.get("commit"),
        "instruction_source_path_matches": instruction_source.get("path")
        == config.get("subject_instruction_path"),
        "instruction_blob_sha_matches": instruction_source.get("api_blob_sha")
        == git_blob_sha1(raw_instructions),
        "instruction_source_content_sha256_matches": instruction_source.get(
            "content_sha256"
        )
        == hashlib.sha256(raw_instructions).hexdigest(),
        "instruction_bytes_sha256_matches": hashlib.sha256(raw_instructions).hexdigest()
        == config.get("subject_instruction_sha256"),
    }
    checks["valid"] = all(checks.values())
    return checks


def _content_record(
    repository: str, commit: str, path: str, token: str | None
) -> dict[str, Any]:
    encoded_path = quote(path, safe="/")
    url = (
        f"https://api.github.com/repos/{repository}/contents/{encoded_path}"
        f"?ref={quote(commit, safe='')}"
    )
    record = _api_get(url, token)
    if record.get("type") != "file" or record.get("encoding") != "base64":
        raise PublicEvidenceError(f"GitHub source is not a base64 file: {path}")
    return record


def _source_from_record(
    record: dict[str, Any], *, repository: str, commit: str, path: str
) -> tuple[dict[str, Any], bytes]:
    raw = decode_github_base64(
        record.get("content"), source=f"GitHub source {path}"
    )
    return {
        "repository": repository,
        "commit": commit,
        "path": path,
        "api_blob_sha": record["sha"],
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "content_base64": base64.b64encode(raw).decode(),
    }, raw


def collect_public_trial(
    repository: str,
    issue_number: int,
    token: str | None = None,
    *,
    controller_actor: str = "github-actions[bot]",
    expected_subject_actor: str | None = None,
    expected_controller_code_sha: str | None = None,
    expected_configuration_commit: str | None = None,
    expected_configuration_path: str | None = None,
    expected_block_id: str | None = None,
) -> dict[str, Any]:
    validate_repository_name(repository)
    if issue_number < 1:
        raise ValueError("issue_number must be positive")
    if not controller_actor:
        raise ValueError("controller_actor must be non-empty")
    if expected_subject_actor is not None and not SUBJECT_LOGIN_RE.fullmatch(
        expected_subject_actor
    ):
        raise ValueError("expected subject actor is unsafe")
    if expected_controller_code_sha is not None and not COMMIT_RE.fullmatch(
        expected_controller_code_sha
    ):
        raise ValueError("expected controller code SHA is invalid")
    if expected_configuration_commit is not None and not COMMIT_RE.fullmatch(
        expected_configuration_commit
    ):
        raise ValueError("expected configuration commit is invalid")
    if expected_configuration_path is not None:
        validate_repository_path(expected_configuration_path)
    if expected_block_id is not None and not BLOCK_ID_RE.fullmatch(expected_block_id):
        raise ValueError("expected block id is invalid")
    raw_comments = _fetch_comments(repository, issue_number, token)
    # Retain the complete issue-comment stream. Protocol verification selects
    # the bound records, while final analysis audits extra subject comments.
    comments = [
        {
            "id": int(item["id"]),
            "created_at": item.get("created_at"),
            "user": {"login": item.get("user", {}).get("login")},
            "body": item.get("body", ""),
        }
        for item in raw_comments
    ]
    try:
        indexed = _indexed_controller_comments(comments, controller_actor)
        reveal = _payload(indexed[REVEAL_PREFIX], REVEAL_PREFIX)
        trial_id = str(reveal["trial_id"])
        ledger_commit = str(reveal["ledger_commit"])
        if not TRIAL_ID_RE.fullmatch(trial_id):
            raise ValueError("unsafe trial id in reveal")
        if not COMMIT_RE.fullmatch(ledger_commit):
            raise ValueError("unsafe ledger commit in reveal")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise PublicEvidenceError(
            f"cannot identify config-bound RCL trial: {error}"
        ) from error

    ledger_path = f"rcl-controller/{trial_id}.json"
    validate_reference(repository, ledger_commit, ledger_path)
    ledger_record = _content_record(repository, ledger_commit, ledger_path, token)
    ledger_source, raw_ledger = _source_from_record(
        ledger_record, repository=repository, commit=ledger_commit, path=ledger_path
    )
    ledger = json.loads(raw_ledger)
    binding = ledger["configuration_binding"]
    config_repository = str(binding["repository"])
    config_commit = str(binding["commit"])
    config_path = str(binding["path"])
    validate_reference(config_repository, config_commit, config_path)
    if config_repository != repository:
        raise PublicEvidenceError(
            "configuration repository differs from trial repository"
        )
    config_record = _content_record(
        config_repository, config_commit, config_path, token
    )
    config_source, raw_config = _source_from_record(
        config_record,
        repository=config_repository,
        commit=config_commit,
        path=config_path,
    )
    configuration = json.loads(raw_config)
    validate_product_config(configuration)
    instruction_path = str(configuration["subject_instruction_path"])
    validate_repository_path(instruction_path, label="subject instruction")
    instruction_record = _content_record(
        config_repository, config_commit, instruction_path, token
    )
    instruction_source, raw_instructions = _source_from_record(
        instruction_record,
        repository=config_repository,
        commit=config_commit,
        path=instruction_path,
    )
    try:
        raw_instructions.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PublicEvidenceError("subject instructions are not UTF-8") from error
    if (
        hashlib.sha256(raw_instructions).hexdigest()
        != configuration["subject_instruction_sha256"]
    ):
        raise PublicEvidenceError(
            "subject instruction bytes do not match configuration"
        )

    bundle = {
        "ledger": ledger,
        "reveal": reveal,
        "configuration": configuration,
        "public_record": {
            "repository": repository,
            "issue_number": issue_number,
            "controller_actor": controller_actor,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "comments": comments,
            "ledger_source": ledger_source,
            "configuration_source": config_source,
            "subject_instruction_source": instruction_source,
        },
    }
    verification = verify_public_trial(
        bundle,
        expected_repository=repository,
        expected_controller_actor=controller_actor,
        expected_subject_actor=expected_subject_actor,
        expected_controller_code_sha=expected_controller_code_sha,
        expected_configuration_commit=expected_configuration_commit,
        expected_configuration_path=expected_configuration_path,
        expected_block_id=expected_block_id,
    )
    bundle["public_verification"] = verification
    if not verification.get("valid"):
        failed = sorted(name for name, passed in verification.items() if not passed)
        raise PublicEvidenceError(
            "config-bound public verification failed: " + ", ".join(failed)
        )
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository")
    parser.add_argument("issue_number", type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--controller-actor", default="github-actions[bot]")
    parser.add_argument("--subject-actor")
    parser.add_argument("--controller-code-sha")
    parser.add_argument("--config-commit")
    parser.add_argument("--config-path")
    parser.add_argument("--block-id")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN") or None
    bundle = collect_public_trial(
        args.repository,
        args.issue_number,
        token,
        controller_actor=args.controller_actor,
        expected_subject_actor=args.subject_actor,
        expected_controller_code_sha=args.controller_code_sha,
        expected_configuration_commit=args.config_commit,
        expected_configuration_path=args.config_path,
        expected_block_id=args.block_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "trial_id": bundle["ledger"]["trial_id"],
                "valid": bundle["public_verification"]["valid"],
                "configuration_binding_hash": bundle["ledger"][
                    "configuration_binding_hash"
                ],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
