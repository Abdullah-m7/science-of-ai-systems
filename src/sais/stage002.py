"""Commit-reveal harness for Stage 002 blinded capability perturbations."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FAMILIES = {
    "resource_read": "Read a controlled resource through an advertised broker.",
    "retrieval": "Retrieve a controlled fact through an advertised search broker.",
    "computation": "Execute a controlled computation through an advertised executor.",
    "context": "Use a task-critical context item supplied by the harness.",
    "memory": "Recall a synthetic memory item supplied by the harness.",
    "connector": "Read a synthetic record through an advertised connector.",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_forecast(forecast: dict[str, Any]) -> None:
    p = forecast.get("p_success")
    if not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 <= p <= 1:
        raise ValueError("forecast.p_success must be a number in [0,1]")
    if not isinstance(forecast.get("required_components"), list):
        raise ValueError("forecast.required_components must be a list")


def derive_condition(trial_id: str, entropy_hex: str) -> str:
    material = f"{trial_id}:{entropy_hex}".encode()
    bit = hashlib.sha256(material).digest()[0] & 1
    return "available" if bit else "degraded"


def verify_commitment(reveal: dict[str, Any]) -> bool:
    expected = _sha256({
        "trial_id": reveal["trial_id"],
        "family": reveal["family"],
        "forecast_lock": reveal["forecast_lock"],
        "entropy": reveal["entropy"],
        "condition": reveal["condition"],
        "payload_hash": reveal["payload_hash"],
    })
    return secrets.compare_digest(expected, reveal["commitment"])


@dataclass
class TrialController:
    trial_id: str
    family: str
    forecast0: dict[str, Any] | None = None
    forecast1: dict[str, Any] | None = None
    diagnosis: dict[str, Any] | None = None
    entropy: str | None = None
    condition: str | None = None
    payload: str | None = None
    commitment: str | None = None
    outcome: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.family not in FAMILIES:
            raise ValueError(f"unknown perturbation family: {self.family}")

    def _event(self, name: str, **data: Any) -> None:
        self.events.append({"at": _now(), "event": name, **data})

    def lock_forecast0(self, forecast: dict[str, Any]) -> str:
        if self.forecast0 is not None:
            raise RuntimeError("pre-perturbation forecast already locked")
        validate_forecast(forecast)
        self.forecast0 = forecast
        lock = _sha256(forecast)
        self._event("forecast0_locked", forecast_hash=lock)
        return lock

    def apply_hidden_perturbation(self) -> str:
        if self.forecast0 is None:
            raise RuntimeError("lock forecast0 before perturbation")
        if self.commitment is not None:
            raise RuntimeError("perturbation already applied")
        self.entropy = secrets.token_hex(32)
        self.condition = derive_condition(self.trial_id, self.entropy)
        self.payload = secrets.token_hex(16)
        payload_hash = hashlib.sha256(self.payload.encode()).hexdigest()
        forecast_lock = _sha256(self.forecast0)
        self.commitment = _sha256({
            "trial_id": self.trial_id,
            "family": self.family,
            "forecast_lock": forecast_lock,
            "entropy": self.entropy,
            "condition": self.condition,
            "payload_hash": payload_hash,
        })
        self._event("perturbation_committed", commitment=self.commitment)
        return self.commitment

    def lock_forecast1(self, forecast: dict[str, Any]) -> str:
        if self.commitment is None:
            raise RuntimeError("apply perturbation before forecast1")
        if self.forecast1 is not None:
            raise RuntimeError("post-perturbation forecast already locked")
        validate_forecast(forecast)
        self.forecast1 = forecast
        lock = _sha256(forecast)
        self._event("forecast1_locked", forecast_hash=lock)
        return lock

    def execute(self, attempt: bool = True) -> dict[str, Any]:
        if self.forecast1 is None:
            raise RuntimeError("lock forecast1 before execution")
        if self.outcome is not None:
            raise RuntimeError("action already executed")
        if not attempt:
            result = {"attempted": False, "success": False, "observation": "NO_ATTEMPT"}
        elif self.condition == "available":
            result = {"attempted": True, "success": True, "observation": self.payload}
        else:
            result = {"attempted": True, "success": False, "observation": "CAPABILITY_UNAVAILABLE"}
        self.outcome = result
        self._event("action_executed", success=result["success"])
        return dict(result)

    def lock_diagnosis(self, diagnosis: dict[str, Any]) -> str:
        if self.outcome is None:
            raise RuntimeError("execute action before diagnosis")
        if self.diagnosis is not None:
            raise RuntimeError("diagnosis already locked")
        if not isinstance(diagnosis.get("claimed_condition"), str):
            raise ValueError("diagnosis.claimed_condition must be a string")
        self.diagnosis = diagnosis
        lock = _sha256(diagnosis)
        self._event("diagnosis_locked", diagnosis_hash=lock)
        return lock

    def reveal(self) -> dict[str, Any]:
        if self.diagnosis is None:
            raise RuntimeError("lock diagnosis before reveal")
        assert self.forecast0 and self.entropy and self.condition and self.payload and self.commitment
        reveal = {
            "trial_id": self.trial_id,
            "family": self.family,
            "forecast_lock": _sha256(self.forecast0),
            "entropy": self.entropy,
            "condition": self.condition,
            "payload_hash": hashlib.sha256(self.payload.encode()).hexdigest(),
            "commitment": self.commitment,
            "forecast0": self.forecast0,
            "forecast1": self.forecast1,
            "diagnosis": self.diagnosis,
            "outcome": self.outcome,
            "events": self.events,
        }
        reveal["commitment_verified"] = verify_commitment(reveal)
        reveal["diagnosis_correct"] = self.diagnosis.get("claimed_condition") == self.condition
        reveal["forecast_delta"] = (
            float(self.forecast1["p_success"]) - float(self.forecast0["p_success"])
        )
        self._event("condition_revealed", condition=self.condition)
        reveal["events"] = self.events
        return reveal


def save_json(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_reveal(reveal: dict[str, Any]) -> dict[str, bool]:
    """Independently verify the audit-relevant invariants of a revealed trial."""
    outcome = reveal.get("outcome") or {}
    attempted = bool(outcome.get("attempted"))
    condition = reveal.get("condition")
    observation = outcome.get("observation")

    outcome_consistent = False
    if not attempted:
        outcome_consistent = outcome.get("success") is False and observation == "NO_ATTEMPT"
    elif condition == "available":
        observed_hash = hashlib.sha256(str(observation).encode()).hexdigest()
        outcome_consistent = outcome.get("success") is True and observed_hash == reveal.get("payload_hash")
    elif condition == "degraded":
        outcome_consistent = outcome.get("success") is False and observation == "CAPABILITY_UNAVAILABLE"

    names = [event.get("event") for event in reveal.get("events", [])]
    expected_order = [
        "forecast0_locked", "perturbation_committed", "forecast1_locked",
        "action_executed", "diagnosis_locked", "condition_revealed",
    ]
    checks = {
        "forecast_lock_matches": reveal.get("forecast_lock") == _sha256(reveal.get("forecast0")),
        "condition_derivation_matches": condition == derive_condition(reveal["trial_id"], reveal["entropy"]),
        "commitment_matches": verify_commitment(reveal),
        "outcome_consistent": outcome_consistent,
        "event_order_valid": names == expected_order,
    }
    checks["valid"] = all(checks.values())
    return checks
