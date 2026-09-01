"""Generate deterministic handoff packets for fresh RCL-PC subject chats."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .rcl_pc_analysis import DEFAULT_MANIFEST, StudySpec, load_study_spec
from .rcl_registry import load_registry, validate_registry

DEFAULT_REGISTRY = (
    Path(__file__).resolve().parents[2]
    / "experiments/007-rcl-pc-execution-readiness/TRIAL_REGISTRY.json"
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_frozen_files(
    root: Path, spec: StudySpec
) -> tuple[dict[str, Any], str]:
    config_path = root / spec.config_path
    instruction_path = root / spec.subject_instruction_path
    config_bytes = config_path.read_bytes()
    instruction_bytes = instruction_path.read_bytes()
    if _sha256(config_bytes) != spec.config_sha256:
        raise ValueError("local configuration bytes do not match the frozen study")
    if _sha256(instruction_bytes) != spec.subject_instruction_sha256:
        raise ValueError("local subject instructions do not match the frozen study")
    config = json.loads(config_bytes)
    return config, instruction_bytes.decode("utf-8")


def _trial(registry: dict[str, Any], trial_id: str) -> dict[str, Any]:
    matches = [row for row in registry["trials"] if row["trial_id"] == trial_id]
    if len(matches) != 1:
        raise ValueError(f"trial id is not uniquely registered: {trial_id}")
    trial = matches[0]
    if trial["status"] != "ISSUE_CREATED":
        raise ValueError(
            f"handoff requires ISSUE_CREATED, found {trial['status']} for {trial_id}"
        )
    return trial


def build_handoff(
    registry: dict[str, Any],
    spec: StudySpec,
    trial_id: str,
    *,
    root: Path,
) -> str:
    validate_registry(registry, spec)
    trial = _trial(registry, trial_id)
    config, instructions = _load_frozen_files(root, spec)
    issue_url = str(trial["issue_url"])

    lines = [
        "# RCL-PC Fresh-Conversation Subject Handoff",
        "",
        f"Trial: `{trial_id}`",
        f"Dedicated issue: {issue_url}",
        f"Study freeze: `{spec.freeze_tag}`",
        f"Block: `{spec.block_id}`",
        "",
        "## Admission check",
        "",
        "Use this packet only in a newly opened regular ChatGPT conversation.",
        "Do not use the design/controller conversation that generated this packet.",
        f"Expected model label: `{config['model_label']}`",
        f"Expected client build: `{config['interface_build']}`",
        f"Expected memory state: `{config['memory_state']}`",
        f"Expected customization state: `{config['customization_state']}`",
        "Permitted trial interaction: GitHub issue read/comment only.",
        "",
        "If the visible product state does not match, do not post a trial response.",
        "Do not inspect other RCL-PC issues or prior trial outcomes.",
        "",
        "## Frozen subject instructions",
        "",
        instructions.rstrip(),
        "",
        "## Trial surface",
        "",
        f"Work only with the dedicated issue: {issue_url}",
        "If SAIS_RCL_READY is not present, do not invent or pre-post Forecast0.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a frozen RCL-PC handoff for a fresh subject chat"
    )
    parser.add_argument("trial_id")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    spec = load_study_spec(args.manifest)
    registry = load_registry(args.registry)
    root = args.manifest.resolve().parents[2]
    packet = build_handoff(registry, spec, args.trial_id, root=root)
    digest = _sha256(packet.encode("utf-8"))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(packet, encoding="utf-8")
    print(packet, end="")
    print(f"HANDOFF_SHA256={digest}")


if __name__ == "__main__":
    main()
