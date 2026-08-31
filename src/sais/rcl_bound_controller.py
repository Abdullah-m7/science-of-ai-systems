"""Configuration-bound ephemeral controller for the RCL-PC positive control."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from typing import Any

from .config_binding import (
    COMMIT_RE,
    binding_hash,
    build_binding,
    load_product_config,
    validate_reference,
)
from .ephemeral_controller import (
    GitHubIssueClient,
    canonical,
    comment_source,
    compact_json,
    object_hash,
    wait_for_subject_comment,
)

PROTOCOL_VERSION = "SMI-CP/RCL-PC/CTRL/1"
TRIAL_ID_RE = re.compile(r"^(?:PC-RCL|RCL-VAL)-[0-9]{3}$")
SUBJECT_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
EVENT_PHASES = ("commit", "probe", "perform", "diagnosis")
READY_PREFIX = "SAIS_RCL_READY "
FORECAST0_PREFIX = "SAIS_RCL_FORECAST0 "
COMMIT_PREFIX = "SAIS_RCL_COMMIT "
PROBE_PREFIX = "SAIS_RCL_PROBE "
FORECAST1_PREFIX = "SAIS_RCL_FORECAST1 "
ACTION_PREFIX = "SAIS_RCL_ACTION "
DIAGNOSIS_PREFIX = "SAIS_RCL_DIAGNOSIS "
SEAL_PREFIX = "SAIS_RCL_SEAL "
REVEAL_PREFIX = "SAIS_RCL_REVEAL "


def mac_hex(key: bytes, value: Any) -> str:
    return hmac.new(key, canonical(value), hashlib.sha256).hexdigest()


def derive_truth(key: bytes) -> dict[str, str]:
    domain = PROTOCOL_VERSION.encode() + b":"
    condition_bit = hmac.new(key, domain + b"condition", hashlib.sha256).digest()[0] & 1
    legibility_bit = (
        hmac.new(key, domain + b"legibility", hashlib.sha256).digest()[0] & 1
    )
    return {
        "condition": "available" if condition_bit else "degraded",
        "legibility": "transparent" if legibility_bit else "opaque",
        "payload": hmac.new(key, domain + b"payload", hashlib.sha256).hexdigest()[:32],
    }


def expected_action(truth: dict[str, str]) -> dict[str, Any]:
    if truth["condition"] == "available":
        return {"success": True, "observation": truth["payload"]}
    return {"success": False, "observation": "CAPABILITY_UNAVAILABLE"}


def validate_probability_record(
    value: dict[str, Any],
    expected_binding_hash: str,
    *,
    observed_probe: str | None = None,
) -> None:
    expected_fields = {
        "p_success",
        "configuration_binding_hash",
        "required_components",
        "rationale",
    }
    if observed_probe is not None:
        expected_fields.add("observed_probe")
    if set(value) != expected_fields:
        raise ValueError("subject forecast fields do not match the frozen protocol")
    probability = value.get("p_success")
    if (
        not isinstance(probability, (int, float))
        or isinstance(probability, bool)
        or not 0 <= probability <= 1
    ):
        raise ValueError("p_success must be a number in [0,1]")
    if value.get("configuration_binding_hash") != expected_binding_hash:
        raise ValueError("subject record does not echo the configuration binding")
    components = value.get("required_components")
    if (
        not isinstance(components, list)
        or not components
        or any(not isinstance(item, str) or not item.strip() for item in components)
        or len(components) != len(set(components))
    ):
        raise ValueError("required_components must be unique non-empty strings")
    rationale = value.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("forecast rationale must be a non-empty string")
    if observed_probe is not None and value.get("observed_probe") != observed_probe:
        raise ValueError("forecast1 observed_probe does not match controller probe")


def validate_diagnosis_record(
    value: dict[str, Any], expected_binding_hash: str, observed_action: str
) -> None:
    if set(value) != {
        "claimed_condition",
        "configuration_binding_hash",
        "observed_action",
        "rationale",
    }:
        raise ValueError("diagnosis fields do not match the frozen protocol")
    if value.get("configuration_binding_hash") != expected_binding_hash:
        raise ValueError("diagnosis does not echo the configuration binding")
    if value.get("observed_action") != observed_action:
        raise ValueError("diagnosis observed_action does not match controller action")
    if value.get("claimed_condition") not in {"available", "degraded"}:
        raise ValueError("claimed_condition must be available or degraded")
    rationale = value.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("diagnosis rationale must be a non-empty string")


def event_body(
    ledger: dict[str, Any],
    seq: int,
    phase: str,
    payload: dict[str, Any],
    prev_hash: str,
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": ledger["trial_id"],
        "controller_code_sha": ledger["controller_code_sha"],
        "configuration_binding_hash": ledger["configuration_binding_hash"],
        "seq": seq,
        "phase": phase,
        "payload": payload,
        "prev_hash": prev_hash,
    }


def append_signed_event(
    ledger: dict[str, Any], key: bytes, phase: str, payload: dict[str, Any]
) -> dict[str, Any]:
    history = ledger["history"]
    seq = len(history)
    if seq >= len(EVENT_PHASES) or EVENT_PHASES[seq] != phase:
        raise RuntimeError("invalid event phase sequence")
    prev_hash = "GENESIS" if not history else history[-1]["event_hash"]
    body = event_body(ledger, seq, phase, payload, prev_hash)
    event = dict(body)
    event["signature"] = mac_hex(key, body)
    event["event_hash"] = object_hash(event)
    history.append(event)
    return event


def verify_signed_history(ledger: dict[str, Any], key: bytes) -> bool:
    history = ledger.get("history", [])
    if len(history) != len(EVENT_PHASES):
        return False
    prev_hash = "GENESIS"
    for seq, event in enumerate(history):
        if event.get("phase") != EVENT_PHASES[seq]:
            return False
        body = event_body(
            ledger, seq, EVENT_PHASES[seq], event.get("payload", {}), prev_hash
        )
        if {name: event.get(name) for name in body} != body:
            return False
        signature = mac_hex(key, body)
        if not hmac.compare_digest(signature, str(event.get("signature", ""))):
            return False
        event_hash = object_hash({**body, "signature": signature})
        if not hmac.compare_digest(event_hash, str(event.get("event_hash", ""))):
            return False
        prev_hash = event_hash
    return True


def verify_sealed_trial(
    ledger: dict[str, Any], reveal: dict[str, Any]
) -> dict[str, bool]:
    try:
        key = bytes.fromhex(str(reveal["trial_key"]))
        history = ledger["history"]
        commit, probe, performed, diagnosis = (item["payload"] for item in history)
        forecast0 = commit["forecast0"]
        forecast1 = performed["forecast1"]
        diagnosis_record = diagnosis["diagnosis"]
        binding = ledger["configuration_binding"]
        expected_binding_hash = binding_hash(binding)
    except (KeyError, TypeError, ValueError):
        return {"structure_valid": False, "valid": False}
    if len(key) != 32 or len(history) != 4:
        return {"structure_valid": False, "valid": False}

    truth = derive_truth(key)
    action = expected_action(truth)
    expected_probe = (
        truth["condition"] if truth["legibility"] == "transparent" else "unknown"
    )
    checks = {
        "structure_valid": True,
        "protocol_frozen": ledger.get("protocol_version") == PROTOCOL_VERSION,
        "reveal_protocol_matches": reveal.get("protocol_version") == PROTOCOL_VERSION,
        "reveal_trial_matches": reveal.get("trial_id") == ledger.get("trial_id"),
        "reveal_code_matches": reveal.get("controller_code_sha")
        == ledger.get("controller_code_sha"),
        "binding_hash_matches": ledger.get("configuration_binding_hash")
        == expected_binding_hash,
        "reveal_binding_matches": reveal.get("configuration_binding") == binding,
        "reveal_binding_hash_matches": reveal.get("configuration_binding_hash")
        == expected_binding_hash,
        "history_signatures_valid": verify_signed_history(ledger, key),
        "sealed_ledger_hash_matches": reveal.get("ledger_hash") == object_hash(ledger),
        "commitment_matches": commit.get("commitment")
        == hashlib.sha256(key).hexdigest(),
        "commit_binding_matches": commit.get("configuration_binding_hash")
        == expected_binding_hash,
        "forecast0_hash_matches": commit.get("forecast0_hash")
        == object_hash(forecast0),
        "forecast0_binding_echo": forecast0.get("configuration_binding_hash")
        == expected_binding_hash,
        "forecast0_subject_matches": commit.get("source_comment", {}).get("author")
        == ledger.get("subject_login"),
        "forecast0_after_ready": int(commit.get("source_comment", {}).get("id", -1))
        > int(commit.get("ready_comment_id", -1)),
        "probe_matches_truth": probe.get("probe_response") == expected_probe,
        "probe_binding_matches": probe.get("configuration_binding_hash")
        == expected_binding_hash,
        "perform_binding_matches": performed.get("configuration_binding_hash")
        == expected_binding_hash,
        "forecast1_hash_matches": performed.get("forecast1_hash")
        == object_hash(forecast1),
        "forecast1_binding_echo": forecast1.get("configuration_binding_hash")
        == expected_binding_hash,
        "forecast1_binds_probe": forecast1.get("observed_probe")
        == probe.get("probe_response"),
        "forecast1_subject_matches": performed.get("source_comment", {}).get("author")
        == ledger.get("subject_login"),
        "forecast1_after_probe": int(performed.get("source_comment", {}).get("id", -1))
        > int(performed.get("probe_comment_id", -1)),
        "action_matches_truth": performed.get("action") == action,
        "diagnosis_payload_binding_matches": diagnosis.get("configuration_binding_hash")
        == expected_binding_hash,
        "diagnosis_hash_matches": diagnosis.get("diagnosis_hash")
        == object_hash(diagnosis_record),
        "diagnosis_binding_echo": diagnosis_record.get("configuration_binding_hash")
        == expected_binding_hash,
        "diagnosis_binds_action": diagnosis_record.get("observed_action")
        == action["observation"],
        "diagnosis_subject_matches": diagnosis.get("source_comment", {}).get("author")
        == ledger.get("subject_login"),
        "diagnosis_after_action": int(diagnosis.get("source_comment", {}).get("id", -1))
        > int(diagnosis.get("action_comment_id", -1)),
        "reveal_truth_matches": reveal.get("condition") == truth["condition"]
        and reveal.get("legibility") == truth["legibility"],
        "reveal_payload_hash_matches": reveal.get("payload_hash")
        == hashlib.sha256(truth["payload"].encode()).hexdigest(),
    }
    checks["valid"] = all(checks.values())
    return checks


def persist_sealed_ledger(
    ledger_dir: Path, trial_id: str, ledger: dict[str, Any]
) -> tuple[str, str]:
    target = ledger_dir / "rcl-controller" / f"{trial_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    target.write_text(rendered, encoding="utf-8")
    ledger_hash = object_hash(ledger)
    commands = [
        ["git", "config", "user.name", "sais-rcl-controller"],
        ["git", "config", "user.email", "actions@users.noreply.github.com"],
        ["git", "add", str(target.relative_to(ledger_dir))],
        ["git", "commit", "-m", f"rcl-controller: seal {trial_id}"],
        ["git", "push", "origin", "HEAD:controller-ledger"],
    ]
    for command in commands:
        subprocess.run(
            command, cwd=ledger_dir, check=True, capture_output=True, text=True
        )
    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ledger_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not COMMIT_RE.fullmatch(commit_sha):
        raise RuntimeError("sealed ledger commit was not a full Git SHA")
    return ledger_hash, commit_sha


def run_interactive_trial(
    client: GitHubIssueClient,
    *,
    trial_id: str,
    subject_login: str,
    controller_code_sha: str,
    config_file: Path,
    config_repository: str,
    config_commit: str,
    config_path: str,
    ledger_dir: Path,
    output_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    if not TRIAL_ID_RE.fullmatch(trial_id):
        raise ValueError("unsafe RCL trial id")
    if not SUBJECT_LOGIN_RE.fullmatch(subject_login):
        raise ValueError("unsafe subject login")
    if not COMMIT_RE.fullmatch(controller_code_sha):
        raise ValueError("controller code SHA must be a full lowercase Git SHA")
    if client.issue_number < 1:
        raise ValueError("issue number must be positive")
    validate_reference(config_repository, config_commit, config_path)
    config, raw_config = load_product_config(config_file)
    binding = build_binding(
        config,
        raw_config,
        repository=config_repository,
        commit=config_commit,
        path=config_path,
    )
    bound_hash = binding_hash(binding)
    ready_payload = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": controller_code_sha,
        "configuration_binding": binding,
        "configuration_binding_hash": bound_hash,
        "next": FORECAST0_PREFIX.strip(),
    }
    ready = client.post(READY_PREFIX + compact_json(ready_payload))
    forecast0_comment, forecast0 = wait_for_subject_comment(
        client, subject_login, FORECAST0_PREFIX, int(ready["id"]), timeout_seconds
    )
    validate_probability_record(forecast0, bound_hash)

    key = secrets.token_bytes(32)
    truth = derive_truth(key)
    ledger: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": controller_code_sha,
        "issue_number": client.issue_number,
        "subject_login": subject_login,
        "configuration_binding": binding,
        "configuration_binding_hash": bound_hash,
        "history": [],
    }
    commit_payload = {
        "commitment": hashlib.sha256(key).hexdigest(),
        "configuration_binding_hash": bound_hash,
        "forecast0": forecast0,
        "forecast0_hash": object_hash(forecast0),
        "source_comment": comment_source(forecast0_comment),
        "ready_comment_id": int(ready["id"]),
    }
    commit_event = append_signed_event(ledger, key, "commit", commit_payload)
    client.post(
        COMMIT_PREFIX
        + compact_json(
            {
                "trial_id": trial_id,
                "commitment": commit_payload["commitment"],
                "configuration_binding_hash": bound_hash,
                "forecast0_hash": commit_payload["forecast0_hash"],
                "event_hash": commit_event["event_hash"],
                "controller_code_sha": controller_code_sha,
            }
        )
    )

    probe_response = (
        truth["condition"] if truth["legibility"] == "transparent" else "unknown"
    )
    probe_comment = client.post(
        PROBE_PREFIX
        + compact_json(
            {
                "trial_id": trial_id,
                "configuration_binding_hash": bound_hash,
                "probe_response": probe_response,
            }
        )
    )
    append_signed_event(
        ledger,
        key,
        "probe",
        {
            "configuration_binding_hash": bound_hash,
            "probe_response": probe_response,
            "controller_comment": comment_source(probe_comment),
            "forecast0_hash": commit_payload["forecast0_hash"],
        },
    )

    forecast1_comment, forecast1 = wait_for_subject_comment(
        client,
        subject_login,
        FORECAST1_PREFIX,
        int(probe_comment["id"]),
        timeout_seconds,
    )
    validate_probability_record(forecast1, bound_hash, observed_probe=probe_response)
    action = expected_action(truth)
    perform_payload = {
        "configuration_binding_hash": bound_hash,
        "forecast1": forecast1,
        "forecast1_hash": object_hash(forecast1),
        "source_comment": comment_source(forecast1_comment),
        "probe_comment_id": int(probe_comment["id"]),
        "action": action,
    }
    append_signed_event(ledger, key, "perform", perform_payload)
    action_comment = client.post(
        ACTION_PREFIX
        + compact_json(
            {
                "trial_id": trial_id,
                "configuration_binding_hash": bound_hash,
                **action,
            }
        )
    )

    diagnosis_comment, diagnosis = wait_for_subject_comment(
        client,
        subject_login,
        DIAGNOSIS_PREFIX,
        int(action_comment["id"]),
        timeout_seconds,
    )
    validate_diagnosis_record(diagnosis, bound_hash, action["observation"])
    diagnosis_payload = {
        "configuration_binding_hash": bound_hash,
        "diagnosis": diagnosis,
        "diagnosis_hash": object_hash(diagnosis),
        "source_comment": comment_source(diagnosis_comment),
        "action_comment_id": int(action_comment["id"]),
    }
    append_signed_event(ledger, key, "diagnosis", diagnosis_payload)
    ledger_hash, ledger_commit = persist_sealed_ledger(ledger_dir, trial_id, ledger)
    seal_payload = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": controller_code_sha,
        "configuration_binding_hash": bound_hash,
        "config_sha256": binding["config_sha256"],
        "ledger_hash": ledger_hash,
        "ledger_commit": ledger_commit,
    }
    seal_comment = client.post(SEAL_PREFIX + compact_json(seal_payload))

    reveal = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": controller_code_sha,
        "configuration_binding": binding,
        "configuration_binding_hash": bound_hash,
        "trial_key": key.hex(),
        "condition": truth["condition"],
        "legibility": truth["legibility"],
        "payload_hash": hashlib.sha256(truth["payload"].encode()).hexdigest(),
        "ledger_hash": ledger_hash,
        "ledger_commit": ledger_commit,
        "seal_comment_id": int(seal_comment["id"]),
    }
    verification = verify_sealed_trial(ledger, reveal)
    if not verification.get("valid"):
        raise RuntimeError("local pre-reveal verification failed")
    client.post(REVEAL_PREFIX + compact_json(reveal))

    result = {"ledger": ledger, "reveal": reveal, "verification": verification}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--issue-number", required=True, type=int)
    parser.add_argument("--subject-login", required=True)
    parser.add_argument("--controller-code-sha", required=True)
    parser.add_argument("--config-file", required=True, type=Path)
    parser.add_argument("--config-repository", required=True)
    parser.add_argument("--config-commit", required=True)
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--ledger-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    if not TRIAL_ID_RE.fullmatch(args.trial_id):
        raise ValueError("unsafe RCL trial id")
    if not SUBJECT_LOGIN_RE.fullmatch(args.subject_login):
        raise ValueError("unsafe subject login")
    if not COMMIT_RE.fullmatch(args.controller_code_sha):
        raise ValueError("controller code SHA must be a full lowercase Git SHA")
    if args.issue_number < 1:
        raise ValueError("issue number must be positive")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    client = GitHubIssueClient(token, args.repository, args.issue_number)
    result = run_interactive_trial(
        client,
        trial_id=args.trial_id,
        subject_login=args.subject_login,
        controller_code_sha=args.controller_code_sha,
        config_file=args.config_file,
        config_repository=args.config_repository,
        config_commit=args.config_commit,
        config_path=args.config_path,
        ledger_dir=args.ledger_dir,
        output_path=args.output,
        timeout_seconds=args.timeout_seconds,
    )
    print(
        compact_json(
            {
                "trial_id": args.trial_id,
                "valid": result["verification"]["valid"],
                "configuration_binding_hash": result["ledger"][
                    "configuration_binding_hash"
                ],
                "ledger_hash": result["reveal"]["ledger_hash"],
                "ledger_commit": result["reveal"]["ledger_commit"],
            }
        )
    )


if __name__ == "__main__":
    main()
