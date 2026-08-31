"""Scoring utilities for SMI-CP trial records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def load_jsonl(path: str | Path) -> list[dict]:
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _observations(records: Iterable[dict]) -> list[tuple[float, int]]:
    out = []
    for record in records:
        p = float(record["forecast"]["p_success"])
        y = int(bool(record["outcome"]["success"]))
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"p_success outside [0,1]: {p}")
        out.append((p, y))
    if not out:
        raise ValueError("no trial records")
    return out


def brier_score(records: Iterable[dict]) -> float:
    obs = _observations(records)
    return sum((p - y) ** 2 for p, y in obs) / len(obs)


def self_model_gap(records: Iterable[dict]) -> float:
    obs = _observations(records)
    return sum(abs(p - y) for p, y in obs) / len(obs)

def mean_confidence(records: Iterable[dict]) -> float:
    obs = _observations(records)
    return sum(p for p, _ in obs) / len(obs)


def empirical_success(records: Iterable[dict]) -> float:
    obs = _observations(records)
    return sum(y for _, y in obs) / len(obs)


def signed_calibration_gap(records: Iterable[dict]) -> float:
    """Positive values indicate aggregate overconfidence."""
    obs = _observations(records)
    return sum(p - y for p, y in obs) / len(obs)


def diagnosis_accuracy(records: Iterable[dict]) -> float | None:
    judged = []
    for record in records:
        actual = record.get("outcome", {}).get("actual_limiting_component")
        claimed = (record.get("diagnosis") or {}).get("claimed_cause")
        if actual is not None and claimed is not None:
            judged.append(int(actual == claimed))
    return None if not judged else sum(judged) / len(judged)


def summarize(records: Iterable[dict]) -> dict:
    rows = list(records)
    return {
        "n": len(rows),
        "brier_score": brier_score(rows),
        "self_model_gap": self_model_gap(rows),
        "mean_confidence": mean_confidence(rows),
        "empirical_success": empirical_success(rows),
        "signed_calibration_gap": signed_calibration_gap(rows),
        "diagnosis_accuracy": diagnosis_accuracy(rows),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl")
    args = parser.parse_args()
    print(json.dumps(summarize(load_jsonl(args.jsonl)), indent=2))