from __future__ import annotations

import pytest

from sais.mosaic import simulate_p0
from sais.mosaic_analysis import (
    evaluate_trial,
    reliability_dominance,
    summarize,
    synthetic_subject_record,
)


def _records(policy: str):
    return [synthetic_subject_record(row, policy=policy) for row in simulate_p0()]


def test_bayesian_subject_is_zero_error_and_invariant() -> None:
    report = summarize(_records("bayes"))
    assert report["n_trials"] == 64
    assert report["n_cores"] == 16
    assert report["mean_final_integration_error"] == pytest.approx(0.0)
    assert report["mean_order_swap_effect"] == pytest.approx(0.0)
    assert report["mean_label_swap_effect"] == pytest.approx(0.0)
    assert report["reliability_dominance_rate"] == pytest.approx(1.0)


def test_recency_policy_is_detected_as_order_distortion() -> None:
    report = summarize(_records("recency"))
    assert report["mean_order_swap_effect"] > 0.20
    assert report["mean_label_swap_effect"] == pytest.approx(0.0)
    assert report["mean_final_integration_error"] > 0.02


def test_named_label_bias_is_isolated_from_neutral_labels() -> None:
    report = summarize(_records("named_label_bias"))
    assert report["mean_named_label_swap_effect"] > 0.10
    assert report["mean_neutral_label_swap_effect"] == pytest.approx(0.0)
    assert report["mean_order_swap_effect"] == pytest.approx(0.0)


def test_unequal_conflict_dominance_uses_stronger_numeric_reliability() -> None:
    records = _records("bayes")
    judged = [reliability_dominance(row) for row in records]
    judged = [value for value in judged if value is not None]
    assert judged
    assert all(judged)


def test_evidence_weight_ratio_is_one_for_bayesian_policy() -> None:
    record = synthetic_subject_record(simulate_p0()[0], policy="bayes")
    evaluated = evaluate_trial(record)
    for value in evaluated["evidence_weight_ratios"]:
        assert value == pytest.approx(1.0)


def test_invalid_probability_is_rejected() -> None:
    record = synthetic_subject_record(simulate_p0()[0], policy="bayes")
    record["p2"] = 1.2
    with pytest.raises(ValueError, match="p2"):
        evaluate_trial(record)
