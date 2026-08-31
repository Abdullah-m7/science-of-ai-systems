from __future__ import annotations

import json
from pathlib import Path

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


def test_manifest_public_provenance_tamper_is_detected(tmp_path):
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    value["public_provenance"]["controller_actor"] = "unfrozen-controller"
    forged = tmp_path / "manifest.json"
    forged.write_text(json.dumps(value), encoding="utf-8")
    report = verify_manifest(forged, ROOT)
    assert report["checks"]["valid"] is False
    assert report["checks"]["controller_actor"] is False
