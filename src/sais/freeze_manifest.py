"""Verify the candidate RCL-PC freeze manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_TRIAL_IDS = tuple(f"PC-RCL-{index:03d}" for index in range(1, 33))


def verify_manifest(manifest_path: Path, root: Path | None = None) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    root = root.resolve() if root else manifest_path.parents[2]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("frozen_artifacts", [])
    paths = [item.get("path") for item in artifacts if isinstance(item, dict)]

    checks: dict[str, bool] = {
        "manifest_version": manifest.get("manifest_version") == "SMI-CP/RCL-PC/MANIFEST/1",
        "candidate_status": manifest.get("status") == "CANDIDATE_FREEZE",
        "freeze_tag": manifest.get("freeze_tag") == "sais-rcl-pc-v1",
        "controller_tag": manifest.get("controller", {}).get("tag") == "sais-stage003-controller-v1",
        "controller_commit": manifest.get("controller", {}).get("commit")
        == "e9715e52f24465362d4b0768fc98e9551df2ed8a",
        "trial_count": manifest.get("trial_count") == 32,
        "trial_ids_exact": tuple(manifest.get("trial_ids", [])) == EXPECTED_TRIAL_IDS,
        "artifact_paths_unique": len(paths) == len(set(paths)),
        "no_included_trial_started": manifest.get("first_included_trial_started") is False,
        "public_repository": manifest.get("public_provenance", {}).get("repository")
        == "Abdullah-m7/science-of-ai-systems",
        "controller_actor": manifest.get("public_provenance", {}).get("controller_actor")
        == "github-actions[bot]",
        "subject_actor": manifest.get("public_provenance", {}).get("subject_actor")
        == "Abdullah-m7",
        "dedicated_issue_per_trial": manifest.get("public_provenance", {}).get(
            "dedicated_issue_per_trial"
        ) is True,
        "live_recollection_required": manifest.get("public_provenance", {}).get(
            "live_recollection_required"
        ) is True,
        "execution_gate_hold": manifest.get("execution_gate", {}).get("state")
        == "HOLD",
        "execution_gate_reason": manifest.get("execution_gate", {}).get("reason")
        == "product_configuration_not_yet_bound_to_each_signed_trial",
        "no_execution_before_binding": len(
            manifest.get("execution_gate", {}).get(
                "required_before_first_included_trial", []
            )
        ) >= 4,
    }

    artifact_results = []
    for item in artifacts:
        relative = item.get("path", "")
        path = root / relative
        exists = path.is_file()
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
        matches = exists and actual == item.get("sha256")
        artifact_results.append({
            "path": relative,
            "exists": exists,
            "expected_sha256": item.get("sha256"),
            "actual_sha256": actual,
            "matches": matches,
        })
    checks["all_artifact_hashes_match"] = bool(artifact_results) and all(
        item["matches"] for item in artifact_results
    )
    checks["valid"] = all(checks.values())
    return {"checks": checks, "artifacts": artifact_results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the RCL-PC freeze manifest")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()

    report = verify_manifest(args.manifest, args.root)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["checks"]["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
