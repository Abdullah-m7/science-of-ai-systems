"""Validation and byte-level binding for RCL product configuration records."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .ephemeral_controller import object_hash

CONFIG_PROTOCOL = "SMI-CP/RCL-PC/CONFIG/2"
BINDING_PROTOCOL = "SMI-CP/RCL-PC/CONFIG-BINDING/1"
BLOCK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

REQUIRED_FIELDS = {
    "protocol_version",
    "block_id",
    "recorded_at_utc",
    "provider",
    "product",
    "model_label",
    "interface",
    "conversation_state",
    "memory_state",
    "available_tools",
    "permitted_trial_tools",
    "subject_instruction_path",
    "subject_instruction_sha256",
    "notes",
}
OPTIONAL_FIELDS = {
    "model_build_or_snapshot",
    "interface_build",
    "customization_state",
    "reasoning_setting",
    "locale",
    "system_instructions_observable",
    "system_instructions_record",
    "product_status_page_checked",
}
BINDING_FIELDS = {
    "binding_protocol",
    "block_id",
    "repository",
    "commit",
    "path",
    "config_sha256",
    "config_protocol",
}


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be an array of strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{name} must contain unique values")
    return value


def validate_product_config(config: dict[str, Any]) -> None:
    if not isinstance(config, dict):
        raise ValueError("product configuration must be an object")
    missing = sorted(REQUIRED_FIELDS - set(config))
    if missing:
        raise ValueError("missing product configuration fields: " + ", ".join(missing))
    extra = sorted(set(config) - REQUIRED_FIELDS - OPTIONAL_FIELDS)
    if extra:
        raise ValueError("unknown product configuration fields: " + ", ".join(extra))
    if config.get("protocol_version") != CONFIG_PROTOCOL:
        raise ValueError("unsupported product configuration protocol")
    block_id = _nonempty_string(config.get("block_id"), "block_id")
    if not BLOCK_ID_RE.fullmatch(block_id):
        raise ValueError("unsafe block_id")
    for name in ("provider", "product", "model_label", "interface"):
        _nonempty_string(config.get(name), name)
    if not isinstance(config.get("notes"), str):
        raise ValueError("notes must be a string")
    recorded = _nonempty_string(config.get("recorded_at_utc"), "recorded_at_utc")
    try:
        timestamp = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("recorded_at_utc must be ISO-8601") from error
    if timestamp.tzinfo is None:
        raise ValueError("recorded_at_utc must include a timezone")
    if timestamp.utcoffset() != timedelta(0):
        raise ValueError("recorded_at_utc must use UTC")
    if config.get("conversation_state") not in {
        "fresh",
        "continued",
        "temporary",
        "unknown",
    }:
        raise ValueError("invalid conversation_state")
    if config.get("memory_state") not in {
        "enabled",
        "disabled",
        "not_available",
        "unknown",
    }:
        raise ValueError("invalid memory_state")
    if "customization_state" in config and config["customization_state"] not in {
        "present",
        "absent",
        "unknown",
    }:
        raise ValueError("invalid customization_state")
    for name in (
        "model_build_or_snapshot",
        "interface_build",
        "reasoning_setting",
        "locale",
        "system_instructions_record",
    ):
        if (
            name in config
            and config[name] is not None
            and not isinstance(config[name], str)
        ):
            raise ValueError(f"{name} must be a string or null")
    if "system_instructions_observable" in config and not isinstance(
        config["system_instructions_observable"], bool
    ):
        raise ValueError("system_instructions_observable must be boolean")
    if (
        "product_status_page_checked" in config
        and config["product_status_page_checked"] is not None
        and not isinstance(config["product_status_page_checked"], bool)
    ):
        raise ValueError("product_status_page_checked must be boolean or null")
    _string_list(config.get("available_tools"), "available_tools")
    _string_list(config.get("permitted_trial_tools"), "permitted_trial_tools")
    validate_repository_path(
        _nonempty_string(
            config.get("subject_instruction_path"), "subject_instruction_path"
        ),
        label="subject instruction",
    )
    if not SHA256_RE.fullmatch(str(config.get("subject_instruction_sha256", ""))):
        raise ValueError("subject_instruction_sha256 must be lowercase SHA-256")


def load_product_config(path: str | Path) -> tuple[dict[str, Any], bytes]:
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise ValueError("product configuration must be a regular file")
    raw = target.read_bytes()
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("product configuration is not valid JSON") from error
    validate_product_config(config)
    return config, raw


def validate_repository_path(path: str, *, label: str = "configuration") -> None:
    if not isinstance(path, str):
        raise ValueError(f"unsafe {label} path")
    parts = path.split("/")
    if (
        not parts
        or any(part in {"", ".", ".."} for part in parts)
        or "\\" in path
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
    ):
        raise ValueError(f"unsafe {label} path")


def validate_repository_name(repository: str) -> None:
    if not REPOSITORY_RE.fullmatch(repository):
        raise ValueError("configuration repository must be owner/name")
    owner, name = repository.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise ValueError("unsafe configuration repository")
    if any(ord(character) < 32 or ord(character) == 127 for character in repository):
        raise ValueError("unsafe configuration repository")


def validate_reference(repository: str, commit: str, path: str) -> None:
    validate_repository_name(repository)
    if not COMMIT_RE.fullmatch(commit):
        raise ValueError("configuration commit must be a full lowercase Git SHA")
    validate_repository_path(path)


def build_binding(
    config: dict[str, Any],
    raw: bytes,
    *,
    repository: str,
    commit: str,
    path: str,
) -> dict[str, Any]:
    validate_product_config(config)
    validate_reference(repository, commit, path)
    return {
        "binding_protocol": BINDING_PROTOCOL,
        "block_id": config["block_id"],
        "repository": repository,
        "commit": commit,
        "path": path,
        "config_sha256": hashlib.sha256(raw).hexdigest(),
        "config_protocol": config["protocol_version"],
    }


def binding_hash(binding: dict[str, Any]) -> str:
    return object_hash(binding)


def verify_binding_bytes(
    binding: dict[str, Any], config: dict[str, Any], raw: bytes
) -> dict[str, bool]:
    try:
        if set(binding) != BINDING_FIELDS:
            raise ValueError("configuration binding fields do not match protocol")
        validate_product_config(config)
        validate_reference(
            str(binding["repository"]), str(binding["commit"]), str(binding["path"])
        )
    except (KeyError, TypeError, ValueError):
        return {"binding_structure_valid": False, "valid": False}
    checks = {
        "binding_structure_valid": True,
        "binding_protocol": binding.get("binding_protocol") == BINDING_PROTOCOL,
        "binding_block_matches_config": binding.get("block_id")
        == config.get("block_id"),
        "binding_config_protocol": binding.get("config_protocol")
        == config.get("protocol_version"),
        "binding_config_sha256": binding.get("config_sha256")
        == hashlib.sha256(raw).hexdigest(),
    }
    checks["valid"] = all(checks.values())
    return checks
