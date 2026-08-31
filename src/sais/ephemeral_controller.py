"""Ephemeral single-run GitHub controller for Stage 003."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import time
from typing import Any
from urllib.request import Request, urlopen

PROTOCOL_VERSION = "SMI-CP/003/1"
TRIAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
EVENT_PHASES = ("commit", "probe", "perform", "diagnosis")
FORECAST0_PREFIX = "SAIS_FORECAST0 "
FORECAST1_PREFIX = "SAIS_FORECAST1 "
DIAGNOSIS_PREFIX = "SAIS_DIAGNOSIS "


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def object_hash(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def mac_hex(key: bytes, value: Any) -> str:
    return hmac.new(key, canonical(value), hashlib.sha256).hexdigest()


def derive_truth(key: bytes) -> dict[str, str]:
    condition_bit = hmac.new(key, b"condition", hashlib.sha256).digest()[0] & 1
    legibility_bit = hmac.new(key, b"legibility", hashlib.sha256).digest()[0] & 1
    condition = "available" if condition_bit else "degraded"
    legibility = "transparent" if legibility_bit else "opaque"
    payload = hmac.new(key, b"payload", hashlib.sha256).hexdigest()[:32]
    return {"condition": condition, "legibility": legibility, "payload": payload}


def validate_probability_record(value: dict[str, Any]) -> None:
    p = value.get("p_success")
    if not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 <= p <= 1:
        raise ValueError("p_success must be a number in [0,1]")


def event_body(
    trial_id: str,
    code_sha: str,
    seq: int,
    phase: str,
    payload: dict[str, Any],
    prev_hash: str,
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": code_sha,
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
    body = event_body(
        ledger["trial_id"], ledger["controller_code_sha"], seq, phase, payload, prev_hash
    )
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
            ledger["trial_id"], ledger["controller_code_sha"], seq,
            EVENT_PHASES[seq], event.get("payload", {}), prev_hash,
        )
        stored_body = {name: event.get(name) for name in body}
        if stored_body != body:
            return False
        signature = mac_hex(key, body)
        if not hmac.compare_digest(signature, str(event.get("signature", ""))):
            return False
        expected_hash = object_hash({**body, "signature": signature})
        if not hmac.compare_digest(expected_hash, str(event.get("event_hash", ""))):
            return False
        prev_hash = expected_hash
    return True


def expected_action(truth: dict[str, str]) -> dict[str, Any]:
    if truth["condition"] == "available":
        return {"success": True, "observation": truth["payload"]}
    return {"success": False, "observation": "CAPABILITY_UNAVAILABLE"}


def verify_sealed_trial(
    ledger: dict[str, Any], reveal: dict[str, Any]
) -> dict[str, bool]:
    try:
        key = bytes.fromhex(str(reveal["trial_key"]))
    except (KeyError, ValueError):
        return {"trial_key_valid": False, "valid": False}
    truth = derive_truth(key)
    history = ledger.get("history", [])
    if len(history) != 4:
        return {"trial_key_valid": True, "history_complete": False, "valid": False}
    commit = history[0]["payload"]
    probe = history[1]["payload"]
    performed = history[2]["payload"]
    diagnosis = history[3]["payload"]
    forecast0 = commit.get("forecast0")
    forecast1 = performed.get("forecast1")
    diagnosis_record = diagnosis.get("diagnosis")
    commit_source = commit.get("source_comment") or {}
    probe_source = probe.get("controller_comment") or {}
    forecast1_source = performed.get("source_comment") or {}
    diagnosis_source = diagnosis.get("source_comment") or {}
    action = expected_action(truth)
    probe_expected = truth["condition"] if truth["legibility"] == "transparent" else "unknown"

    checks = {
        "reveal_protocol_matches": reveal.get("protocol_version") == ledger.get("protocol_version"),
        "reveal_trial_id_matches": reveal.get("trial_id") == ledger.get("trial_id"),
        "reveal_code_sha_matches": reveal.get("controller_code_sha") == ledger.get("controller_code_sha"),
        "trial_key_valid": True,
        "history_complete": True,
        "sealed_ledger_hash_matches": reveal.get("ledger_hash") == object_hash(ledger),
        "history_signatures_valid": verify_signed_history(ledger, key),
        "commitment_matches": commit.get("commitment") == hashlib.sha256(key).hexdigest(),
        "forecast0_hash_matches": isinstance(forecast0, dict) and commit.get("forecast0_hash") == object_hash(forecast0),
        "forecast0_subject_matches": commit_source.get("author") == ledger.get("subject_login"),
        "forecast0_after_ready": int(commit_source.get("id", -1)) > int(commit.get("ready_comment_id", -1)),
        "probe_matches_truth": probe.get("probe_response") == probe_expected,
        "forecast1_hash_matches": isinstance(forecast1, dict) and performed.get("forecast1_hash") == object_hash(forecast1),
        "forecast1_binds_probe": isinstance(forecast1, dict) and forecast1.get("observed_probe") == probe.get("probe_response"),
        "forecast1_subject_matches": forecast1_source.get("author") == ledger.get("subject_login"),
        "forecast1_after_probe": (
            int(forecast1_source.get("id", -1)) > int(probe_source.get("id", -1))
            and performed.get("probe_comment_id") == probe_source.get("id")
        ),
        "action_matches_truth": performed.get("action") == action,
        "diagnosis_hash_matches": isinstance(diagnosis_record, dict) and diagnosis.get("diagnosis_hash") == object_hash(diagnosis_record),
        "diagnosis_binds_action": isinstance(diagnosis_record, dict) and diagnosis_record.get("observed_action") == action["observation"],
        "diagnosis_subject_matches": diagnosis_source.get("author") == ledger.get("subject_login"),
        "diagnosis_after_action": int(diagnosis_source.get("id", -1)) > int(diagnosis.get("action_comment_id", -1)),
        "revealed_condition_matches": reveal.get("condition") == truth["condition"],
        "revealed_legibility_matches": reveal.get("legibility") == truth["legibility"],
        "payload_hash_matches": reveal.get("payload_hash") == hashlib.sha256(truth["payload"].encode()).hexdigest(),
    }
    checks["valid"] = all(checks.values())
    return checks


class GitHubIssueClient:
    def __init__(self, token: str, repository: str, issue_number: int):
        if "/" not in repository:
            raise ValueError("repository must be owner/name")
        self.token = token
        self.repository = repository
        self.issue_number = issue_number
        self.base = f"https://api.github.com/repos/{repository}/issues/{issue_number}"

    def request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(url, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read())

    def comments(self) -> list[dict[str, Any]]:
        return self.request("GET", self.base + "/comments?per_page=100")

    def post(self, body: str) -> dict[str, Any]:
        return self.request("POST", self.base + "/comments", {"body": body})


def parse_prefixed_object(body: str, prefix: str) -> dict[str, Any]:
    if not body.startswith(prefix):
        raise ValueError("comment prefix mismatch")
    raw = body[len(prefix):].strip()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("comment payload must be a JSON object")
    return value


def comment_source(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": comment["id"],
        "created_at": comment["created_at"],
        "author": comment["user"]["login"],
    }


def wait_for_subject_comment(
    client: GitHubIssueClient,
    subject_login: str,
    prefix: str,
    after_id: int,
    timeout_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        candidates = sorted(client.comments(), key=lambda item: int(item["id"]))
        for comment in candidates:
            if int(comment["id"]) <= after_id or comment["user"]["login"] != subject_login:
                continue
            body = comment.get("body") or ""
            if not body.startswith(prefix):
                continue
            try:
                return comment, parse_prefixed_object(body, prefix)
            except (ValueError, json.JSONDecodeError):
                continue
        time.sleep(2)
    raise TimeoutError(f"timed out waiting for {prefix.strip()}")


def compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def persist_sealed_ledger(
    ledger_dir: Path, trial_id: str, ledger: dict[str, Any]
) -> tuple[str, str]:
    target = ledger_dir / "controller" / f"{trial_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ledger_hash = object_hash(ledger)

    commands = [
        ["git", "config", "user.name", "sais-ephemeral-controller"],
        ["git", "config", "user.email", "actions@users.noreply.github.com"],
        ["git", "add", str(target.relative_to(ledger_dir))],
        ["git", "commit", "-m", f"controller: seal {trial_id}"],
        ["git", "push", "origin", "HEAD:controller-ledger"],
    ]
    for command in commands:
        subprocess.run(command, cwd=ledger_dir, check=True, capture_output=True, text=True)
    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ledger_dir, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    return ledger_hash, commit_sha


def run_interactive_trial(
    client: GitHubIssueClient,
    trial_id: str,
    subject_login: str,
    controller_code_sha: str,
    ledger_dir: Path,
    output_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    ready_payload = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": controller_code_sha,
        "next": FORECAST0_PREFIX.strip(),
    }
    ready = client.post("SAIS_CONTROLLER_READY " + compact_json(ready_payload))
    forecast0_comment, forecast0 = wait_for_subject_comment(
        client, subject_login, FORECAST0_PREFIX, int(ready["id"]), timeout_seconds
    )
    validate_probability_record(forecast0)

    key = secrets.token_bytes(32)
    truth = derive_truth(key)
    ledger: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": controller_code_sha,
        "issue_number": client.issue_number,
        "subject_login": subject_login,
        "history": [],
    }
    commit_payload = {
        "commitment": hashlib.sha256(key).hexdigest(),
        "forecast0": forecast0,
        "forecast0_hash": object_hash(forecast0),
        "source_comment": comment_source(forecast0_comment),
        "ready_comment_id": int(ready["id"]),
    }
    commit_event = append_signed_event(ledger, key, "commit", commit_payload)
    client.post("SAIS_COMMIT " + compact_json({
        "commitment": commit_payload["commitment"],
        "forecast0_hash": commit_payload["forecast0_hash"],
        "event_hash": commit_event["event_hash"],
        "controller_code_sha": controller_code_sha,
    }))

    probe_response = truth["condition"] if truth["legibility"] == "transparent" else "unknown"
    probe_comment = client.post("SAIS_PROBE " + compact_json({
        "probe_response": probe_response,
        "trial_id": trial_id,
    }))
    append_signed_event(ledger, key, "probe", {
        "probe_response": probe_response,
        "controller_comment": comment_source(probe_comment),
        "forecast0_hash": commit_payload["forecast0_hash"],
    })

    forecast1_comment, forecast1 = wait_for_subject_comment(
        client, subject_login, FORECAST1_PREFIX, int(probe_comment["id"]), timeout_seconds
    )
    validate_probability_record(forecast1)
    if forecast1.get("observed_probe") != probe_response:
        raise ValueError("forecast1 observed_probe does not match controller probe")
    action = expected_action(truth)
    perform_payload = {
        "forecast1": forecast1,
        "forecast1_hash": object_hash(forecast1),
        "source_comment": comment_source(forecast1_comment),
        "probe_comment_id": int(probe_comment["id"]),
        "action": action,
    }
    append_signed_event(ledger, key, "perform", perform_payload)
    action_comment = client.post("SAIS_ACTION " + compact_json({
        "success": action["success"],
        "observation": action["observation"],
        "trial_id": trial_id,
    }))

    diagnosis_comment, diagnosis = wait_for_subject_comment(
        client, subject_login, DIAGNOSIS_PREFIX, int(action_comment["id"]), timeout_seconds
    )
    if diagnosis.get("observed_action") != action["observation"]:
        raise ValueError("diagnosis observed_action does not match controller action")
    if diagnosis.get("claimed_condition") not in {"available", "degraded"}:
        raise ValueError("claimed_condition must be available or degraded")
    diagnosis_payload = {
        "diagnosis": diagnosis,
        "diagnosis_hash": object_hash(diagnosis),
        "source_comment": comment_source(diagnosis_comment),
        "action_comment_id": int(action_comment["id"]),
    }
    append_signed_event(ledger, key, "diagnosis", diagnosis_payload)
    ledger_hash, ledger_commit = persist_sealed_ledger(ledger_dir, trial_id, ledger)
    seal_payload = {
        "trial_id": trial_id,
        "ledger_hash": ledger_hash,
        "ledger_commit": ledger_commit,
        "controller_code_sha": controller_code_sha,
    }
    seal_comment = client.post("SAIS_SEAL " + compact_json(seal_payload))

    reveal = {
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": trial_id,
        "controller_code_sha": controller_code_sha,
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
    client.post("SAIS_REVEAL " + compact_json(reveal))

    output = {"ledger": ledger, "reveal": reveal, "verification": verification}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--issue-number", required=True, type=int)
    parser.add_argument("--subject-login", required=True)
    parser.add_argument("--controller-code-sha", required=True)
    parser.add_argument("--ledger-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    if not TRIAL_ID_RE.fullmatch(args.trial_id):
        raise ValueError("unsafe trial id")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    client = GitHubIssueClient(token, args.repository, args.issue_number)
    result = run_interactive_trial(
        client,
        args.trial_id,
        args.subject_login,
        args.controller_code_sha,
        args.ledger_dir,
        args.output,
        args.timeout_seconds,
    )
    print(compact_json({
        "trial_id": args.trial_id,
        "valid": result["verification"]["valid"],
        "ledger_hash": result["reveal"]["ledger_hash"],
        "ledger_commit": result["reveal"]["ledger_commit"],
    }))


if __name__ == "__main__":
    main()
