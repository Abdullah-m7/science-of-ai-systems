from sais.stage002 import TrialController, derive_condition, verify_commitment, verify_reveal


def forecast(p: float) -> dict:
    return {"p_success": p, "required_components": ["broker"]}


def test_condition_is_deterministic():
    entropy = "00" * 32
    assert derive_condition("T-001", entropy) == derive_condition("T-001", entropy)


def test_commit_reveal_roundtrip():
    t = TrialController("T-002", "resource_read")
    t.lock_forecast0(forecast(0.5))
    commitment = t.apply_hidden_perturbation()
    assert len(commitment) == 64
    t.lock_forecast1(forecast(0.5))
    outcome = t.execute()
    t.lock_diagnosis({"claimed_condition": "available"})
    reveal = t.reveal()
    assert reveal["commitment_verified"] is True
    assert verify_commitment(reveal) is True


def test_tamper_breaks_commitment():
    t = TrialController("T-003", "retrieval")
    t.lock_forecast0(forecast(0.4))
    t.apply_hidden_perturbation()
    t.lock_forecast1(forecast(0.6))
    outcome = t.execute()
    t.lock_diagnosis({"claimed_condition": "degraded"})
    reveal = t.reveal()
    reveal["condition"] = "degraded" if reveal["condition"] == "available" else "available"
    assert verify_commitment(reveal) is False


def test_forecast_must_precede_perturbation():
    t = TrialController("T-004", "computation")
    try:
        t.apply_hidden_perturbation()
    except RuntimeError as exc:
        assert "forecast0" in str(exc)
    else:
        raise AssertionError("perturbation applied before forecast lock")


def test_full_reveal_verifier():
    t = TrialController("T-005", "memory")
    t.lock_forecast0(forecast(0.5))
    t.apply_hidden_perturbation()
    t.lock_forecast1(forecast(0.5))
    t.execute()
    t.lock_diagnosis({"claimed_condition": t.condition})
    reveal = t.reveal()
    checks = verify_reveal(reveal)
    assert checks["valid"] is True


def test_action_cannot_execute_twice():
    t = TrialController("T-006", "connector")
    t.lock_forecast0(forecast(0.5))
    t.apply_hidden_perturbation()
    t.lock_forecast1(forecast(0.5))
    t.execute()
    try:
        t.execute()
    except RuntimeError as exc:
        assert "already executed" in str(exc)
    else:
        raise AssertionError("second action execution was accepted")


def test_protocol_version_tamper_is_detected():
    t = TrialController("T-007", "resource_read")
    t.lock_forecast0(forecast(0.5))
    t.apply_hidden_perturbation()
    t.lock_forecast1(forecast(0.5))
    t.execute()
    t.lock_diagnosis({"claimed_condition": t.condition})
    reveal = t.reveal()
    reveal["protocol_version"] = "SMI-CP/002A/0"
    assert verify_reveal(reveal)["valid"] is False


def test_event_order_tamper_is_detected():
    t = TrialController("T-008", "retrieval")
    t.lock_forecast0(forecast(0.5))
    t.apply_hidden_perturbation()
    t.lock_forecast1(forecast(0.5))
    t.execute()
    t.lock_diagnosis({"claimed_condition": t.condition})
    reveal = t.reveal()
    reveal["events"][1], reveal["events"][2] = reveal["events"][2], reveal["events"][1]
    assert verify_reveal(reveal)["event_order_valid"] is False
