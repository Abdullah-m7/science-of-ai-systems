"""Secondary temporal diagnostics for the memory-enabled RCL-PC v2 block.

These diagnostics are descriptive and never modify the frozen qualification
status produced by rcl_pc_analysis.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
from statistics import mean
from typing import Any, Iterable, Sequence

SEQUENTIAL_VERSION = "SMI-CP/RCL-PC/SEQUENTIAL/1"
TRIAL_RE = re.compile(r"^PC-RCL-([0-9]{3})$")
EXPECTED_IDS = tuple(f"PC-RCL-{index:03d}" for index in range(1, 33))


def trial_index(trial_id: str) -> int:
    match = TRIAL_RE.fullmatch(trial_id)
    if not match:
        raise ValueError(f"invalid included trial id: {trial_id}")
    return int(match.group(1))


def _values(records: Iterable[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in records]


def linear_slope(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    xs = list(range(1, len(values) + 1))
    xbar = mean(xs)
    ybar = mean(values)
    denominator = sum((x - xbar) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, values)) / denominator


def lag1_correlation(values: Sequence[float]) -> float | None:
    if len(values) < 3:
        return None
    left = list(values[:-1])
    right = list(values[1:])
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum(
        (a - left_mean) * (b - right_mean) for a, b in zip(left, right)
    )
    left_ss = sum((a - left_mean) ** 2 for a in left)
    right_ss = sum((b - right_mean) ** 2 for b in right)
    denominator = math.sqrt(left_ss * right_ss)
    return None if denominator == 0 else numerator / denominator


def primary_effect(records: Sequence[dict[str, Any]]) -> float | None:
    transparent = [
        float(row["gain"]) for row in records if row["legibility"] == "transparent"
    ]
    opaque = [
        float(row["gain"]) for row in records if row["legibility"] == "opaque"
    ]
    if not transparent or not opaque:
        return None
    return mean(transparent) - mean(opaque)


def block_summary(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(
        f"{row['condition']}|{row['legibility']}" for row in records
    )
    return {
        "n": len(records),
        "mean_p0": mean(_values(records, "p0")) if records else None,
        "mean_abs_update": mean(_values(records, "abs_update")) if records else None,
        "mean_gain": mean(_values(records, "gain")) if records else None,
        "primary_effect": primary_effect(records),
        "cell_counts": dict(sorted(counts.items())),
    }


def analyze_final_report(report: dict[str, Any]) -> dict[str, Any]:
    """Compute post-block temporal diagnostics without changing qualification."""
    if report.get("status") not in {"PASS", "FAIL"}:
        raise ValueError("sequential analysis requires a terminal complete PASS/FAIL report")
    integrity = report.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("pass") is not True:
        raise ValueError("sequential analysis requires primary integrity PASS")
    records = report.get("valid_trials")
    if not isinstance(records, list) or len(records) != 32:
        raise ValueError("sequential analysis requires exactly 32 valid trials")
    ordered = sorted(records, key=lambda row: trial_index(str(row["trial_id"])))
    ids = tuple(str(row["trial_id"]) for row in ordered)
    if ids != EXPECTED_IDS:
        raise ValueError("valid trial order does not match the fixed denominator")

    p0 = _values(ordered, "p0")
    abs_update = _values(ordered, "abs_update")
    gain = _values(ordered, "gain")
    first = ordered[:16]
    second = ordered[16:]
    prefixes = {}
    for size in (8, 16, 24, 32):
        subset = ordered[:size]
        prefixes[str(size)] = {
            "primary_effect": primary_effect(subset),
            "mean_p0": mean(_values(subset, "p0")),
            "mean_abs_update": mean(_values(subset, "abs_update")),
        }

    return {
        "sequential_version": SEQUENTIAL_VERSION,
        "primary_analysis_status_unchanged": report["status"],
        "n": 32,
        "trial_ids": list(ids),
        "slopes_per_trial": {
            "p0": linear_slope(p0),
            "abs_update": linear_slope(abs_update),
            "gain": linear_slope(gain),
        },
        "lag1_correlations": {
            "p0": lag1_correlation(p0),
            "abs_update": lag1_correlation(abs_update),
            "gain": lag1_correlation(gain),
        },
        "first_half": block_summary(first),
        "second_half": block_summary(second),
        "retrospective_prefixes": prefixes,
        "qualification_modified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute secondary temporal diagnostics after final RCL-PC analysis"
    )
    parser.add_argument("analysis_json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.analysis_json.read_text(encoding="utf-8"))
    result = analyze_final_report(report)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
