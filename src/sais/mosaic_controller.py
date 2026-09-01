"""Fail-closed quartet controller candidate for MOSAIC-P1.

This module is intentionally transport-agnostic. Stage 009 validates the quartet
state machine locally; it does not expose a GitHub Actions dispatch workflow.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Callable, Mapping, Protocol, Sequence

from .mosaic import (
    CLAIMS,
    CoreSpec,
    Cue,
    canonical_hash,
    make_design_matrix,
    posterior_path,
    validate_cue_record,
    variant_spec,
)

PROTOCOL_VERSION = "SAIS/MOSAIC/CTRL-CANDIDATE/1"
SUBJECT_PROTOCOL = "SAIS/MOSAIC/SUBJECT/1"
READY_PREFIX = "SAIS_MOSAIC_READY "
P0_PREFIX = "SAIS_MOSAIC_P0 "
P0_SEAL_PREFIX = "SAIS_MOSAIC_P0_SEAL "
COMMIT_PREFIX = "SAIS_MOSAIC_CORE_COMMIT "
CUE1_PREFIX = "SAIS_MOSAIC_CUE1 "
P1_PREFIX = "SAIS_MOSAIC_P1 "
CUE2_PREFIX = "SAIS_MOSAIC_CUE2 "
P2_PREFIX = "SAIS_MOSAIC_P2 "
ACTION_PREFIX = "SAIS_MOSAIC_ACTION "
DIAGNOSIS_PREFIX = "SAIS_MOSAIC_DIAGNOSIS "
SEAL_PREFIX = "SAIS_MOSAIC_SEAL "
REVEAL_PREFIX = "SAIS_MOSAIC_REVEAL "
HEX64 = frozenset("0123456789abcdef")


class IssueClient(Protocol):
    issue_number: int

    def post(self, body: str) -> dict[str, Any]: ...

    def comments(self) -> list[dict[str, Any]]: ...


SealCallback = Callable[[dict[str, Any]], str]


def _compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _hex64(value: Any) -> bool:
    text = str(value)
    return len(text) == 64 and all(char in HEX64 for char in text)


def _comment_source(comment: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": int(comment["id"]),
        "created_at": comment.get("created_at"),
        "author": str(comment["user"]["login"]),
    }


def _parse_prefixed(body: str, prefix: str) -> dict[str, Any]:
    if not body.startswith(prefix):
        raise ValueError("comment prefix mismatch")
    value = json.loads(body[len(prefix):])
    if not isinstance(value, dict):
        raise ValueError("subject record must be a JSON object")
    return value


def _probability(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0,1]")
    return value


def _validate_common_subject_fields(
    value: dict[str, Any],
    *,
    expected_fields: set[str],
    trial_id: str,
    core_id: str,
    study_binding_hash: str,
) -> None:
    if set(value) != expected_fields:
        raise ValueError("subject record fields do not match frozen candidate protocol")
    if value.get("protocol_version") != SUBJECT_PROTOCOL:
        raise ValueError("subject protocol mismatch")
    if value.get("trial_id") != trial_id or value.get("core_id") != core_id:
        raise ValueError("subject record identity mismatch")
    if value.get("study_binding_hash") != study_binding_hash:
        raise ValueError("subject record binding mismatch")
    if not isinstance(value.get("rationale"), str) or not value["rationale"].strip():
        raise ValueError("subject rationale must be non-empty")


def validate_p0(
    value: dict[str, Any], trial_id: str, core_id: str, study_binding_hash: str
) -> None:
    fields = {
        "protocol_version", "trial_id", "core_id", "study_binding_hash",
        "p_available", "rationale",
    }
    _validate_common_subject_fields(
        value, expected_fields=fields, trial_id=trial_id,
        core_id=core_id, study_binding_hash=study_binding_hash,
    )
    _probability(value["p_available"], "p_available")


def validate_p1(
    value: dict[str, Any], trial_id: str, core_id: str,
    study_binding_hash: str, cue_hash: str,
) -> None:
    fields = {
        "protocol_version", "trial_id", "core_id", "study_binding_hash",
        "p_available", "observed_cue_hash", "rationale",
    }
    _validate_common_subject_fields(
        value, expected_fields=fields, trial_id=trial_id,
        core_id=core_id, study_binding_hash=study_binding_hash,
    )
    _probability(value["p_available"], "p_available")
    if value.get("observed_cue_hash") != cue_hash:
        raise ValueError("p1 does not bind the exact first cue")


def validate_p2(
    value: dict[str, Any], trial_id: str, core_id: str,
    study_binding_hash: str, evidence_hash: str,
) -> None:
    fields = {
        "protocol_version", "trial_id", "core_id", "study_binding_hash",
        "p_available", "observed_evidence_hash", "rationale",
    }
    _validate_common_subject_fields(
        value, expected_fields=fields, trial_id=trial_id,
        core_id=core_id, study_binding_hash=study_binding_hash,
    )
    _probability(value["p_available"], "p_available")
    if value.get("observed_evidence_hash") != evidence_hash:
        raise ValueError("p2 does not bind the exact two-cue transcript")


def validate_diagnosis(
    value: dict[str, Any], trial_id: str, core_id: str,
    study_binding_hash: str, observed_action: str,
) -> None:
    fields = {
        "protocol_version", "trial_id", "core_id", "study_binding_hash",
        "claimed_condition", "observed_action", "rationale",
    }
    _validate_common_subject_fields(
        value, expected_fields=fields, trial_id=trial_id,
        core_id=core_id, study_binding_hash=study_binding_hash,
    )
    if value.get("claimed_condition") not in CLAIMS:
        raise ValueError("diagnosis condition must be available or degraded")
    if value.get("observed_action") != observed_action:
        raise ValueError("diagnosis does not bind the exact action observation")


def wait_first_subject_record(
    client: IssueClient,
    subject_login: str,
    prefix: str,
    after_id: int,
    timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind the first prefixed subject response; malformed first attempts cannot be repaired."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        comments = sorted(client.comments(), key=lambda item: int(item["id"]))
        candidates = [
            item for item in comments
            if int(item["id"]) > after_id
            and item.get("user", {}).get("login") == subject_login
            and str(item.get("body") or "").startswith(prefix)
        ]
        if candidates:
            first = candidates[0]
            return first, _parse_prefixed(str(first["body"]), prefix)
        time.sleep(0.01)
    raise TimeoutError(f"timed out waiting for {prefix.strip()}")


def _randomization_domain(
    *, core_id: str, study_binding_hash: str, design_hash: str
) -> bytes:
    if not core_id:
        raise ValueError("core_id must be non-empty")
    if not _hex64(study_binding_hash) or not _hex64(design_hash):
        raise ValueError("randomization bindings must be lowercase SHA-256")
    return _compact({
        "protocol_version": PROTOCOL_VERSION,
        "core_id": core_id,
        "study_binding_hash": study_binding_hash,
        "design_hash": design_hash,
    }).encode("utf-8")


def _uniform64(key: bytes, domain: bytes, label: bytes) -> float:
    digest = hmac.new(key, domain + b":" + label, hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def derive_core_realization(
    key: bytes,
    *,
    core_id: str,
    study_binding_hash: str,
    design_hash: str,
    reliability_x: float,
    reliability_y: float,
) -> dict[str, Any]:
    if len(key) != 32:
        raise ValueError("MOSAIC core key must be 256 bits")
    domain = _randomization_domain(
        core_id=core_id,
        study_binding_hash=study_binding_hash,
        design_hash=design_hash,
    )
    truth = "available" if _uniform64(key, domain, b"truth") < 0.5 else "degraded"
    x_correct = _uniform64(key, domain, b"cue-x") < reliability_x
    y_correct = _uniform64(key, domain, b"cue-y") < reliability_y

    def claim(correct: bool) -> str:
        if correct:
            return truth
        return "degraded" if truth == "available" else "available"

    payload = hmac.new(
        key, domain + b":payload", hashlib.sha256
    ).hexdigest()[:32]
    return {
        "core_id": core_id,
        "truth": truth,
        "cue_x_claim": claim(x_correct),
        "cue_y_claim": claim(y_correct),
        "x_correct": x_correct,
        "y_correct": y_correct,
        "payload": payload,
    }


def make_quartet_commitment(
    key: bytes,
    *,
    core_id: str,
    study_binding_hash: str,
    design_hash: str,
    p0_bundle_hash: str,
    baseline_hash: str,
    baseline_seal_reference: str,
) -> str:
    if len(key) != 32:
        raise ValueError("MOSAIC core key must be 256 bits")
    if not all(_hex64(value) for value in (
        study_binding_hash, design_hash, p0_bundle_hash, baseline_hash
    )):
        raise ValueError("commitment bindings must be lowercase SHA-256")
    if not isinstance(baseline_seal_reference, str) or not baseline_seal_reference.strip():
        raise ValueError("baseline seal reference must be non-empty")
    return canonical_hash({
        "protocol_version": PROTOCOL_VERSION,
        "core_id": core_id,
        "study_binding_hash": study_binding_hash,
        "design_hash": design_hash,
        "p0_bundle_hash": p0_bundle_hash,
        "baseline_hash": baseline_hash,
        "baseline_seal_reference": baseline_seal_reference,
        "core_key": key.hex(),
    })


def expected_action(realization: Mapping[str, Any]) -> dict[str, Any]:
    if realization["truth"] == "available":
        return {"success": True, "observation": realization["payload"]}
    return {"success": False, "observation": "CAPABILITY_UNAVAILABLE"}


def frozen_design_hash() -> str:
    return canonical_hash(make_design_matrix())


def validate_core_rows(core_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if len(core_rows) != 4:
        raise ValueError("a MOSAIC quartet must contain exactly four rows")
    core_ids = {row.get("core_id") for row in core_rows}
    frames = {row.get("frame") for row in core_rows}
    profiles = {row.get("reliability_profile") for row in core_rows}
    variants = {row.get("variant") for row in core_rows}
    if len(core_ids) != 1 or len(frames) != 1 or len(profiles) != 1:
        raise ValueError("quartet design identity is inconsistent")
    expected_variants = {
        "canonical", "order_swap", "label_swap", "label_and_order_swap"
    }
    if variants != expected_variants:
        raise ValueError("quartet variants are incomplete")
    trial_ids = [str(row.get("trial_id")) for row in core_rows]
    if len(set(trial_ids)) != 4:
        raise ValueError("quartet trial ids must be unique")
    if any(row.get("hidden_state") is not None for row in core_rows):
        raise ValueError("design shell already contains hidden state")
    if any(row.get("cue_x_claim") is not None or row.get("cue_y_claim") is not None for row in core_rows):
        raise ValueError("design shell already contains cue claims")
    frozen_rows = {str(row["trial_id"]): row for row in make_design_matrix()}
    for row in core_rows:
        trial_id = str(row.get("trial_id"))
        if trial_id not in frozen_rows or row != frozen_rows[trial_id]:
            raise ValueError(f"quartet row does not match frozen design: {trial_id}")
    first = core_rows[0]
    reliabilities = first.get("reliabilities")
    if not isinstance(reliabilities, dict) or set(reliabilities) != {"X", "Y"}:
        raise ValueError("quartet reliability mapping is invalid")
    core = CoreSpec(
        core_id=str(first["core_id"]),
        frame=str(first["frame"]),
        reliability_profile=str(first["reliability_profile"]),
        reliability_x=float(reliabilities["X"]),
        reliability_y=float(reliabilities["Y"]),
    )
    for row in core_rows:
        expected = variant_spec(core, str(row["variant"]))
        for field in ("frame", "reliability_profile", "prior", "cue_order", "labels", "reliabilities"):
            if row.get(field) != expected[field]:
                raise ValueError(f"quartet design transform mismatch: {field}")
    return {
        "core_id": str(next(iter(core_ids))),
        "frame": str(next(iter(frames))),
        "reliability_profile": str(next(iter(profiles))),
        "trial_ids": trial_ids,
    }


def _cue_record(
    row: Mapping[str, Any], cue_id: str, cue_index: int,
    realization: Mapping[str, Any], commitment: str,
) -> dict[str, Any]:
    claim = realization["cue_x_claim"] if cue_id == "X" else realization["cue_y_claim"]
    cue = {
        "protocol_version": "SAIS/MOSAIC/CUE/1",
        "trial_id": row["trial_id"],
        "core_id": row["core_id"],
        "cue_index": cue_index,
        "source_label": row["labels"][cue_id],
        "claim": claim,
        "stated_reliability": row["reliabilities"][cue_id],
        "quartet_commitment": commitment,
    }
    validate_cue_record(cue)
    return cue


def subject_protocol_audit(
    client: IssueClient, subject_login: str
) -> dict[str, Any]:
    prefixes = (P0_PREFIX, P1_PREFIX, P2_PREFIX, DIAGNOSIS_PREFIX)
    counts = {prefix.strip(): 0 for prefix in prefixes}
    unexpected: list[int] = []
    total = 0
    for comment in client.comments():
        if comment.get("user", {}).get("login") != subject_login:
            continue
        total += 1
        body = str(comment.get("body") or "")
        matched = False
        for prefix in prefixes:
            if body.startswith(prefix):
                counts[prefix.strip()] += 1
                matched = True
                break
        if not matched:
            unexpected.append(int(comment["id"]))
    return {
        "counts": counts,
        "unexpected_subject_comment_ids": unexpected,
        "total_subject_comments": total,
    }


def subject_protocol_counts(
    client: IssueClient, subject_login: str
) -> dict[str, int]:
    return dict(subject_protocol_audit(client, subject_login)["counts"])


def _protocol_counts_valid(counts: Mapping[str, int]) -> bool:
    return all(counts.get(prefix.strip()) == 1 for prefix in (
        P0_PREFIX, P1_PREFIX, P2_PREFIX, DIAGNOSIS_PREFIX
    ))


def _phase_counts_valid(
    counts: Mapping[str, int], *, p0: int, p1: int, p2: int, diagnosis: int
) -> bool:
    expected = {
        P0_PREFIX.strip(): p0,
        P1_PREFIX.strip(): p1,
        P2_PREFIX.strip(): p2,
        DIAGNOSIS_PREFIX.strip(): diagnosis,
    }
    return dict(counts) == expected


def _phase_audit_valid(
    audit: Mapping[str, Any], *, p0: int, p1: int, p2: int, diagnosis: int
) -> bool:
    unexpected = audit.get("unexpected_subject_comment_ids")
    counts = audit.get("counts")
    return (
        isinstance(unexpected, list)
        and not unexpected
        and isinstance(counts, Mapping)
        and _phase_counts_valid(
            counts, p0=p0, p1=p1, p2=p2, diagnosis=diagnosis
        )
    )


def _ideal_path_for_trial(
    cues: Sequence[dict[str, Any]],
) -> list[float]:
    objects = [
        Cue(
            cue_id=f"cue-{index}",
            claim=str(cue["claim"]),
            reliability=float(cue["stated_reliability"]),
            source_label=str(cue["source_label"]),
        )
        for index, cue in enumerate(cues, start=1)
    ]
    return posterior_path(0.5, objects)


def run_quartet(
    clients: Mapping[str, IssueClient],
    core_rows: Sequence[dict[str, Any]],
    *,
    subject_login: str,
    study_binding_hash: str,
    design_hash: str,
    baseline_seal_callback: SealCallback,
    seal_callback: SealCallback,
    seal_envelope_callback: SealCallback,
    timeout_seconds: float = 1.0,
) -> dict[str, Any]:
    identity = validate_core_rows(core_rows)
    if not _hex64(study_binding_hash) or not _hex64(design_hash):
        raise ValueError("study and design bindings must be lowercase SHA-256")
    if design_hash != frozen_design_hash():
        raise ValueError("design_hash does not match the frozen 64-row design")
    rows = {str(row["trial_id"]): dict(row) for row in core_rows}
    trial_ids = identity["trial_ids"]
    if set(clients) != set(trial_ids):
        raise ValueError("client mapping must match quartet trial ids exactly")
    issue_numbers = [int(clients[trial_id].issue_number) for trial_id in trial_ids]
    if len(issue_numbers) != len(set(issue_numbers)):
        raise ValueError("quartet issue numbers must be unique")
    for trial_id in trial_ids:
        if clients[trial_id].comments():
            raise ValueError(f"quartet issue is not empty before READY: {trial_id}")

    ready_comments: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        row = rows[trial_id]
        payload = {
            "protocol_version": PROTOCOL_VERSION,
            "trial_id": trial_id,
            "core_id": identity["core_id"],
            "variant": row["variant"],
            "study_binding_hash": study_binding_hash,
            "design_hash": design_hash,
            "prior_available": 0.5,
            "next": P0_PREFIX.strip(),
        }
        ready_comments[trial_id] = clients[trial_id].post(
            READY_PREFIX + _compact(payload)
        )

    p0_records: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        comment, record = wait_first_subject_record(
            clients[trial_id], subject_login, P0_PREFIX,
            int(ready_comments[trial_id]["id"]), timeout_seconds,
        )
        validate_p0(record, trial_id, identity["core_id"], study_binding_hash)
        p0_records[trial_id] = {
            "record": record,
            "source_comment": _comment_source(comment),
            "ready_comment_id": int(ready_comments[trial_id]["id"]),
        }

    # Critical barrier: baseline records are unique and immutably sealed before entropy exists.
    for trial_id in trial_ids:
        audit = subject_protocol_audit(clients[trial_id], subject_login)
        if not _phase_audit_valid(audit, p0=1, p1=0, p2=0, diagnosis=0):
            raise ValueError(
                f"pre-randomization subject protocol violation for {trial_id}: {audit}"
            )
    p0_bundle_hash = canonical_hash(p0_records)
    baseline_ledger = {
        "protocol_version": PROTOCOL_VERSION,
        "core_id": identity["core_id"],
        "study_binding_hash": study_binding_hash,
        "design_hash": design_hash,
        "p0_bundle_hash": p0_bundle_hash,
        "p0_records": p0_records,
    }
    baseline_hash = canonical_hash(baseline_ledger)
    baseline_seal_reference = baseline_seal_callback(json.loads(json.dumps(baseline_ledger)))
    if not isinstance(baseline_seal_reference, str) or not baseline_seal_reference.strip():
        raise RuntimeError("baseline seal callback must return a non-empty immutable reference")
    p0_seal_comments: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        payload = {
            "protocol_version": PROTOCOL_VERSION,
            "trial_id": trial_id,
            "core_id": identity["core_id"],
            "study_binding_hash": study_binding_hash,
            "design_hash": design_hash,
            "p0_bundle_hash": p0_bundle_hash,
            "baseline_hash": baseline_hash,
            "baseline_seal_reference": baseline_seal_reference,
        }
        p0_seal_comments[trial_id] = clients[trial_id].post(
            P0_SEAL_PREFIX + _compact(payload)
        )

    # Hidden entropy is generated only after all four public baseline seals exist.
    key = secrets.token_bytes(32)
    first = rows[trial_ids[0]]
    realization = derive_core_realization(
        key,
        core_id=identity["core_id"],
        study_binding_hash=study_binding_hash,
        design_hash=design_hash,
        reliability_x=float(first["reliabilities"]["X"]),
        reliability_y=float(first["reliabilities"]["Y"]),
    )
    commitment = make_quartet_commitment(
        key,
        core_id=identity["core_id"],
        study_binding_hash=study_binding_hash,
        design_hash=design_hash,
        p0_bundle_hash=p0_bundle_hash,
        baseline_hash=baseline_hash,
        baseline_seal_reference=baseline_seal_reference,
    )
    commit_comments: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        payload = {
            "protocol_version": PROTOCOL_VERSION,
            "trial_id": trial_id,
            "core_id": identity["core_id"],
            "study_binding_hash": study_binding_hash,
            "design_hash": design_hash,
            "quartet_commitment": commitment,
            "p0_bundle_hash": p0_bundle_hash,
        }
        commit_comments[trial_id] = clients[trial_id].post(
            COMMIT_PREFIX + _compact(payload)
        )

    cue_records: dict[str, list[dict[str, Any]]] = {trial_id: [] for trial_id in trial_ids}
    cue_comments: dict[str, list[dict[str, Any]]] = {trial_id: [] for trial_id in trial_ids}
    p1_records: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        row = rows[trial_id]
        cue_id = str(row["cue_order"][0])
        cue = _cue_record(row, cue_id, 1, realization, commitment)
        cue_hash = canonical_hash(cue)
        payload = {**cue, "cue_hash": cue_hash}
        comment = clients[trial_id].post(CUE1_PREFIX + _compact(payload))
        cue_records[trial_id].append(cue)
        cue_comments[trial_id].append(comment)

    # Barrier: all first cues are posted before any second cue exists.
    for trial_id in trial_ids:
        cue = cue_records[trial_id][0]
        cue_hash = canonical_hash(cue)
        comment, record = wait_first_subject_record(
            clients[trial_id], subject_login, P1_PREFIX,
            int(cue_comments[trial_id][0]["id"]), timeout_seconds,
        )
        validate_p1(
            record, trial_id, identity["core_id"], study_binding_hash, cue_hash
        )
        p1_records[trial_id] = {
            "record": record,
            "source_comment": _comment_source(comment),
            "cue_comment_id": int(cue_comments[trial_id][0]["id"]),
            "cue_hash": cue_hash,
        }

    for trial_id in trial_ids:
        audit = subject_protocol_audit(clients[trial_id], subject_login)
        if not _phase_audit_valid(audit, p0=1, p1=1, p2=0, diagnosis=0):
            raise ValueError(
                f"post-cue1 subject protocol violation for {trial_id}: {audit}"
            )

    # Barrier: cue2 is not posted until every p1 record is valid and unique.
    p2_records: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        row = rows[trial_id]
        cue_id = str(row["cue_order"][1])
        cue = _cue_record(row, cue_id, 2, realization, commitment)
        cue_hash = canonical_hash(cue)
        payload = {**cue, "cue_hash": cue_hash}
        comment = clients[trial_id].post(CUE2_PREFIX + _compact(payload))
        cue_records[trial_id].append(cue)
        cue_comments[trial_id].append(comment)

    for trial_id in trial_ids:
        evidence_hash = canonical_hash(cue_records[trial_id])
        comment, record = wait_first_subject_record(
            clients[trial_id], subject_login, P2_PREFIX,
            int(cue_comments[trial_id][1]["id"]), timeout_seconds,
        )
        validate_p2(
            record, trial_id, identity["core_id"],
            study_binding_hash, evidence_hash,
        )
        p2_records[trial_id] = {
            "record": record,
            "source_comment": _comment_source(comment),
            "cue_comment_id": int(cue_comments[trial_id][1]["id"]),
            "evidence_hash": evidence_hash,
        }

    for trial_id in trial_ids:
        audit = subject_protocol_audit(clients[trial_id], subject_login)
        if not _phase_audit_valid(audit, p0=1, p1=1, p2=1, diagnosis=0):
            raise ValueError(
                f"pre-action subject protocol violation for {trial_id}: {audit}"
            )

    # Barrier: controlled action occurs only after all four p2 forecasts are valid and unique.
    action = expected_action(realization)
    action_comments: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        payload = {
            "protocol_version": PROTOCOL_VERSION,
            "trial_id": trial_id,
            "core_id": identity["core_id"],
            "study_binding_hash": study_binding_hash,
            "quartet_commitment": commitment,
            **action,
        }
        action_comments[trial_id] = clients[trial_id].post(
            ACTION_PREFIX + _compact(payload)
        )

    diagnosis_records: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        comment, record = wait_first_subject_record(
            clients[trial_id], subject_login, DIAGNOSIS_PREFIX,
            int(action_comments[trial_id]["id"]), timeout_seconds,
        )
        validate_diagnosis(
            record, trial_id, identity["core_id"],
            study_binding_hash, str(action["observation"]),
        )
        diagnosis_records[trial_id] = {
            "record": record,
            "source_comment": _comment_source(comment),
            "action_comment_id": int(action_comments[trial_id]["id"]),
        }

    transcript_audit: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        audit = subject_protocol_audit(clients[trial_id], subject_login)
        transcript_audit[trial_id] = audit
        if not _phase_audit_valid(audit, p0=1, p1=1, p2=1, diagnosis=1):
            raise ValueError(
                f"subject protocol response count violation for {trial_id}: {audit}"
            )

    trials: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        ideal = _ideal_path_for_trial(cue_records[trial_id])
        trials[trial_id] = {
            "issue_number": int(clients[trial_id].issue_number),
            "design_row": rows[trial_id],
            "ready_comment": _comment_source(ready_comments[trial_id]),
            "p0": p0_records[trial_id],
            "p0_seal_comment": _comment_source(p0_seal_comments[trial_id]),
            "commit_comment": _comment_source(commit_comments[trial_id]),
            "cues": cue_records[trial_id],
            "cue_comments": [
                _comment_source(item) for item in cue_comments[trial_id]
            ],
            "p1": p1_records[trial_id],
            "p2": p2_records[trial_id],
            "ideal_probability_path": ideal,
            "action": action,
            "action_comment": _comment_source(action_comments[trial_id]),
            "diagnosis": diagnosis_records[trial_id],
            "subject_protocol_audit": transcript_audit[trial_id],
        }

    ledger = {
        "protocol_version": PROTOCOL_VERSION,
        "core_id": identity["core_id"],
        "frame": identity["frame"],
        "reliability_profile": identity["reliability_profile"],
        "study_binding_hash": study_binding_hash,
        "design_hash": design_hash,
        "quartet_commitment": commitment,
        "p0_bundle_hash": p0_bundle_hash,
        "baseline_hash": baseline_hash,
        "baseline_seal_reference": baseline_seal_reference,
        "subject_login": subject_login,
        "trials": trials,
    }
    ledger_hash = canonical_hash(ledger)
    ledger_seal_reference = seal_callback(json.loads(json.dumps(ledger)))
    if not isinstance(ledger_seal_reference, str) or not ledger_seal_reference.strip():
        raise RuntimeError("seal callback must return a non-empty immutable reference")
    seal_envelope = {
        "protocol_version": PROTOCOL_VERSION,
        "core_id": identity["core_id"],
        "study_binding_hash": study_binding_hash,
        "design_hash": design_hash,
        "quartet_commitment": commitment,
        "baseline_hash": baseline_hash,
        "baseline_seal_reference": baseline_seal_reference,
        "ledger_hash": ledger_hash,
        "ledger_seal_reference": ledger_seal_reference,
    }
    seal_envelope_hash = canonical_hash(seal_envelope)
    seal_envelope_reference = seal_envelope_callback(
        json.loads(json.dumps(seal_envelope))
    )
    if not isinstance(seal_envelope_reference, str) or not seal_envelope_reference.strip():
        raise RuntimeError(
            "seal envelope callback must return a non-empty immutable reference"
        )

    seal_comments: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        payload = {
            "protocol_version": PROTOCOL_VERSION,
            "trial_id": trial_id,
            "core_id": identity["core_id"],
            "study_binding_hash": study_binding_hash,
            "ledger_hash": ledger_hash,
            "ledger_seal_reference": ledger_seal_reference,
            "seal_envelope_hash": seal_envelope_hash,
            "seal_envelope_reference": seal_envelope_reference,
        }
        seal_comments[trial_id] = clients[trial_id].post(
            SEAL_PREFIX + _compact(payload)
        )

    reveal = {
        "protocol_version": PROTOCOL_VERSION,
        "core_id": identity["core_id"],
        "study_binding_hash": study_binding_hash,
        "design_hash": design_hash,
        "quartet_commitment": commitment,
        "p0_bundle_hash": p0_bundle_hash,
        "baseline_hash": baseline_hash,
        "baseline_seal_reference": baseline_seal_reference,
        "ledger_hash": ledger_hash,
        "ledger_seal_reference": ledger_seal_reference,
        "seal_envelope": seal_envelope,
        "seal_envelope_hash": seal_envelope_hash,
        "seal_envelope_reference": seal_envelope_reference,
        "core_key": key.hex(),
        "realization": realization,
    }
    verification = verify_sealed_quartet(ledger, reveal)
    if not verification.get("valid"):
        failed = sorted(name for name, passed in verification.items() if not passed)
        raise RuntimeError("sealed quartet verification failed: " + ", ".join(failed))

    # Key disclosure is fail-closed behind local verification of the sealed ledger.
    reveal_comments: dict[str, dict[str, Any]] = {}
    for trial_id in trial_ids:
        payload = {**reveal, "trial_id": trial_id}
        reveal_comments[trial_id] = clients[trial_id].post(
            REVEAL_PREFIX + _compact(payload)
        )
    return {
        "ledger": ledger,
        "reveal": reveal,
        "seal_comments": {
            trial_id: _comment_source(comment)
            for trial_id, comment in seal_comments.items()
        },
        "reveal_comments": {
            trial_id: _comment_source(comment)
            for trial_id, comment in reveal_comments.items()
        },
        "verification": verification,
    }


def verify_sealed_quartet(
    ledger: dict[str, Any], reveal: dict[str, Any]
) -> dict[str, bool]:
    try:
        key = bytes.fromhex(str(reveal["core_key"]))
        trials = ledger["trials"]
        if not isinstance(trials, dict) or len(trials) != 4:
            raise ValueError("invalid trial container")
        rows = [trial["design_row"] for trial in trials.values()]
        identity = validate_core_rows(rows)
        first = rows[0]
        reliabilities = first["reliabilities"]
        realization = derive_core_realization(
            key,
            core_id=identity["core_id"],
            study_binding_hash=str(ledger["study_binding_hash"]),
            design_hash=str(ledger["design_hash"]),
            reliability_x=float(reliabilities["X"]),
            reliability_y=float(reliabilities["Y"]),
        )
    except (KeyError, TypeError, ValueError):
        return {"structure_valid": False, "valid": False}
    if len(key) != 32:
        return {"structure_valid": False, "valid": False}

    expected_action_record = expected_action(realization)
    p0_bundle = {
        trial_id: trials[trial_id]["p0"]
        for trial_id in identity["trial_ids"]
    }
    expected_p0_bundle_hash = canonical_hash(p0_bundle)
    baseline_ledger = {
        "protocol_version": PROTOCOL_VERSION,
        "core_id": identity["core_id"],
        "study_binding_hash": ledger.get("study_binding_hash"),
        "design_hash": ledger.get("design_hash"),
        "p0_bundle_hash": expected_p0_bundle_hash,
        "p0_records": p0_bundle,
    }
    expected_baseline_hash = canonical_hash(baseline_ledger)
    checks: dict[str, bool] = {
        "structure_valid": True,
        "protocol_version": ledger.get("protocol_version") == PROTOCOL_VERSION,
        "reveal_protocol": reveal.get("protocol_version") == PROTOCOL_VERSION,
        "core_id": ledger.get("core_id") == identity["core_id"] == reveal.get("core_id"),
        "study_binding": ledger.get("study_binding_hash") == reveal.get("study_binding_hash"),
        "design_binding": ledger.get("design_hash") == reveal.get("design_hash")
        == frozen_design_hash(),
        "commitment": ledger.get("quartet_commitment")
        == reveal.get("quartet_commitment")
        == make_quartet_commitment(
            key,
            core_id=identity["core_id"],
            study_binding_hash=str(ledger.get("study_binding_hash")),
            design_hash=str(ledger.get("design_hash")),
            p0_bundle_hash=expected_p0_bundle_hash,
            baseline_hash=expected_baseline_hash,
            baseline_seal_reference=str(ledger.get("baseline_seal_reference")),
        ),
        "realization": reveal.get("realization") == realization,
        "p0_bundle_hash": ledger.get("p0_bundle_hash")
        == reveal.get("p0_bundle_hash")
        == expected_p0_bundle_hash,
        "baseline_hash": ledger.get("baseline_hash")
        == reveal.get("baseline_hash")
        == expected_baseline_hash,
        "baseline_seal_reference": isinstance(ledger.get("baseline_seal_reference"), str)
        and ledger.get("baseline_seal_reference") == reveal.get("baseline_seal_reference")
        and bool(str(ledger.get("baseline_seal_reference", "")).strip()),
        "ledger_hash": reveal.get("ledger_hash") == canonical_hash(ledger),
        "ledger_seal_reference": isinstance(reveal.get("ledger_seal_reference"), str)
        and bool(str(reveal.get("ledger_seal_reference", "")).strip()),
        "seal_envelope_reference": isinstance(reveal.get("seal_envelope_reference"), str)
        and bool(str(reveal.get("seal_envelope_reference", "")).strip()),
    }

    expected_seal_envelope = {
        "protocol_version": PROTOCOL_VERSION,
        "core_id": identity["core_id"],
        "study_binding_hash": ledger.get("study_binding_hash"),
        "design_hash": ledger.get("design_hash"),
        "quartet_commitment": ledger.get("quartet_commitment"),
        "baseline_hash": expected_baseline_hash,
        "baseline_seal_reference": ledger.get("baseline_seal_reference"),
        "ledger_hash": canonical_hash(ledger),
        "ledger_seal_reference": reveal.get("ledger_seal_reference"),
    }
    checks.update({
        "seal_envelope": reveal.get("seal_envelope") == expected_seal_envelope,
        "seal_envelope_hash": reveal.get("seal_envelope_hash")
        == canonical_hash(expected_seal_envelope),
    })

    issue_numbers: list[int] = []
    final_ideals: list[float] = []
    trial_checks: list[bool] = []
    for trial_id in identity["trial_ids"]:
        trial = trials[trial_id]
        row = trial["design_row"]
        expected_cues = [
            _cue_record(
                row,
                str(row["cue_order"][index]),
                index + 1,
                realization,
                str(ledger["quartet_commitment"]),
            )
            for index in range(2)
        ]
        actual_cues = trial.get("cues")
        ideal_path = _ideal_path_for_trial(expected_cues)
        final_ideals.append(ideal_path[-1])
        issue_numbers.append(int(trial["issue_number"]))
        try:
            validate_p0(
                trial["p0"]["record"], trial_id, identity["core_id"],
                str(ledger["study_binding_hash"]),
            )
            validate_p1(
                trial["p1"]["record"], trial_id, identity["core_id"],
                str(ledger["study_binding_hash"]), canonical_hash(expected_cues[0]),
            )
            validate_p2(
                trial["p2"]["record"], trial_id, identity["core_id"],
                str(ledger["study_binding_hash"]), canonical_hash(expected_cues),
            )
            validate_diagnosis(
                trial["diagnosis"]["record"], trial_id, identity["core_id"],
                str(ledger["study_binding_hash"]),
                str(expected_action_record["observation"]),
            )
            records_valid = True
        except (KeyError, TypeError, ValueError):
            records_valid = False

        try:
            ready_id = int(trial["ready_comment"]["id"])
            p0_id = int(trial["p0"]["source_comment"]["id"])
            p0_seal_id = int(trial["p0_seal_comment"]["id"])
            commit_id = int(trial["commit_comment"]["id"])
            cue_ids = [int(item["id"]) for item in trial["cue_comments"]]
            p1_id = int(trial["p1"]["source_comment"]["id"])
            p2_id = int(trial["p2"]["source_comment"]["id"])
            action_id = int(trial["action_comment"]["id"])
            diagnosis_id = int(trial["diagnosis"]["source_comment"]["id"])
            temporal_valid = (
                len(cue_ids) == 2
                and ready_id < p0_id < p0_seal_id < commit_id < cue_ids[0]
                < p1_id < cue_ids[1] < p2_id < action_id < diagnosis_id
                and int(trial["p0"]["ready_comment_id"]) == ready_id
                and int(trial["p1"]["cue_comment_id"]) == cue_ids[0]
                and int(trial["p2"]["cue_comment_id"]) == cue_ids[1]
                and int(trial["diagnosis"]["action_comment_id"]) == action_id
            )
        except (KeyError, TypeError, ValueError, IndexError):
            temporal_valid = False

        protocol_audit = trial.get("subject_protocol_audit", {})
        trial_checks.append(
            records_valid
            and actual_cues == expected_cues
            and trial.get("ideal_probability_path") == ideal_path
            and trial.get("action") == expected_action_record
            and temporal_valid
            and isinstance(protocol_audit, dict)
            and _phase_audit_valid(
                protocol_audit, p0=1, p1=1, p2=1, diagnosis=1
            )
        )

    checks.update({
        "four_trials": len(trials) == 4,
        "trial_ids_exact": set(trials) == set(identity["trial_ids"]),
        "issue_numbers_unique": len(issue_numbers) == len(set(issue_numbers)) == 4,
        "subject_login": isinstance(ledger.get("subject_login"), str)
        and bool(str(ledger.get("subject_login")).strip()),
        "trial_records_valid": len(trial_checks) == 4 and all(trial_checks),
        "action_matches_truth": all(
            trial.get("action") == expected_action_record
            for trial in trials.values()
        ),
        "final_bayes_quartet_invariant": len(final_ideals) == 4
        and max(final_ideals) - min(final_ideals) < 1e-12,
    })
    checks["valid"] = all(checks.values())
    return checks
