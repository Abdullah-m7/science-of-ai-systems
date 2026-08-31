from __future__ import annotations

import json
from pathlib import Path

from sais.rcl_bound_evidence import verify_public_trial

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / (
    "experiments/005-config-bound-controller/validation/"
    "RCL-VAL-001.public.json"
)
CONTROLLER_SHA = "c899213eb5b3f68a77e399a9dd32a9f86a827824"
CONFIG_PATH = (
    "experiments/005-config-bound-controller/validation/CONFIG.json"
)
BINDING_HASH = (
    "dffe11d7898a74d61b0b33a3f15843f185008711516cf7825f3a434b3a43c177"
)


def test_rcl_val_001_public_fixture_reproduces_all_checks():
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    checks = verify_public_trial(
        bundle,
        expected_repository="Abdullah-m7/science-of-ai-systems",
        expected_controller_actor="github-actions[bot]",
        expected_subject_actor="Abdullah-m7",
        expected_controller_code_sha=CONTROLLER_SHA,
        expected_configuration_commit=CONTROLLER_SHA,
        expected_configuration_path=CONFIG_PATH,
        expected_block_id="RCL-VAL-001",
    )

    assert checks["valid"] is True
    assert len(checks) - 1 == 100
    assert [name for name, value in checks.items() if value is False] == []
    assert bundle["ledger"]["trial_id"] == "RCL-VAL-001"
    assert (
        bundle["ledger"]["configuration_binding_hash"] == BINDING_HASH
    )
    assert bundle["reveal"]["seal_comment_id"] == 5475382000
    reveal_id = next(
        int(item["id"])
        for item in bundle["public_record"]["comments"]
        if item["body"].startswith("SAIS_RCL_REVEAL ")
    )
    assert bundle["reveal"]["seal_comment_id"] < reveal_id
