from __future__ import annotations

import copy

import pytest

from sais.rcl_sequential_analysis import (
    SEQUENTIAL_VERSION,
    analyze_final_report,
    lag1_correlation,
    linear_slope,
)


def _report(status: str = "PASS") -> dict:
    records = []
    cells = [
        ("available", "transparent"),
        ("degraded", "transparent"),
        ("available", "opaque"),
        ("degraded", "opaque"),
    ]
    for index in range(1, 33):
        condition, legibility = cells[(index - 1) % 4]
        outcome = 1 if condition == "available" else 0
        p0 = 0.5
        if legibility == "transparent":
            p1 = 0.95 if outcome else 0.05
        else:
            p1 = 0.5
        brier0 = (p0 - outcome) ** 2
        brier1 = (p1 - outcome) ** 2
        records.append({
            "trial_id": f"PC-RCL-{index:03d}",
            "condition": condition,
            "legibility": legibility,
            "p0": p0,
            "p1": p1,
            "outcome": outcome,
            "gain": brier0 - brier1,
            "abs_update": abs(p1 - p0),
        })
    return {"status": status, "integrity": {"pass": True}, "valid_trials": records}


def test_sequential_report_is_secondary_and_complete() -> None:
    result = analyze_final_report(_report())
    assert result["sequential_version"] == SEQUENTIAL_VERSION
    assert result["primary_analysis_status_unchanged"] == "PASS"
    assert result["qualification_modified"] is False
    assert result["n"] == 32
    assert result["first_half"]["n"] == 16
    assert result["second_half"]["n"] == 16
    assert result["retrospective_prefixes"]["32"]["primary_effect"] > 0.2
    assert result["slopes_per_trial"]["p0"] == 0.0


def test_fail_primary_status_remains_fail() -> None:
    result = analyze_final_report(_report("FAIL"))
    assert result["primary_analysis_status_unchanged"] == "FAIL"
    assert result["qualification_modified"] is False


def test_nonterminal_or_integrity_failure_is_rejected() -> None:
    with pytest.raises(ValueError, match="terminal complete"):
        analyze_final_report(_report("INCOMPLETE"))
    forged = _report()
    forged["integrity"]["pass"] = False
    with pytest.raises(ValueError, match="integrity PASS"):
        analyze_final_report(forged)


def test_wrong_fixed_denominator_is_rejected() -> None:
    forged = copy.deepcopy(_report())
    forged["valid_trials"][-1]["trial_id"] = "PC-RCL-999"
    with pytest.raises(ValueError, match="fixed denominator"):
        analyze_final_report(forged)


def test_temporal_helpers_are_deterministic() -> None:
    assert linear_slope([1.0, 2.0, 3.0]) == 1.0
    assert lag1_correlation([1.0, 2.0, 3.0, 4.0]) == pytest.approx(1.0)
    assert lag1_correlation([1.0, 1.0, 1.0]) is None
