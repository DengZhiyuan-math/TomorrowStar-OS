"""Canonical serialization and content identity helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for JSON-compatible data."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_digest(value: bytes) -> str:
    """Return a prefixed SHA-256 digest."""
    return f"sha256:{hashlib.sha256(value).hexdigest()}"
