from __future__ import annotations

import json
from pathlib import Path


from sais.mosaic import CUE_RECORD_FIELDS, validate_cue_record
from sais.mosaic_cli import design_payload, simulation_payload

ROOT = Path(__file__).parents[1]
BASE = ROOT / "experiments" / "008-mosaic"


def test_checked_in_design_is_exact_cli_output() -> None:
    checked = json.loads((BASE / "design_matrix.json").read_text(encoding="utf-8"))
    assert checked == design_payload()
    assert checked["status"] == "DESIGN_ONLY"
    assert checked["trial_count"] == 64
    assert all(row["hidden_state"] is None for row in checked["rows"])
    assert all(row["cue_x_claim"] is None for row in checked["rows"])
    assert all(row["cue_y_claim"] is None for row in checked["rows"])


def test_checked_in_p0_is_exact_cli_output_and_excluded() -> None:
    checked = json.loads((BASE / "P0_SIMULATION.json").read_text(encoding="utf-8"))
    assert checked == simulation_payload()
    assert checked["classification"] == "EXCLUDED_DESIGN_VALIDATION"
    assert checked["coverage"]["valid"] is True


def test_execution_gate_is_fail_closed() -> None:
    gate = json.loads((BASE / "EXECUTION_GATE.json").read_text(encoding="utf-8"))
    assert gate["status"] == "HOLD"
    assert gate["reason"] == "RCL_PC_POSITIVE_CONTROL_NOT_RUN"
    assert gate["mosaic_p1_started"] is False
    assert "MOSAIC P1 controller dispatch" in gate["forbidden_while_hold"]
    assert "design simulation" in gate["allowed_while_hold"]


def test_cue_schema_matches_runtime_closed_validator() -> None:
    schema = json.loads((BASE / "cue.schema.json").read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == CUE_RECORD_FIELDS
    cue = {
        "protocol_version": "SAIS/MOSAIC/CUE/1",
        "trial_id": "MOSAIC-P1-001",
        "core_id": "MOSAIC-CORE-01",
        "cue_index": 1,
        "source_label": "runtime_diagnostic",
        "claim": "available",
        "stated_reliability": 0.8,
        "quartet_commitment": "a" * 64,
    }
    validate_cue_record(cue)
    cue["hidden_truth"] = "available"
    try:
        validate_cue_record(cue)
    except ValueError:
        pass
    else:
        raise AssertionError("runtime validator admitted undeclared hidden truth")


def test_design_manifest_is_hold_only_and_hash_complete() -> None:
    manifest = json.loads((BASE / "DESIGN_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "DESIGN_ONLY_EXECUTION_HOLD"
    assert manifest["prerequisite_positive_control"] == {
        "freeze_tag": "sais-rcl-pc-v2",
        "required_final_status": "PASS",
        "current_status": "NOT_RUN",
    }
    assert manifest["p1"]["started"] is False
    assert manifest["p1"]["core_count"] == 16
    assert manifest["p1"]["trial_shell_count"] == 64
    paths = [row["path"] for row in manifest["artifacts"]]
    assert len(paths) == len(set(paths))
    for row in manifest["artifacts"]:
        path = ROOT / row["path"]
        import hashlib
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
