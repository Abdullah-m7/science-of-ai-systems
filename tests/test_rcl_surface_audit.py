from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sais.rcl_pc_analysis import load_study_spec
from sais.rcl_registry import (
    issue_title,
    load_registry,
    render_issue_body,
    validate_registry,
)

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json"
REGISTRY = ROOT / "experiments/007-rcl-pc-execution-readiness/TRIAL_REGISTRY.json"
AUDIT = ROOT / "experiments/007-rcl-pc-execution-readiness/SURFACE_AUDIT.json"


def test_surface_audit_matches_registry_and_freeze() -> None:
    spec = load_study_spec(MANIFEST, root=ROOT)
    registry = load_registry(REGISTRY)
    validate_registry(registry, spec)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))

    assert audit["audit_version"] == "SMI-CP/RCL-PC/SURFACES/1"
    assert audit["repository"] == spec.repository
    assert audit["freeze_tag"] == spec.freeze_tag
    assert audit["freeze_commit"] == registry["freeze_commit"]
    assert audit["block_id"] == spec.block_id
    assert audit["included_trials_started"] == 0
    assert audit["surface_count"] == 32
    assert audit["trial_ids_exact"] is True
    assert audit["zero_comments"] is True

    registry_sha = hashlib.sha256(REGISTRY.read_bytes()).hexdigest()
    assert audit["registry_sha256"] == registry_sha

    surfaces = audit["surfaces"]
    assert [row["trial_id"] for row in surfaces] == list(spec.expected_ids)
    assert [row["issue_number"] for row in surfaces] == list(range(18, 50))
    assert all(row["comment_count"] == 0 for row in surfaces)
    assert all(
        row["url"]
        == f"https://github.com/{spec.repository}/issues/{row['issue_number']}"
        for row in surfaces
    )

    by_trial = {row["trial_id"]: row for row in registry["trials"]}
    assert all(by_trial[row["trial_id"]]["status"] == "ISSUE_CREATED" for row in surfaces)
    for row in surfaces:
        trial = dict(by_trial[row["trial_id"]])
        trial["status"] = "NOT_CREATED"
        expected_body = render_issue_body(trial, registry).encode()
        assert row["title"] == issue_title(row["trial_id"])
        assert row["body_sha256"] == hashlib.sha256(expected_body).hexdigest()
    assert all(
        by_trial[row["trial_id"]]["issue_number"] == row["issue_number"]
        and by_trial[row["trial_id"]]["issue_url"] == row["url"]
        for row in surfaces
    )
    assert len(registry["events"]) == 32
