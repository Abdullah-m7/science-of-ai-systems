"""Command-line interface for MOSAIC design-only tooling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mosaic import (
    P0_SIMULATION_SEED,
    canonical_hash,
    make_design_matrix,
    p0_coverage_report,
    simulate_p0,
)
from .mosaic_analysis import summarize, synthetic_subject_record


def _write_or_print(value: object, output: Path | None) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output is None:
        print(rendered, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def design_payload() -> dict:
    rows = make_design_matrix()
    return {
        "protocol_version": "SAIS/MOSAIC/P1-DESIGN/1",
        "status": "DESIGN_ONLY",
        "trial_count": len(rows),
        "design_hash": canonical_hash(rows),
        "rows": rows,
    }


def simulation_payload() -> dict:
    design = make_design_matrix()
    rows = simulate_p0()
    return {
        "protocol_version": "SAIS/MOSAIC/P0/1",
        "classification": "EXCLUDED_DESIGN_VALIDATION",
        "seed": P0_SIMULATION_SEED,
        "row_count": len(rows),
        "design_hash": canonical_hash(design),
        "coverage": p0_coverage_report(rows),
        "rows": rows,
    }


def diagnostic_payload(policy: str) -> dict:
    simulated = simulate_p0()
    records = [synthetic_subject_record(row, policy=policy) for row in simulated]
    return {
        "classification": "SYNTHETIC_METRIC_DIAGNOSTIC",
        "policy": policy,
        "summary": summarize(records),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="MOSAIC design-only utilities")
    sub = parser.add_subparsers(dest="command", required=True)
    design = sub.add_parser("design")
    design.add_argument("--output", type=Path)
    simulate = sub.add_parser("simulate")
    simulate.add_argument("--output", type=Path)
    diagnose = sub.add_parser("diagnose")
    diagnose.add_argument("policy", choices=("bayes", "recency", "named_label_bias"))
    diagnose.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "design":
        _write_or_print(design_payload(), args.output)
    elif args.command == "simulate":
        _write_or_print(simulation_payload(), args.output)
    else:
        _write_or_print(diagnostic_payload(args.policy), args.output)


if __name__ == "__main__":
    main()
