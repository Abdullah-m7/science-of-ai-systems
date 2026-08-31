"""Interactive controller for Stage 002 instrument-validation trials."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .stage002 import FAMILIES, TrialController, save_json


def _read_json(label: str) -> dict:
    print(label, flush=True)
    raw = input().strip()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def run_trial(trial_id: str, family: str, output: Path) -> dict:
    trial = TrialController(trial_id, family)
    print(json.dumps({
        "trial_id": trial_id,
        "family": family,
        "task": FAMILIES[family],
        "note": "Capability is advertised; effective runtime state is not disclosed.",
    }), flush=True)
    forecast0 = _read_json("FORECAST0_JSON")
    f0_hash = trial.lock_forecast0(forecast0)
    print(json.dumps({"forecast0_locked": f0_hash}), flush=True)

    commitment = trial.apply_hidden_perturbation()
    print(json.dumps({
        "perturbation_applied": True,
        "commitment": commitment,
        "condition_disclosed": False,
    }), flush=True)

    forecast1 = _read_json("FORECAST1_JSON")
    f1_hash = trial.lock_forecast1(forecast1)
    print(json.dumps({"forecast1_locked": f1_hash}), flush=True)

    action = _read_json("ACTION_JSON")
    outcome = trial.execute(attempt=bool(action.get("attempt", True)))
    print(json.dumps({"outcome": outcome}), flush=True)

    diagnosis = _read_json("DIAGNOSIS_JSON")
    trial.lock_diagnosis(diagnosis)
    reveal = trial.reveal()
    save_json(output, reveal)
    print(json.dumps({
        "reveal": reveal,
        "saved_to": str(output),
    }), flush=True)
    return reveal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trial_id")
    parser.add_argument("family", choices=sorted(FAMILIES))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run_trial(args.trial_id, args.family, args.output)


if __name__ == "__main__":
    main()
