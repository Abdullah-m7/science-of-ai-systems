from __future__ import annotations

from collections import Counter, defaultdict
import math

import pytest

from sais.mosaic import (
    PRIOR,
    VARIANTS,
    Cue,
    bayes_update,
    make_core_specs,
    make_design_matrix,
    posterior_path,
    p0_coverage_report,
    simulate_p0,
    validate_quartet,
    validate_reliability,
)


def test_single_cue_posterior_equals_reliability_from_symmetric_prior() -> None:
    assert bayes_update(0.5, "available", 0.8) == pytest.approx(0.8)
    assert bayes_update(0.5, "degraded", 0.8) == pytest.approx(0.2)


def test_conflicting_unequal_cues_favor_stronger_evidence() -> None:
    cues = [
        Cue("X", "available", 0.80, "source_x"),
        Cue("Y", "degraded", 0.65, "source_y"),
    ]
    path = posterior_path(PRIOR, cues)
    assert 0.5 < path[-1] < 0.8


def test_equal_reliability_opposite_cues_cancel() -> None:
    cues = [
        Cue("X", "available", 0.72, "source_x"),
        Cue("Y", "degraded", 0.72, "source_y"),
    ]
    assert posterior_path(PRIOR, cues)[-1] == pytest.approx(0.5)


def test_bayes_final_posterior_is_order_invariant() -> None:
    x = Cue("X", "available", 0.80, "runtime_diagnostic")
    y = Cue("Y", "degraded", 0.65, "interface_declaration")
    assert posterior_path(PRIOR, [x, y])[-1] == pytest.approx(
        posterior_path(PRIOR, [y, x])[-1]
    )


def test_reliability_domain_is_closed() -> None:
    for value in (0.0, 0.5, 1.0):
        with pytest.raises(ValueError):
            validate_reliability(value)


def test_design_matrix_is_exactly_16_quartets_and_64_trials() -> None:
    rows = make_design_matrix()
    assert len(rows) == 64
    assert len({row["trial_id"] for row in rows}) == 64
    counts = Counter(row["core_id"] for row in rows)
    assert set(counts.values()) == {4}
    assert Counter(row["frame"] for row in rows) == {"named": 32, "neutral": 32}
    assert Counter(row["reliability_profile"] for row in rows) == {
        "unequal": 32,
        "equal": 32,
    }


def test_design_shell_contains_no_hidden_assignment() -> None:
    for row in make_design_matrix():
        assert row["hidden_state"] is None
        assert row["cue_x_claim"] is None
        assert row["cue_y_claim"] is None


def test_p0_simulation_is_deterministic_and_quartet_valid() -> None:
    first = simulate_p0()
    second = simulate_p0()
    assert first == second
    by_core = defaultdict(list)
    for row in first:
        by_core[row["core_id"]].append(row)
    assert len(by_core) == 16
    assert all(validate_quartet(rows)["valid"] for rows in by_core.values())


def test_p0_final_bayes_posterior_is_label_and_order_invariant() -> None:
    by_core = defaultdict(list)
    for row in simulate_p0():
        by_core[row["core_id"]].append(row)
    for rows in by_core.values():
        assert {row["variant"] for row in rows} == set(VARIANTS)
        posteriors = {round(row["ideal_p2"], 12) for row in rows}
        assert len(posteriors) == 1


def test_p0_coverage_exercises_agree_and_conflict_in_every_cell() -> None:
    report = p0_coverage_report()
    assert report["valid"] is True
    assert report["truth_counts"] == {"available": 8, "degraded": 8}
    assert all(
        value == {"agree": 2, "conflict": 2}
        for value in report["frame_profile_paths"].values()
    )
