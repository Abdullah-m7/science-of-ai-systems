"""Verify the final RCL-PC freeze package before included trials begin."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any

from .config_binding import (
    BINDING_PROTOCOL,
    CONFIG_PROTOCOL,
    binding_hash,
    build_binding,
    load_product_config,
)
from .rcl_bound_evidence import verify_public_trial

MANIFEST_VERSION = "SMI-CP/RCL-PC/MANIFEST/2"
FREEZE_TAG = "sais-rcl-pc-v2"
SUPERSEDED_TAG = "sais-rcl-pc-v1"
SUPERSEDED_COMMIT = "332075e3b887053c641f19b41f410e8f2c4721ee"
INVALIDATION_PATH = "experiments/006-rcl-pc-final-freeze/FREEZE_V1_INVALIDATION.md"
REPOSITORY = "Abdullah-m7/science-of-ai-systems"
STUDY_PROTOCOL = "SMI-CP/RCL-PC/2"
ANALYSIS_VERSION = "SMI-CP/RCL-PC/ANALYSIS/2"
BLOCK_ID = "RCL-PC-GPT56SOL-IOS-20260901-A"
SUBJECT_LOGIN = "Abdullah-m7"
SUBJECT_VERSION = "SMI-CP/RCL-PC/SUBJECT/2"
CONTROLLER_PROTOCOL = "SMI-CP/RCL-PC/CTRL/1"
CONTROLLER_TAG = "sais-rcl-bound-controller-v1"
CONTROLLER_COMMIT = "c899213eb5b3f68a77e399a9dd32a9f86a827824"
CONTROLLER_ACTOR = "github-actions[bot]"
WORKFLOW_PATH = ".github/workflows/rcl-bound-controller.yml"

CONFIG_COMMIT = "b6a1e728f9ced540306b604dece5e42465b46073"
CONFIG_PATH = "experiments/006-rcl-pc-final-freeze/CONFIG.json"
CONFIG_SHA256 = "a9358d9e3a6bf91eb42dc0b6ae997d4e1a12ade26086dc1ae50d70f2a002e4de"
SCHEMA_PATH = "experiments/006-rcl-pc-final-freeze/CONFIG_SCHEMA.json"
SCHEMA_SHA256 = "4cd923c6932538c316eb273789fe523731ae01402df459662e88e909c3a1d48a"
SUBJECT_PATH = "experiments/006-rcl-pc-final-freeze/SUBJECT_INSTRUCTIONS.md"
SUBJECT_SHA256 = "6fa4af5edd19d83ab8e41814544a6be69deb17ecca274c83fce4c2d0bff24d39"
BINDING_SHA256 = "6d09daad4c45c1976794add2c7a404aca0e3f27fca1946ad467b900b00d85caa"

BOOTSTRAP_SEED = 20260831
BOOTSTRAP_REPS = 20_000
TRIAL_IDS = tuple(f"PC-RCL-{index:03d}" for index in range(1, 33))
EXCLUDED_PREFIXES = ("S001-", "S002", "S003-", "RCL-VAL-")
FINAL_STATUSES = ("PASS", "FAIL", "INCOMPLETE", "INVALID")

VALIDATION_TRIAL_ID = "RCL-VAL-001"
VALIDATION_CONFIG_COMMIT = CONTROLLER_COMMIT
VALIDATION_CONFIG_PATH = "experiments/005-config-bound-controller/validation/CONFIG.json"
VALIDATION_BLOCK_ID = "RCL-VAL-001"
VALIDATION_FIXTURE_PATH = "experiments/005-config-bound-controller/validation/RCL-VAL-001.public.json"
VALIDATION_FIXTURE_SHA256 = "12e70c4ea3839f8447655c3f85464bbba52913e71abf5419dd61a8b45bfb33a5"
VALIDATION_RESULT_PATH = "experiments/005-config-bound-controller/validation/VALIDATION_RESULT.md"
VALIDATION_RESULT_SHA256 = "40d3ec81da2917cc41b86094b5dea67196a5f0bff5a917df0db94c4f3a0ea43e"
VALIDATION_RUN_ID = 33369858082
VALIDATION_CHECK_COUNT = 100

EXPECTED_ARTIFACT_PATHS = (
    "experiments/006-rcl-pc-final-freeze/PREREGISTRATION.md",
    SUBJECT_PATH,
    SCHEMA_PATH,
    CONFIG_PATH,
    "experiments/006-rcl-pc-final-freeze/RUNBOOK.md",
    INVALIDATION_PATH,
    VALIDATION_FIXTURE_PATH,
    VALIDATION_RESULT_PATH,
    "src/sais/rcl_pc_analysis.py",
    "src/sais/freeze_manifest.py",
    "src/sais/rcl_bound_evidence.py",
    "src/sais/rcl_bound_controller.py",
    "src/sais/config_binding.py",
    WORKFLOW_PATH,
)
EXPECTED_AVAILABLE_TOOLS = (
    "GitHub connector",
    "web retrieval",
    "conversation file and library tools",
    "Python execution",
    "Remote Desktop Commander",
    "Google Workspace connectors",
    "Adobe and Canva connectors",
    "image generation",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and str(path) == value


def _utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0


def _git_bytes(root: Path, commit: str, path: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout


def _tag_target(root: Path, tag: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-list", "-n", "1", tag],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value if HEX40.fullmatch(value) else None


def _artifact_report(
    root: Path, entries: Any
) -> tuple[list[dict[str, Any]], dict[str, bool]]:
    if not isinstance(entries, list):
        return [], {"artifact_entries_list": False}
    rows: list[dict[str, Any]] = []
    paths: list[Any] = []
    well_formed = True
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            well_formed = False
            continue
        relative = entry.get("path")
        expected = entry.get("sha256")
        paths.append(relative)
        safe = _safe_relative(relative)
        formatted = isinstance(expected, str) and bool(HEX64.fullmatch(expected))
        target = root / str(relative) if safe else root / "__invalid__"
        exists = safe and target.is_file()
        actual = _sha256_file(target) if exists else None
        rows.append({
            "path": relative,
            "expected_sha256": expected,
            "actual_sha256": actual,
            "exists": exists,
            "matches": bool(formatted and exists and actual == expected),
        })
    checks = {
        "artifact_entries_list": True,
        "artifact_entries_well_formed": well_formed and len(rows) == len(entries),
        "artifact_paths_exact": tuple(paths) == EXPECTED_ARTIFACT_PATHS,
        "artifact_paths_unique": len(paths) == len(set(paths)),
        "artifact_paths_safe": all(_safe_relative(path) for path in paths),
        "artifact_hashes_match": bool(rows) and all(row["matches"] for row in rows),
    }
    return rows, checks


def _configuration_report(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    configuration = manifest.get("configuration")
    if not isinstance(configuration, dict):
        return {"checks": {"configuration_object": False}, "valid": False}
    config_path = root / CONFIG_PATH
    subject_path = root / SUBJECT_PATH
    schema_path = root / SCHEMA_PATH
    try:
        config, config_bytes = load_product_config(config_path)
    except (OSError, ValueError):
        return {"checks": {"configuration_object": False}, "valid": False}
    current_subject = subject_path.read_bytes() if subject_path.is_file() else b""
    current_schema = schema_path.read_bytes() if schema_path.is_file() else b""
    committed_config = _git_bytes(root, CONFIG_COMMIT, CONFIG_PATH)
    committed_subject = _git_bytes(root, CONFIG_COMMIT, SUBJECT_PATH)
    binding = build_binding(
        config,
        config_bytes,
        repository=REPOSITORY,
        commit=CONFIG_COMMIT,
        path=CONFIG_PATH,
    )
    computed_binding = binding_hash(binding)
    checks = {
        "configuration_object": True,
        "manifest_config_repository": configuration.get("repository") == REPOSITORY,
        "manifest_config_commit": configuration.get("commit") == CONFIG_COMMIT,
        "manifest_config_path": configuration.get("path") == CONFIG_PATH,
        "manifest_config_sha256": configuration.get("sha256") == CONFIG_SHA256,
        "manifest_schema_path": configuration.get("schema_path") == SCHEMA_PATH,
        "manifest_schema_sha256": configuration.get("schema_sha256") == SCHEMA_SHA256,
        "manifest_protocol": configuration.get("protocol_version") == CONFIG_PROTOCOL,
        "manifest_block_id": configuration.get("block_id") == BLOCK_ID,
        "manifest_subject_path": configuration.get("subject_instruction_path") == SUBJECT_PATH,
        "manifest_subject_sha256": configuration.get("subject_instruction_sha256") == SUBJECT_SHA256,
        "manifest_binding_sha256": configuration.get("binding_sha256") == BINDING_SHA256,
        "current_config_sha256": _sha256_bytes(config_bytes) == CONFIG_SHA256,
        "current_subject_sha256": _sha256_bytes(current_subject) == SUBJECT_SHA256,
        "current_schema_sha256": _sha256_bytes(current_schema) == SCHEMA_SHA256,
        "source_commit_config_available": committed_config is not None,
        "source_commit_subject_available": committed_subject is not None,
        "source_commit_config_matches": committed_config == config_bytes,
        "source_commit_subject_matches": committed_subject == current_subject,
        "binding_protocol": binding.get("binding_protocol") == BINDING_PROTOCOL,
        "binding_hash": computed_binding == BINDING_SHA256,
    }
    checks.update({
        "config_provider": config.get("provider") == "OpenAI",
        "config_product": config.get("product") == "ChatGPT",
        "config_model_label": config.get("model_label") == "GPT-5.6 Sol",
        "config_model_snapshot_unobserved": config.get("model_build_or_snapshot") is None,
        "config_interface": config.get("interface") == "ChatGPT native iOS app with GitHub connector-mediated issue interaction",
        "config_interface_build": config.get("interface_build") == "ChatGPT/1.2026.230; iOS 26.6.1",
        "config_conversation_state": config.get("conversation_state") == "fresh",
        "config_memory_state": config.get("memory_state") == "enabled",
        "config_customization_state": config.get("customization_state") == "present",
        "config_reasoning_setting": config.get("reasoning_setting") == "GPT-5.6 Sol",
        "config_locale": config.get("locale") == "ar-SA; protocol messages in English",
        "config_available_tools": tuple(config.get("available_tools", [])) == EXPECTED_AVAILABLE_TOOLS,
        "config_permitted_tools": config.get("permitted_trial_tools") == ["GitHub issue read", "GitHub issue comment"],
        "config_subject_path": config.get("subject_instruction_path") == SUBJECT_PATH,
        "config_subject_sha256": config.get("subject_instruction_sha256") == SUBJECT_SHA256,
        "config_hidden_instructions_truthful": config.get("system_instructions_observable") is False and config.get("system_instructions_record") is None,
        "config_recorded_at_utc": _utc_timestamp(config.get("recorded_at_utc")),
    })
    return {
        "checks": checks,
        "binding": binding,
        "computed_binding_sha256": computed_binding,
        "valid": all(checks.values()),
    }


def _validation_report(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    fixture_path = root / VALIDATION_FIXTURE_PATH
    result_path = root / VALIDATION_RESULT_PATH
    evidence_checks: dict[str, bool] = {}
    if fixture_path.is_file():
        try:
            bundle = json.loads(fixture_path.read_text(encoding="utf-8"))
            evidence_checks = verify_public_trial(
                bundle,
                expected_repository=REPOSITORY,
                expected_controller_actor=CONTROLLER_ACTOR,
                expected_subject_actor=SUBJECT_LOGIN,
                expected_controller_code_sha=CONTROLLER_COMMIT,
                expected_configuration_commit=VALIDATION_CONFIG_COMMIT,
                expected_configuration_path=VALIDATION_CONFIG_PATH,
                expected_block_id=VALIDATION_BLOCK_ID,
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            evidence_checks = {}
    validation = manifest.get("validation")
    validation = validation if isinstance(validation, dict) else {}
    result_text = result_path.read_text(encoding="utf-8") if result_path.is_file() else ""
    checks = {
        "validation_fixture_exists": fixture_path.is_file(),
        "validation_result_exists": result_path.is_file(),
        "validation_fixture_sha256": fixture_path.is_file() and _sha256_file(fixture_path) == VALIDATION_FIXTURE_SHA256,
        "validation_result_sha256": result_path.is_file() and _sha256_file(result_path) == VALIDATION_RESULT_SHA256,
        "validation_public_evidence": bool(evidence_checks.get("valid", False)),
        "validation_check_count": len([name for name in evidence_checks if name != "valid"]) == VALIDATION_CHECK_COUNT,
        "validation_result_pass": "Status: **PASS**" in result_text,
        "validation_result_run": str(VALIDATION_RUN_ID) in result_text,
        "manifest_validation_trial": validation.get("trial_id") == VALIDATION_TRIAL_ID,
        "manifest_validation_excluded": validation.get("excluded") is True,
        "manifest_validation_fixture": validation.get("fixture_path") == VALIDATION_FIXTURE_PATH,
        "manifest_validation_fixture_sha256": validation.get("fixture_sha256") == VALIDATION_FIXTURE_SHA256,
        "manifest_validation_result": validation.get("result_path") == VALIDATION_RESULT_PATH,
        "manifest_validation_result_sha256": validation.get("result_sha256") == VALIDATION_RESULT_SHA256,
        "manifest_validation_run": validation.get("controller_run_id") == VALIDATION_RUN_ID,
        "manifest_validation_checks": validation.get("verification_checks") == VALIDATION_CHECK_COUNT,
    }
    return {
        "checks": checks,
        "evidence_checks": evidence_checks,
        "valid": all(checks.values()),
    }


def verify_manifest(manifest_path: Path, root: Path | None = None) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    root = root.resolve() if root else manifest_path.parents[2]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "checks": {"manifest_parseable": False, "valid": False},
            "error": str(error),
        }
    if not isinstance(manifest, dict):
        return {"checks": {"manifest_object": False, "valid": False}}
    study = manifest.get("study") if isinstance(manifest.get("study"), dict) else {}
    subject = manifest.get("subject") if isinstance(manifest.get("subject"), dict) else {}
    controller = manifest.get("controller") if isinstance(manifest.get("controller"), dict) else {}
    sample = manifest.get("sample") if isinstance(manifest.get("sample"), dict) else {}
    analysis = manifest.get("analysis") if isinstance(manifest.get("analysis"), dict) else {}
    thresholds = analysis.get("thresholds") if isinstance(analysis.get("thresholds"), dict) else {}
    supersedes = manifest.get("supersedes") if isinstance(manifest.get("supersedes"), dict) else {}
    checks: dict[str, bool] = {
        "manifest_parseable": True,
        "manifest_object": True,
        "manifest_version": manifest.get("manifest_version") == MANIFEST_VERSION,
        "status_final_freeze": manifest.get("status") == "FINAL_FREEZE",
        "freeze_tag": manifest.get("freeze_tag") == FREEZE_TAG,
        "prepared_at_utc": _utc_timestamp(manifest.get("prepared_at_utc")),
        "repository": manifest.get("repository") == REPOSITORY,
        "first_included_trial_not_started": manifest.get("first_included_trial_started") is False,
        "study_id": study.get("study_id") == "RCL-PC",
        "study_protocol": study.get("protocol_version") == STUDY_PROTOCOL,
        "study_analysis_version": study.get("analysis_version") == ANALYSIS_VERSION,
        "study_block_id": study.get("block_id") == BLOCK_ID,
        "study_language": study.get("interaction_language") == "English",
        "subject_login": subject.get("login") == SUBJECT_LOGIN,
        "subject_version": subject.get("instruction_version") == SUBJECT_VERSION,
        "controller_protocol": controller.get("protocol_version") == CONTROLLER_PROTOCOL,
        "controller_tag": controller.get("tag") == CONTROLLER_TAG,
        "controller_commit": controller.get("commit") == CONTROLLER_COMMIT,
        "controller_workflow": controller.get("workflow") == WORKFLOW_PATH,
        "controller_actor": controller.get("actor") == CONTROLLER_ACTOR,
        "controller_tag_target": _tag_target(root, CONTROLLER_TAG) == CONTROLLER_COMMIT,
        "superseded_tag": supersedes.get("freeze_tag") == SUPERSEDED_TAG,
        "superseded_reason": supersedes.get("reason") == "pre-trial model-identity provenance error",
        "superseded_invalidation_path": supersedes.get("invalidation_path") == INVALIDATION_PATH,
        "superseded_tag_target": _tag_target(root, SUPERSEDED_TAG) == SUPERSEDED_COMMIT,
    }
    checks.update({
        "sample_trial_count": sample.get("trial_count") == len(TRIAL_IDS),
        "sample_trial_ids": tuple(sample.get("trial_ids", [])) == TRIAL_IDS,
        "sample_no_replacement": sample.get("replacement_allowed") is False,
        "sample_requires_all_records": sample.get("requires_all_records") is True,
        "sample_requires_protocol_fidelity": sample.get("requires_protocol_fidelity") is True,
        "sample_no_optional_stopping": sample.get("optional_stopping_allowed") is False,
        "analysis_version": analysis.get("version") == ANALYSIS_VERSION,
        "analysis_bootstrap_seed": analysis.get("bootstrap_seed") == BOOTSTRAP_SEED,
        "analysis_bootstrap_reps": analysis.get("bootstrap_reps") == BOOTSTRAP_REPS,
        "analysis_public_required": analysis.get("require_public_provenance") is True,
        "analysis_artifact_final_forbidden": analysis.get("artifact_only_final_allowed") is False,
        "analysis_final_statuses": tuple(analysis.get("final_statuses", [])) == FINAL_STATUSES,
        "analysis_primary_threshold": thresholds.get("primary_effect_min") == 0.15,
        "analysis_direction_threshold": thresholds.get("transparent_correct_direction_rate_min") == 0.8,
        "analysis_opaque_threshold": thresholds.get("opaque_mean_abs_update_max") == 0.1,
        "excluded_prefixes": tuple(manifest.get("excluded_prefixes", [])) == EXCLUDED_PREFIXES,
        "execution_gate_ready": isinstance(manifest.get("execution_gate"), dict) and manifest["execution_gate"].get("status") == "READY",
    })
    artifacts, artifact_checks = _artifact_report(root, manifest.get("frozen_artifacts"))
    checks.update(artifact_checks)
    configuration = _configuration_report(root, manifest)
    validation = _validation_report(root, manifest)
    checks["configuration_valid"] = bool(configuration.get("valid"))
    checks["validation_valid"] = bool(validation.get("valid"))
    checks["valid"] = all(checks.values())
    return {
        "manifest": str(manifest_path),
        "root": str(root),
        "checks": checks,
        "artifacts": artifacts,
        "configuration": configuration,
        "validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the final RCL-PC freeze package")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    report = verify_manifest(args.manifest, args.root)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    if not report["checks"].get("valid", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
