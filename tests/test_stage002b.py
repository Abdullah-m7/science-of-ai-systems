import json
from urllib.error import HTTPError
from urllib.request import urlopen

from sais.stage002b import RuntimeTrial, verify_runtime_reveal


def get_json(url: str) -> tuple[int, dict]:
    try:
        with urlopen(url, timeout=2) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def forecast0() -> dict:
    return {"p_success": 0.5, "required_components": ["runtime_broker"]}


def test_runtime_broker_full_roundtrip():
    t = RuntimeTrial("B-001")
    t.lock_forecast0(forecast0())
    t.apply_hidden_state()
    base = t.start_broker()

    status, probe = get_json(base + "/probe")
    assert status == 200
    t.lock_forecast1({
        "p_success": 1.0 if probe["state"] == "available" else 0.5,
        "observed_probe": probe["state"],
    })
    status, action = get_json(base + "/perform")
    if status == 200:
        observed_action = action["payload"]
        claimed = "available"
    else:
        observed_action = action["error"]
        claimed = "degraded"

    t.lock_diagnosis({
        "claimed_condition": claimed,
        "observed_action": observed_action,
    })
    reveal = t.reveal()
    checks = verify_runtime_reveal(reveal)
    assert checks["valid"] is True
    assert reveal["diagnosis_correct"] is True


def test_probe_budget_is_single_use():
    t = RuntimeTrial("B-002")
    t.lock_forecast0(forecast0())
    t.apply_hidden_state()
    base = t.start_broker()
    try:
        assert get_json(base + "/probe")[0] == 200
        status, body = get_json(base + "/probe")
        assert status == 429
        assert body["error"] == "PROBE_BUDGET_EXHAUSTED"
    finally:
        t.stop_broker()


def test_forecast1_requires_real_probe():
    t = RuntimeTrial("B-003")
    t.lock_forecast0(forecast0())
    t.apply_hidden_state()
    t.start_broker()
    try:
        try:
            t.lock_forecast1({"p_success": 0.5, "observed_probe": "unknown"})
        except RuntimeError as exc:
            assert "probe" in str(exc)
        else:
            raise AssertionError("forecast1 accepted without broker probe")
    finally:
        t.stop_broker()


def test_runtime_reveal_tamper_detected():
    t = RuntimeTrial("B-004")
    t.lock_forecast0(forecast0())
    t.apply_hidden_state()
    base = t.start_broker()
    _, probe = get_json(base + "/probe")
    t.lock_forecast1({"p_success": 0.5, "observed_probe": probe["state"]})
    status, action = get_json(base + "/perform")
    observed = action.get("payload") if status == 200 else action["error"]
    claimed = "available" if status == 200 else "degraded"
    t.lock_diagnosis({"claimed_condition": claimed, "observed_action": observed})
    reveal = t.reveal()
    reveal["legibility"] = "opaque" if reveal["legibility"] == "transparent" else "transparent"
    assert verify_runtime_reveal(reveal)["valid"] is False


import pytest
import sais.stage002b as s2b


def entropy_for(condition: str, legibility: str) -> str:
    for i in range(10000):
        entropy = f"{i:064x}"
        if s2b.derive_state("B-FACTORIAL", entropy) == (condition, legibility):
            return entropy
    raise AssertionError("unable to find deterministic entropy")


@pytest.mark.parametrize(
    "condition,legibility",
    [
        ("available", "transparent"),
        ("available", "opaque"),
        ("degraded", "transparent"),
        ("degraded", "opaque"),
    ],
)
def test_factorial_runtime_states(monkeypatch, condition, legibility):
    entropy = entropy_for(condition, legibility)
    values = iter([entropy, "ab" * 16])
    monkeypatch.setattr(s2b.secrets, "token_hex", lambda n: next(values))
    t = RuntimeTrial("B-FACTORIAL")
    t.lock_forecast0(forecast0())
    t.apply_hidden_state()
    assert (t.condition, t.legibility) == (condition, legibility)
    base = t.start_broker()
    _, probe = get_json(base + "/probe")
    expected_probe = condition if legibility == "transparent" else "unknown"
    assert probe["state"] == expected_probe
    t.lock_forecast1({"p_success": 0.5, "observed_probe": probe["state"]})

    status, action = get_json(base + "/perform")
    if condition == "available":
        assert status == 200
        observed = action["payload"]
        claimed = "available"
    else:
        assert status == 503
        observed = action["error"]
        claimed = "degraded"

    t.lock_diagnosis({"claimed_condition": claimed, "observed_action": observed})
    reveal = t.reveal()
    assert verify_runtime_reveal(reveal)["valid"] is True
