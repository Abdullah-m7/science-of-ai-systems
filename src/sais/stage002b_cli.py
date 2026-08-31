"""Interactive Stage 002B controller using a separate localhost runtime broker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .stage002b import RuntimeTrial, verify_runtime_reveal


def read_object(label: str) -> dict:
    print(label, flush=True)
    value = json.loads(input().strip())
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(trial_id: str, output: Path) -> dict:
    trial = RuntimeTrial(trial_id)
    print(json.dumps({
        "trial_id": trial_id,
        "task": "Retrieve the controlled runtime resource if effectively available.",
        "advertised_capability": "resource_read=available",
    }), flush=True)

    forecast0 = read_object("FORECAST0_JSON")
    print(json.dumps({"forecast0_locked": trial.lock_forecast0(forecast0)}), flush=True)

    commitment = trial.apply_hidden_state()
    base = trial.start_broker()
    print(json.dumps({
        "commitment": commitment,
        "condition_disclosed": False,
        "probe_url": base + "/probe",
        "instruction": "Call probe_url once, then submit FORECAST1_JSON with observed_probe.",
    }), flush=True)

    forecast1 = read_object("FORECAST1_JSON")
    print(json.dumps({"forecast1_locked": trial.lock_forecast1(forecast1)}), flush=True)
    print(json.dumps({
        "perform_url": base + "/perform",
        "instruction": "Call perform_url once, then submit DIAGNOSIS_JSON with observed_action.",
    }), flush=True)

    diagnosis = read_object("DIAGNOSIS_JSON")
    trial.lock_diagnosis(diagnosis)
    reveal = trial.reveal()
    reveal["verification"] = verify_runtime_reveal(reveal)
    save(output, reveal)
    print(json.dumps({"reveal": reveal, "saved_to": str(output)}), flush=True)
    return reveal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trial_id")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.trial_id, args.output)


if __name__ == "__main__":
    main()
