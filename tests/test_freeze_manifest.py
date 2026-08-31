from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from sais.freeze_manifest import verify_manifest

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "experiments" / "004-construct-validity" / "manifest.json"


def test_candidate_freeze_manifest_matches_repository_bytes():
    report = verify_manifest(MANIFEST, ROOT)
    assert report["checks"]["valid"] is True
    assert all(item["matches"] for item in report["artifacts"])


def test_manifest_hash_tamper_is_detected(tmp_path):
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    value["frozen_artifacts"][0]["sha256"] = "0" * 64
    forged = tmp_path / "manifest.json"
    forged.write_text(json.dumps(value), encoding="utf-8")
    report = verify_manifest(forged, ROOT)
    assert report["checks"]["valid"] is False
    assert report["checks"]["all_artifact_hashes_match"] is False


def test_manifest_repository_tamper_is_semantically_rejected(tmp_path):
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    value["repository"] = "other/repository"
    forged = tmp_path / "manifest.json"
    forged.write_text(json.dumps(value), encoding="utf-8")
    report = verify_manifest(forged, ROOT)
    assert report["checks"]["all_artifact_hashes_match"] is True
    assert report["checks"]["repository"] is False
    assert report["checks"]["valid"] is False


def _copy_frozen_artifacts(value, destination_root):
    for item in value["frozen_artifacts"]:
        source = ROOT / item["path"]
        destination = destination_root / item["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_rehashed_wrong_block_model_is_still_rejected(tmp_path):
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    _copy_frozen_artifacts(value, tmp_path)
    relative = value["block_config"]
    block_path = tmp_path / relative
    block = json.loads(block_path.read_text(encoding="utf-8"))
    block["model_label"] = "Different model"
    block_path.write_text(json.dumps(block, indent=2) + "\n", encoding="utf-8")
    new_hash = hashlib.sha256(block_path.read_bytes()).hexdigest()
    for item in value["frozen_artifacts"]:
        if item["path"] == relative:
            item["sha256"] = new_hash
    forged = tmp_path / "manifest.json"
    forged.write_text(json.dumps(value), encoding="utf-8")

    report = verify_manifest(forged, tmp_path)
    assert report["checks"]["all_artifact_hashes_match"] is True
    assert report["checks"]["block_model_label"] is False
    assert report["checks"]["valid"] is False
