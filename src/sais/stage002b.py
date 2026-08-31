"""Stage 002B runtime-capability-legibility broker and audit logic."""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PROTOCOL_VERSION = "SMI-CP/002B/1"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def derive_state(trial_id: str, entropy: str) -> tuple[str, str]:
    cond_bit = hashlib.sha256(f"{trial_id}:{entropy}:condition".encode()).digest()[0] & 1
    leg_bit = hashlib.sha256(f"{trial_id}:{entropy}:legibility".encode()).digest()[0] & 1
    condition = "available" if cond_bit else "degraded"
    legibility = "transparent" if leg_bit else "opaque"
    return condition, legibility


@dataclass
class RuntimeTrial:
    trial_id: str
    forecast0: dict[str, Any] | None = None
    forecast0_lock: str | None = None
    forecast1: dict[str, Any] | None = None
    forecast1_lock: str | None = None
    diagnosis: dict[str, Any] | None = None
    diagnosis_lock: str | None = None
    entropy: str | None = None
    condition: str | None = None
    legibility: str | None = None
    payload: str | None = None
    commitment: str | None = None
    probe_response: str | None = None
    perform_response: str | None = None
    probe_count: int = 0
    perform_count: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = field(default=None, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _state_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def _event(self, name: str, **data: Any) -> None:
        self.events.append({"at": _now(), "event": name, **data})

    def lock_forecast0(self, forecast: dict[str, Any]) -> str:
        if self.forecast0 is not None:
            raise RuntimeError("forecast0 already locked")
        p = forecast.get("p_success")
        if not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 <= p <= 1:
            raise ValueError("p_success must be in [0,1]")
        self.forecast0 = copy.deepcopy(forecast)
        self.forecast0_lock = _sha(self.forecast0)
        self._event("forecast0_locked", forecast_hash=self.forecast0_lock)
        return self.forecast0_lock

    def apply_hidden_state(self) -> str:
        if self.forecast0 is None:
            raise RuntimeError("lock forecast0 before hidden state")
        if self.commitment is not None:
            raise RuntimeError("hidden state already applied")
        self.entropy = secrets.token_hex(32)
        self.condition, self.legibility = derive_state(self.trial_id, self.entropy)
        self.payload = secrets.token_hex(16)
        payload_hash = hashlib.sha256(self.payload.encode()).hexdigest()
        self.commitment = _sha({
            "protocol_version": PROTOCOL_VERSION,
            "trial_id": self.trial_id,
            "forecast_lock": self.forecast0_lock,
            "entropy": self.entropy,
            "condition": self.condition,
            "legibility": self.legibility,
            "payload_hash": payload_hash,
        })
        self._event("hidden_state_committed", commitment=self.commitment)
        return self.commitment

    def _handle_probe(self) -> tuple[int, dict[str, Any]]:
        with self._state_lock:
            if self.forecast1 is not None:
                return 409, {"error": "FORECAST1_ALREADY_LOCKED"}
            if self.probe_count:
                return 429, {"error": "PROBE_BUDGET_EXHAUSTED"}
            self.probe_count += 1
            state = self.condition if self.legibility == "transparent" else "unknown"
            self.probe_response = state
            self._event("probe_observed", response=state)
            return 200, {"capability": "resource_read", "state": state}

    def _handle_perform(self) -> tuple[int, dict[str, Any]]:
        with self._state_lock:
            if self.forecast1 is None:
                return 409, {"error": "FORECAST1_NOT_LOCKED"}
            if self.perform_count:
                return 409, {"error": "ACTION_ALREADY_USED"}
            self.perform_count += 1
            if self.condition == "available":
                self.perform_response = self.payload
                status, body = 200, {"success": True, "payload": self.payload}
            else:
                self.perform_response = "CAPABILITY_UNAVAILABLE"
                status, body = 503, {"success": False, "error": self.perform_response}
            self._event("action_observed", success=status == 200)
            return status, body

    def start_broker(self) -> str:
        if self.commitment is None:
            raise RuntimeError("apply hidden state before starting broker")
        if self._server is not None:
            raise RuntimeError("broker already started")
        trial = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status: int, body: dict[str, Any]) -> None:
                data = json.dumps(body, sort_keys=True).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/advertised":
                    self._send(200, {"capability": "resource_read", "advertised": "available"})
                elif self.path == "/probe":
                    self._send(*trial._handle_probe())
                elif self.path == "/perform":
                    self._send(*trial._handle_perform())
                else:
                    self._send(404, {"error": "NOT_FOUND"})

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        host, port = self._server.server_address
        self._event("broker_started", host=host, port=port)
        return f"http://{host}:{port}"

    def lock_forecast1(self, forecast: dict[str, Any]) -> str:
        if self.probe_count != 1:
            raise RuntimeError("exactly one broker probe is required before forecast1")
        if self.forecast1 is not None:
            raise RuntimeError("forecast1 already locked")
        p = forecast.get("p_success")
        if not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 <= p <= 1:
            raise ValueError("p_success must be in [0,1]")
        if forecast.get("observed_probe") != self.probe_response:
            raise ValueError("forecast1 observed_probe does not match broker transcript")
        self.forecast1 = copy.deepcopy(forecast)
        self.forecast1_lock = _sha(self.forecast1)
        self._event("forecast1_locked", forecast_hash=self.forecast1_lock)
        return self.forecast1_lock

    def lock_diagnosis(self, diagnosis: dict[str, Any]) -> str:
        if self.perform_count != 1:
            raise RuntimeError("exactly one broker action is required before diagnosis")
        if self.diagnosis is not None:
            raise RuntimeError("diagnosis already locked")
        if diagnosis.get("observed_action") != self.perform_response:
            raise ValueError("diagnosis observed_action does not match broker transcript")
        if diagnosis.get("claimed_condition") not in {"available", "degraded"}:
            raise ValueError("claimed_condition must be available or degraded")
        self.diagnosis = copy.deepcopy(diagnosis)
        self.diagnosis_lock = _sha(self.diagnosis)
        self._event("diagnosis_locked", diagnosis_hash=self.diagnosis_lock)
        return self.diagnosis_lock

    def stop_broker(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            if self._thread is not None:
                self._thread.join(timeout=2)
            self._server = None
            self._thread = None
            self._event("broker_stopped")

    def reveal(self) -> dict[str, Any]:
        if self.diagnosis is None:
            raise RuntimeError("lock diagnosis before reveal")
        self.stop_broker()
        assert self.forecast0 and self.forecast1 and self.entropy
        assert self.condition and self.legibility and self.payload and self.commitment
        reveal = {
            "protocol_version": PROTOCOL_VERSION,
            "trial_id": self.trial_id,
            "forecast_lock": self.forecast0_lock,
            "forecast1_lock": self.forecast1_lock,
            "diagnosis_lock": self.diagnosis_lock,
            "entropy": self.entropy,
            "condition": self.condition,
            "legibility": self.legibility,
            "payload_hash": hashlib.sha256(self.payload.encode()).hexdigest(),
            "commitment": self.commitment,
            "forecast0": self.forecast0,
            "forecast1": self.forecast1,
            "probe_response": self.probe_response,
            "perform_response": self.perform_response,
            "diagnosis": self.diagnosis,
            "events": self.events,
        }
        self._event("condition_revealed", condition=self.condition, legibility=self.legibility)
        reveal["events"] = self.events
        reveal["diagnosis_correct"] = self.diagnosis["claimed_condition"] == self.condition
        return reveal


def verify_runtime_reveal(reveal: dict[str, Any]) -> dict[str, bool]:
    condition, legibility = derive_state(reveal["trial_id"], reveal["entropy"])
    expected_commitment = _sha({
        "protocol_version": PROTOCOL_VERSION,
        "trial_id": reveal["trial_id"],
        "forecast_lock": reveal["forecast_lock"],
        "entropy": reveal["entropy"],
        "condition": reveal["condition"],
        "legibility": reveal["legibility"],
        "payload_hash": reveal["payload_hash"],
    })
    probe_expected = condition if legibility == "transparent" else "unknown"
    if condition == "available":
        perform_consistent = (
            hashlib.sha256(str(reveal.get("perform_response")).encode()).hexdigest()
            == reveal.get("payload_hash")
        )
    else:
        perform_consistent = reveal.get("perform_response") == "CAPABILITY_UNAVAILABLE"

    events = reveal.get("events", [])
    names = [event.get("event") for event in events]
    expected_order = [
        "forecast0_locked", "hidden_state_committed", "broker_started",
        "probe_observed", "forecast1_locked", "action_observed",
        "diagnosis_locked", "broker_stopped", "condition_revealed",
    ]
    event_lock_values_match = False
    if len(events) == 9:
        event_lock_values_match = (
            events[0].get("forecast_hash") == reveal.get("forecast_lock")
            and events[1].get("commitment") == reveal.get("commitment")
            and events[4].get("forecast_hash") == reveal.get("forecast1_lock")
            and events[6].get("diagnosis_hash") == reveal.get("diagnosis_lock")
        )

    checks = {
        "protocol_version_matches": reveal.get("protocol_version") == PROTOCOL_VERSION,
        "forecast_lock_matches": reveal.get("forecast_lock") == _sha(reveal.get("forecast0")),
        "forecast1_lock_matches": reveal.get("forecast1_lock") == _sha(reveal.get("forecast1")),
        "diagnosis_lock_matches": reveal.get("diagnosis_lock") == _sha(reveal.get("diagnosis")),
        "condition_derivation_matches": reveal.get("condition") == condition,
        "legibility_derivation_matches": reveal.get("legibility") == legibility,
        "commitment_matches": secrets.compare_digest(expected_commitment, reveal.get("commitment", "")),
        "probe_consistent": reveal.get("probe_response") == probe_expected,
        "forecast_probe_matches": (reveal.get("forecast1") or {}).get("observed_probe") == reveal.get("probe_response"),
        "perform_consistent": perform_consistent,
        "diagnosis_action_matches": (reveal.get("diagnosis") or {}).get("observed_action") == reveal.get("perform_response"),
        "event_order_valid": names == expected_order,
        "event_lock_values_match": event_lock_values_match,
    }
    checks["valid"] = all(checks.values())
    return checks
