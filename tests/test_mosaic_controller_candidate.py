from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

from sais.mosaic_controller import run_quartet

ROOT = Path(__file__).parents[1]
STAGE = ROOT / "experiments" / "009-mosaic-quartet-controller"
GATE = ROOT / "experiments" / "008-mosaic" / "EXECUTION_GATE.json"


def test_stage009_status_is_local_only_and_p1_not_started() -> None:
    status = json.loads((STAGE / "STATUS.json").read_text(encoding="utf-8"))
    assert status["status"] == "LOCAL_CANDIDATE_PASS_PUBLIC_DISPATCH_DISABLED"
    assert status["mosaic_p1_started"] is False
    assert status["public_workflow_present"] is False
    assert status["public_evidence_collector"] == "PENDING"
    assert status["public_excluded_validation"] == "PENDING"
    assert status["frozen_controller_tag"] is None


def test_stage008_execution_gate_remains_hold() -> None:
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    assert gate["status"] == "HOLD"
    assert gate["mosaic_p1_started"] is False
    assert gate["reason"] == "RCL_PC_POSITIVE_CONTROL_NOT_RUN"


def test_no_public_mosaic_workflow_exists() -> None:
    workflows = ROOT / ".github" / "workflows"
    mosaic = [path for path in workflows.glob("*") if "mosaic" in path.name.lower()]
    assert mosaic == []


def test_source_order_guards_baseline_randomization_and_reveal() -> None:
    source = inspect.getsource(run_quartet)
    baseline = source.index("baseline_seal_reference = baseline_seal_callback")
    p0_public_seal = source.index("P0_SEAL_PREFIX + _compact")
    keygen = source.index("key = secrets.token_bytes(32)")
    ledger_seal = source.index("ledger_seal_reference = seal_callback")
    envelope_seal = source.index(
        "seal_envelope_reference = seal_envelope_callback"
    )
    public_seal = source.index("\n    seal_comments: dict[str, dict[str, Any]] = {}")
    verify = source.index("verification = verify_sealed_quartet")
    reveal = source.index("REVEAL_PREFIX + _compact")
    assert baseline < p0_public_seal < keygen
    assert ledger_seal < envelope_seal < public_seal < verify < reveal


def test_candidate_manifest_hashes_all_stage009_artifacts() -> None:
    manifest = json.loads((STAGE / "CANDIDATE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "LOCAL_CANDIDATE_EXECUTION_HOLD"
    assert manifest["public_dispatch_enabled"] is False
    paths = [row["path"] for row in manifest["artifacts"]]
    assert len(paths) == len(set(paths))
    for row in manifest["artifacts"]:
        path = ROOT / row["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]


def test_candidate_manifest_freezes_design_dependencies() -> None:
    from sais.mosaic import canonical_hash, make_design_matrix

    manifest = json.loads((STAGE / "CANDIDATE_MANIFEST.json").read_text(encoding="utf-8"))
    binding = manifest["design_binding"]
    expected_design_hash = canonical_hash(make_design_matrix())
    assert binding["canonical_design_hash"] == expected_design_hash

    expected_paths = {
        "src/sais/mosaic.py": "design_source_sha256",
        "experiments/008-mosaic/design_matrix.json": "design_matrix_sha256",
        "experiments/008-mosaic/DESIGN_MANIFEST.json": "design_manifest_sha256",
    }
    artifacts = {row["path"]: row["sha256"] for row in manifest["artifacts"]}
    for path, field in expected_paths.items():
        target = ROOT / path
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        assert binding[field] == actual
        assert artifacts[path] == actual
