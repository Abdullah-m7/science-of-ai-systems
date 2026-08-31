from sais.score import (
    brier_score,
    diagnosis_accuracy,
    self_model_gap,
    signed_calibration_gap,
    summarize,
)


def rec(p, success, actual=None, claimed=None):
    return {
        "forecast": {"p_success": p},
        "outcome": {
            "success": success,
            "actual_limiting_component": actual,
        },
        "diagnosis": {"claimed_cause": claimed} if claimed else None,
    }


def test_perfect_forecasts_score_zero():
    rows = [rec(1.0, True), rec(0.0, False)]
    assert brier_score(rows) == 0.0
    assert self_model_gap(rows) == 0.0


def test_overconfidence_is_positive():
    rows = [rec(0.9, False), rec(0.8, True)]
    assert signed_calibration_gap(rows) > 0

def test_diagnosis_accuracy_uses_judged_rows_only():
    rows = [
        rec(0.2, False, "web", "web"),
        rec(0.2, False, "memory", "context"),
        rec(0.7, True),
    ]
    assert diagnosis_accuracy(rows) == 0.5


def test_summary_contract():
    rows = [rec(0.75, True), rec(0.25, False)]
    result = summarize(rows)
    assert result["n"] == 2
    assert set(result) == {
        "n",
        "brier_score",
        "self_model_gap",
        "mean_confidence",
        "empirical_success",
        "signed_calibration_gap",
        "diagnosis_accuracy",
    }
