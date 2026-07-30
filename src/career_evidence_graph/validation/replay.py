"""Exact replay from recorded output only."""

from __future__ import annotations

from .hashing import canonical_json_bytes, sha256_digest
from .models import ReplayResult
from .store import FormalRunStorageError, FormalRunStore


def replay_recorded_response(store: FormalRunStore, run_id: str) -> ReplayResult:
    """Compare the stored response result with the stored confirmed expectation."""
    raw_response = store.payload(run_id, "raw_response.json")
    expected = store.payload(run_id, "expected_result.json")
    if not isinstance(raw_response, dict) or "result" not in raw_response:
        raise FormalRunStorageError("recorded raw response has no structured result")
    actual = raw_response["result"]
    expected_hash = sha256_digest(canonical_json_bytes(expected))
    actual_hash = sha256_digest(canonical_json_bytes(actual))
    return ReplayResult(
        schema_version="replay-result/v1",
        run_id=run_id,
        matched=expected_hash == actual_hash,
        expected_hash=expected_hash,
        actual_hash=actual_hash,
    )
