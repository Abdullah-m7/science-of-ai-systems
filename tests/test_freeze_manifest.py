from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from sais.freeze_manifest import (
    BINDING_SHA256,
    BLOCK_ID,
    CONFIG_COMMIT,
    EXPECTED_ARTIFACT_PATHS,
    FREEZE_TAG,
    MANIFEST_VERSION,
    verify_manifest,
)
from sais.rcl_pc_analysis import ANALYSIS_VERSION, load_study_spec

ROOT = Path(__file__).parents[1]
RELATIVE_MANIFEST = Path("experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json")
MANIFEST = ROOT / RELATIVE_MANIFEST


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(report: dict, relative: str) -> dict:
    return next(item for item in report["artifacts"] if item["path"] == relative)


def _copied_freeze(tmp_path: Path) -> tuple[Path, Path, dict]:
    target_root = tmp_path / "repository"
    subprocess.run(
        ["git", "clone", "--local", "--no-hardlinks", str(ROOT), str(target_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for relative in EXPECTED_ARTIFACT_PATHS:
        source = ROOT / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    target_manifest = target_root / RELATIVE_MANIFEST
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    target_manifest.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return target_root, target_manifest, value


def test_final_freeze_manifest_matches_repository_bytes() -> None:
    report = verify_manifest(MANIFEST, ROOT)
    assert report["checks"]["valid"] is True
    assert report["configuration"]["valid"] is True
    assert report["validation"]["valid"] is True
    assert len(report["artifacts"]) == len(EXPECTED_ARTIFACT_PATHS)
    assert all(item["matches"] for item in report["artifacts"])


def test_study_spec_loads_only_from_valid_freeze() -> None:
    spec = load_study_spec(MANIFEST, root=ROOT)
    assert spec.manifest_version == MANIFEST_VERSION
    assert spec.freeze_tag == FREEZE_TAG
    assert spec.analysis_version == ANALYSIS_VERSION
    assert spec.config_commit == CONFIG_COMMIT
    assert spec.block_id == BLOCK_ID
    assert spec.expected_binding_hash == BINDING_SHA256
    assert len(spec.expected_ids) == 32


def test_frozen_artifact_byte_tamper_is_detected(tmp_path: Path) -> None:
    root, manifest, _ = _copied_freeze(tmp_path)
    relative = "experiments/006-rcl-pc-final-freeze/PREREGISTRATION.md"
    target = root / relative
    target.write_text(target.read_text() + "\nforged\n", encoding="utf-8")
    report = verify_manifest(manifest, root)
    assert report["checks"]["valid"] is False
    assert report["checks"]["artifact_hashes_match"] is False
    assert _artifact(report, relative)["matches"] is False


def test_rehashed_semantic_config_forgery_is_detected(tmp_path: Path) -> None:
    root, manifest_path, value = _copied_freeze(tmp_path)
    relative = "experiments/006-rcl-pc-final-freeze/CONFIG.json"
    config_path = root / relative
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["provider"] = "Forged Provider"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    forged_hash = _sha256(config_path)
    value["configuration"]["sha256"] = forged_hash
    for entry in value["frozen_artifacts"]:
        if entry["path"] == relative:
            entry["sha256"] = forged_hash
    manifest_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    report = verify_manifest(manifest_path, root)
    assert report["checks"]["valid"] is False
    assert report["configuration"]["checks"]["config_provider"] is False
    assert report["configuration"]["checks"]["current_config_sha256"] is False
    assert report["configuration"]["checks"]["source_commit_config_matches"] is False


def test_wrong_configuration_commit_is_detected(tmp_path: Path) -> None:
    root, manifest_path, value = _copied_freeze(tmp_path)
    value["configuration"]["commit"] = "d" * 40
    manifest_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    report = verify_manifest(manifest_path, root)
    assert report["checks"]["valid"] is False
    assert report["configuration"]["checks"]["manifest_config_commit"] is False


def test_missing_frozen_artifact_entry_is_detected(tmp_path: Path) -> None:
    root, manifest_path, value = _copied_freeze(tmp_path)
    value["frozen_artifacts"].pop()
    manifest_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    report = verify_manifest(manifest_path, root)
    assert report["checks"]["valid"] is False
    assert report["checks"]["artifact_paths_exact"] is False


def test_optional_stopping_or_trial_id_change_is_detected(tmp_path: Path) -> None:
    root, manifest_path, value = _copied_freeze(tmp_path)
    value["sample"]["optional_stopping_allowed"] = True
    value["sample"]["trial_ids"][-1] = "PC-RCL-999"
    manifest_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    report = verify_manifest(manifest_path, root)
    assert report["checks"]["valid"] is False
    assert report["checks"]["sample_no_optional_stopping"] is False
    assert report["checks"]["sample_trial_ids"] is False
    with pytest.raises(ValueError, match="invalid freeze manifest"):
        load_study_spec(manifest_path, root=root)


def test_validation_fixture_tamper_is_detected_even_if_manifest_rehashed(tmp_path: Path) -> None:
    root, manifest_path, value = _copied_freeze(tmp_path)
    relative = "experiments/005-config-bound-controller/validation/RCL-VAL-001.public.json"
    fixture = root / relative
    fixture.write_text(fixture.read_text() + "\n", encoding="utf-8")
    forged_hash = _sha256(fixture)
    value["validation"]["fixture_sha256"] = forged_hash
    for entry in value["frozen_artifacts"]:
        if entry["path"] == relative:
            entry["sha256"] = forged_hash
    manifest_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    report = verify_manifest(manifest_path, root)
    assert report["checks"]["valid"] is False
    assert report["validation"]["checks"]["validation_fixture_sha256"] is False
    assert report["validation"]["checks"]["manifest_validation_fixture_sha256"] is False


def test_controller_tag_anchor_is_enforced(tmp_path: Path) -> None:
    root, manifest_path, _ = _copied_freeze(tmp_path)
    subprocess.run(["git", "tag", "-f", "sais-rcl-bound-controller-v1", "HEAD"], cwd=root, check=True, capture_output=True)
    report = verify_manifest(manifest_path, root)
    assert report["checks"]["valid"] is False
    assert report["checks"]["controller_tag_target"] is False
