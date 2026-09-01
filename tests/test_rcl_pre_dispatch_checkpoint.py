from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from sais.rcl_pc_analysis import load_study_spec

ROOT = Path(__file__).parents[1]
BASE = ROOT / "experiments/008d-pre-dispatch-checkpoint"
CHECKPOINT = BASE / "PC-RCL-001_CHECKPOINT.json"
LEDGER_GENESIS = BASE / "DISPATCH_LEDGER_GENESIS.json"
MANIFEST = ROOT / "experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json"
PLAN = ROOT / "experiments/008c-dispatch-guard/DISPATCH_PLAN.json"
REGISTRY = ROOT / "experiments/007-rcl-pc-execution-readiness/TRIAL_REGISTRY.json"
HANDOFFS = ROOT / "experiments/008b-subject-isolation/HANDOFF_MANIFEST.json"
SURFACES = ROOT / "experiments/007-rcl-pc-execution-readiness/SURFACE_AUDIT.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pc_rcl_001_checkpoint_is_pre_behavioral_and_frozen() -> None:
    spec = load_study_spec(MANIFEST, root=ROOT)
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    handoffs = json.loads(HANDOFFS.read_text(encoding="utf-8"))
    surfaces = json.loads(SURFACES.read_text(encoding="utf-8"))
    genesis = json.loads(LEDGER_GENESIS.read_text(encoding="utf-8"))

    assert checkpoint["checkpoint_version"] == "SMI-CP/RCL-PC/PRE-DISPATCH/1"
    assert checkpoint["trial_id"] == "PC-RCL-001"
    assert checkpoint["status"] == "WAITING_FOR_FRESH_SUBJECT_AND_OPERATOR_CONFIRMATION"
    assert checkpoint["included_trial_started"] is False
    assert checkpoint["apply_authorized"] is False
    assert checkpoint["operator_confirmation"] == "PENDING"
    assert checkpoint["current_design_conversation_eligible"] is False
    assert checkpoint["subject_context_requirement"] == "NEW_REGULAR_CHAT_ONLY"

    assert checkpoint["freeze_tag"] == spec.freeze_tag == plan["freeze_tag"]
    assert checkpoint["freeze_commit"] == plan["freeze_commit"]
    assert checkpoint["controller_commit"] == plan["controller_commit"]
    assert checkpoint["configuration_commit"] == spec.config_commit
    assert checkpoint["configuration_binding_hash"] == spec.expected_binding_hash
    assert checkpoint["registry_sha256"] == _sha(REGISTRY)
    assert checkpoint["dispatch_plan_sha256"] == _sha(PLAN)
    assert checkpoint["handoff_manifest_sha256"] == _sha(HANDOFFS)

    handoff = next(row for row in handoffs["handoffs"] if row["trial_id"] == "PC-RCL-001")
    handoff_path = ROOT / handoff["path"]
    assert checkpoint["subject_handoff"] == {
        "path": handoff["path"],
        "sha256": _sha(handoff_path),
    }

    surface = next(row for row in surfaces["surfaces"] if row["trial_id"] == "PC-RCL-001")
    assert checkpoint["issue"]["number"] == surface["issue_number"] == 18
    assert checkpoint["issue"]["url"] == surface["url"]
    assert checkpoint["issue"]["body_sha256"] == surface["body_sha256"]
    assert checkpoint["issue"]["frozen_body_sha256"] == surface["body_sha256"]
    assert checkpoint["issue"]["comment_count"] == 0
    assert checkpoint["matching_controller_run_ids"] == []

    assert checkpoint["dispatch_ledger"]["manifest_sha256"] == _sha(LEDGER_GENESIS)
    assert checkpoint["dispatch_ledger"]["manifest_plan_sha256"] == _sha(PLAN)
    assert checkpoint["dispatch_ledger"]["reservation_record_count"] == 0
    assert checkpoint["dispatch_ledger"]["manifest_snapshot_path"] == str(
        LEDGER_GENESIS.relative_to(ROOT)
    )
    assert genesis["plan_sha256"] == _sha(PLAN)
    assert genesis["freeze_tag"] == spec.freeze_tag
    assert genesis["controller_commit"] == spec.controller_code_sha

    result = subprocess.run(
        [
            "git", "merge-base", "--is-ancestor",
            checkpoint["main_commit_at_checkpoint"], "HEAD",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
