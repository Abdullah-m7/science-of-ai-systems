from sais.stage002 import TrialController, derive_condition, verify_commitment


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
    reveal = t.reveal(outcome)
    assert reveal["commitment_verified"] is True
    assert verify_commitment(reveal) is True


def test_tamper_breaks_commitment():
    t = TrialController("T-003", "retrieval")
    t.lock_forecast0(forecast(0.4))
    t.apply_hidden_perturbation()
    t.lock_forecast1(forecast(0.6))
    outcome = t.execute()
    t.lock_diagnosis({"claimed_condition": "degraded"})
    reveal = t.reveal(outcome)
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
