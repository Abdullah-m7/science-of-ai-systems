"""Verify the candidate RCL-PC freeze manifest and its block semantics."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any

MANIFEST_VERSION = "SMI-CP/RCL-PC/MANIFEST/1"
FREEZE_TAG = "sais-rcl-pc-v1"
REPOSITORY = "Abdullah-m7/science-of-ai-systems"
SUBJECT_LOGIN = "Abdullah-m7"
SUBJECT_INSTRUCTION_VERSION = "SMI-CP/RCL-PC/SUBJECT/1"
ANALYSIS_VERSION = "SMI-CP/RCL-PC/ANALYSIS/1"
CONTROLLER_PROTOCOL = "SMI-CP/003/1"
CONTROLLER_TAG = "sais-stage003-controller-v1"
CONTROLLER_COMMIT = "e9715e52f24465362d4b0768fc98e9551df2ed8a"
CONTROLLER_ACTOR = "github-actions[bot]"
CONTROLLER_WORKFLOW = ".github/workflows/stage003-controller.yml"
BLOCK_CONFIG_PATH = "experiments/004-construct-validity/BLOCK_CONFIG.json"
BLOCK_ID = "PC-RCL-CHATGPT-2026-08-31-A"
EXPECTED_TRIAL_IDS = tuple(f"PC-RCL-{index:03d}" for index in range(1, 33))
EXPECTED_EXCLUDED_PREFIXES = ("S001-", "S002", "S003-", "DRYRUN-")
EXPECTED_ARTIFACT_PATHS = (
    "experiments/004-construct-validity/DESIGN_AUDIT.md",
    "experiments/004-construct-validity/RCL_PC_PREREGISTRATION.md",
    "experiments/004-construct-validity/SUBJECT_INSTRUCTIONS.md",
    "experiments/004-construct-validity/PUBLIC_EVIDENCE_PROTOCOL.md",
    "experiments/004-construct-validity/config.schema.json",
    BLOCK_CONFIG_PATH,
    "src/sais/rcl_pc_analysis.py",
    "src/sais/public_evidence.py",
)
HEX64 = re.compile(r"^[a-f0-9]{64}$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _is_utc_timestamp(value: Any) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    offset = parsed.utcoffset()
    return parsed.tzinfo is not None and offset is not None and offset.total_seconds() == 0


def verify_manifest(manifest_path: Path, root: Path | None = None) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    root = root.resolve() if root else manifest_path.parents[2]
    manifest = _load_object(manifest_path)
    if manifest is None:
        return {
            "checks": {"manifest_json_object": False, "valid": False},
            "artifacts": [],
        }

    artifacts = manifest.get("frozen_artifacts", [])
    artifact_rows = [item for item in artifacts if isinstance(item, dict)]
    paths = [item.get("path") for item in artifact_rows]
    controller = manifest.get("controller", {})
    if not isinstance(controller, dict):
        controller = {}

    checks: dict[str, bool] = {
        "manifest_json_object": True,
        "manifest_version": manifest.get("manifest_version") == MANIFEST_VERSION,
        "candidate_status": manifest.get("status") == "CANDIDATE_FREEZE",
        "freeze_tag": manifest.get("freeze_tag") == FREEZE_TAG,
        "repository": manifest.get("repository") == REPOSITORY,
        "interaction_language": manifest.get("interaction_language") == "English",
        "subject_login": manifest.get("subject_login") == SUBJECT_LOGIN,
        "subject_instruction_version": (
            manifest.get("subject_instruction_version") == SUBJECT_INSTRUCTION_VERSION
        ),
        "analysis_version": manifest.get("analysis_version") == ANALYSIS_VERSION,
        "bootstrap_reps": manifest.get("bootstrap_reps") == 20_000,
        "bootstrap_seed": manifest.get("bootstrap_seed") == 20260831,
        "block_config_path": manifest.get("block_config") == BLOCK_CONFIG_PATH,
        "controller_protocol": controller.get("protocol_version") == CONTROLLER_PROTOCOL,
        "controller_tag": controller.get("tag") == CONTROLLER_TAG,
        "controller_commit": controller.get("commit") == CONTROLLER_COMMIT,
        "controller_actor": controller.get("actor") == CONTROLLER_ACTOR,
        "controller_workflow": controller.get("workflow") == CONTROLLER_WORKFLOW,
        "trial_count": manifest.get("trial_count") == len(EXPECTED_TRIAL_IDS),
        "trial_ids_exact": tuple(manifest.get("trial_ids", [])) == EXPECTED_TRIAL_IDS,
        "excluded_prefixes_exact": (
            tuple(manifest.get("excluded_prefixes", [])) == EXPECTED_EXCLUDED_PREFIXES
        ),
        "artifact_records_well_formed": len(artifact_rows) == len(artifacts),
        "artifact_paths_exact": tuple(paths) == EXPECTED_ARTIFACT_PATHS,
        "artifact_paths_safe": all(_safe_relative(path) for path in paths),
        "artifact_hashes_well_formed": all(
            isinstance(item.get("sha256"), str)
            and HEX64.fullmatch(item["sha256"]) is not None
            for item in artifact_rows
        ),
        "no_included_trial_started": manifest.get("first_included_trial_started") is False,
    }

    artifact_results: list[dict[str, Any]] = []
    for item in artifact_rows:
        relative = item.get("path")
        safe = _safe_relative(relative)
        path = root / relative if safe else None
        exists = bool(path and path.is_file())
        actual = _sha256(path) if exists and path else None
        expected = item.get("sha256")
        artifact_results.append({
            "path": relative,
            "exists": exists,
            "expected_sha256": expected,
            "actual_sha256": actual,
            "matches": bool(exists and actual == expected),
        })
    checks["all_artifact_hashes_match"] = (
        len(artifact_results) == len(EXPECTED_ARTIFACT_PATHS)
        and all(item["matches"] for item in artifact_results)
    )

    block_path = root / BLOCK_CONFIG_PATH
    block = _load_object(block_path)
    subject_path = root / "experiments/004-construct-validity/SUBJECT_INSTRUCTIONS.md"
    subject_hash = _sha256(subject_path) if subject_path.is_file() else None
    schema_path = root / "experiments/004-construct-validity/config.schema.json"
    schema = _load_object(schema_path)
    permitted = ["GitHub issue comments through the GitHub connector"]
    available_tools = block.get("available_tools", []) if block else []

    checks.update({
        "block_config_json_object": block is not None,
        "block_protocol": bool(block and block.get("protocol_version") == "SMI-CP/RCL-PC/1"),
        "block_id": bool(block and block.get("block_id") == BLOCK_ID),
        "block_provider": bool(block and block.get("provider") == "OpenAI"),
        "block_product": bool(block and block.get("product") == "ChatGPT"),
        "block_model_label": bool(block and block.get("model_label") == "GPT-5.6 Pro"),
        "block_interface": bool(
            block
            and block.get("interface")
            == "ChatGPT native iOS application with GitHub connector"
        ),
        "block_timestamp": bool(block and _is_utc_timestamp(block.get("recorded_at_utc"))),
        "block_fresh_context": bool(block and block.get("conversation_state") == "fresh"),
        "block_memory_state": bool(block and block.get("memory_state") == "enabled"),
        "block_customization_state": bool(
            block and block.get("customization_state") == "present"
        ),
        "block_permitted_tools": bool(
            block and block.get("permitted_trial_tools") == permitted
        ),
        "block_available_tools_unique": bool(
            isinstance(available_tools, list)
            and available_tools
            and len(available_tools) == len(set(available_tools))
            and "GitHub connector" in available_tools
        ),
        "block_subject_instruction_hash": bool(
            block
            and subject_hash is not None
            and block.get("subject_instruction_sha256") == subject_hash
        ),
        "block_hidden_instruction_record_truthful": bool(
            block
            and block.get("system_instructions_observable") is False
            and block.get("system_instructions_record") is None
        ),
        "config_schema_json_object": schema is not None,
        "config_schema_id": bool(schema and schema.get("$id") == "urn:sais:rcl-pc:config:1"),
        "block_config_is_frozen_artifact": BLOCK_CONFIG_PATH in paths,
    })
    checks["valid"] = all(checks.values())
    return {"checks": checks, "artifacts": artifact_results}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the RCL-PC freeze manifest and block semantics"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()

    report = verify_manifest(args.manifest, args.root)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["checks"].get("valid", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
