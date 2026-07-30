"""Immutable filesystem storage for narrow offline formal-run bundles."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .hashing import canonical_json_bytes, sha256_digest
from .models import (
    CodexCLIResult,
    CorrectionRecord,
    FormalRunManifest,
    ModelDriftLimitation,
    ModelIdentity,
    ValidationCharter,
)

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REQUIRED_INPUTS = (
    "fixture",
    "artifacts",
    "prompt",
    "model",
    "configuration",
    "policy",
    "reviewer",
)
BASE_PAYLOAD_FILES = (
    "raw_response.json",
    "original_proposal.json",
    "corrections.json",
    "confirmed_result.json",
)


class FormalRunStorageError(RuntimeError):
    """Raised when a formal bundle cannot be safely created or verified."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalRunStorageError(f"cannot read valid JSON from {path.name}") from exc


def load_charter(path: Path) -> ValidationCharter:
    """Load a charter using its strict schema."""
    try:
        return ValidationCharter.model_validate(_load_json(path.resolve(strict=True)))
    except (OSError, ValidationError) as exc:
        raise FormalRunStorageError("invalid validation charter") from exc


class FormalRunStore:
    """Create and verify bundles under one resolved workspace boundary."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.runs_root = self.workspace / "formal-runs"

    def _run_path(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise FormalRunStorageError("run_id contains unsafe path characters")
        candidate = self.runs_root / run_id
        if candidate.parent.resolve() != self.runs_root.resolve():
            raise FormalRunStorageError("run destination escapes the formal-runs root")
        return candidate

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        data = canonical_json_bytes(value) + b"\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    def create(
        self,
        *,
        run_id: str,
        charter: ValidationCharter,
        raw_response: Any,
        proposal: Any,
        confirmed_result: Any,
        lineage_inputs: dict[str, Any],
        corrections: list[CorrectionRecord] | None = None,
        execution_mode: str = "recorded-response",
        limitations: list[str] | None = None,
        parent_run_id: str | None = None,
        change_reason: str | None = None,
        diff: Any | None = None,
        codex_cli_result: CodexCLIResult | None = None,
        model_identity: ModelIdentity | None = None,
        model_drift_limitation: ModelDriftLimitation | None = None,
    ) -> FormalRunManifest:
        """Atomically publish a new immutable formal bundle."""
        destination = self._run_path(run_id)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FormalRunStorageError(f"formal run already exists: {run_id}")
        if set(lineage_inputs) != set(REQUIRED_INPUTS):
            raise FormalRunStorageError("lineage inputs must contain the exact required keys")
        if parent_run_id is not None:
            self.verify(parent_run_id)
            if not change_reason or not change_reason.strip():
                raise FormalRunStorageError("linked rerun requires a non-empty change reason")
            if diff is None:
                raise FormalRunStorageError("linked rerun requires an explicit diff")
        elif change_reason is not None or diff is not None:
            raise FormalRunStorageError("change reason and diff require a parent run")
        if execution_mode == "live-reexecution":
            if codex_cli_result is None or model_identity is None:
                raise FormalRunStorageError(
                    "live formal runs require successful Codex metadata and model identity"
                )
            if codex_cli_result.exit_code != 0 or codex_cli_result.structured_result is None:
                raise FormalRunStorageError("unsuccessful Codex result cannot become formal")
            if not codex_cli_result.raw_stdout_jsonl:
                raise FormalRunStorageError("live formal runs must retain raw JSONL")
            if codex_cli_result.model_identity != model_identity:
                raise FormalRunStorageError("Codex and manifest model identities disagree")
            if codex_cli_result.model_drift_limitation != model_drift_limitation:
                raise FormalRunStorageError("Codex and manifest drift limitations disagree")
            if not isinstance(raw_response, dict):
                raise FormalRunStorageError("live raw response must be a structured envelope")
            if raw_response.get("raw_jsonl") != codex_cli_result.raw_stdout_jsonl:
                raise FormalRunStorageError("live raw JSONL does not match Codex metadata")
            if canonical_json_bytes(raw_response.get("result")) != canonical_json_bytes(
                codex_cli_result.structured_result
            ):
                raise FormalRunStorageError("live structured result does not match Codex metadata")
            if model_identity.resolved_snapshot is None and model_drift_limitation is None:
                raise FormalRunStorageError(
                    "alias-based live formal runs require a drift limitation"
                )
        elif (
            codex_cli_result is not None
            or model_identity is not None
            or model_drift_limitation is not None
        ):
            raise FormalRunStorageError("recorded-response runs cannot include live Codex metadata")

        temporary = Path(tempfile.mkdtemp(dir=self.runs_root, prefix=f".{run_id}."))
        try:
            correction_values = corrections or []
            proposal_hash = sha256_digest(canonical_json_bytes(proposal))
            for correction in correction_values:
                if correction.original_proposal_hash != proposal_hash:
                    raise FormalRunStorageError(
                        "correction does not reference the immutable original proposal"
                    )
                if canonical_json_bytes(correction.original_proposal) != canonical_json_bytes(
                    proposal
                ):
                    raise FormalRunStorageError(
                        "correction must retain the complete original proposal"
                    )
            values = {
                "raw_response.json": raw_response,
                "original_proposal.json": proposal,
                "corrections.json": [
                    correction.model_dump(mode="json") for correction in correction_values
                ],
                "confirmed_result.json": confirmed_result,
            }
            if diff is not None:
                values["diff.json"] = diff
            if codex_cli_result is not None:
                values["codex_cli_result.json"] = codex_cli_result.model_dump(mode="json")
            manifest_hashes: dict[str, str] = {}
            for filename, value in values.items():
                self._write_json(temporary / filename, value)
                manifest_hashes[filename] = sha256_digest((temporary / filename).read_bytes())
            manifest = FormalRunManifest(
                schema_version="formal-run/v1",
                run_id=run_id,
                run_kind="formal",
                execution_mode=execution_mode,
                created_at=datetime.now(UTC),
                charter_version=charter.charter_version,
                input_hashes={
                    key: sha256_digest(canonical_json_bytes(value))
                    for key, value in lineage_inputs.items()
                },
                content_manifest=manifest_hashes,
                parent_run_id=parent_run_id,
                change_reason=change_reason,
                limitations=limitations or [],
                model_identity=model_identity,
                model_drift_limitation=model_drift_limitation,
                replay_mode="exact-recorded-response",
            )
            self._write_json(temporary / "manifest.json", manifest)
            try:
                os.rename(temporary, destination)
            except FileExistsError as exc:
                raise FormalRunStorageError(f"formal run already exists: {run_id}") from exc
            return manifest
        finally:
            if temporary.exists():
                for child in temporary.iterdir():
                    child.unlink()
                temporary.rmdir()

    def create_linked_rerun(
        self,
        *,
        parent_run_id: str,
        run_id: str,
        change_reason: str,
        diff: Any,
        charter: ValidationCharter,
        raw_response: Any,
        proposal: Any,
        confirmed_result: Any,
        lineage_inputs: dict[str, Any],
        corrections: list[CorrectionRecord] | None = None,
        execution_mode: str = "recorded-response",
        limitations: list[str] | None = None,
    ) -> FormalRunManifest:
        """Create a new bundle linked to a verified, untouched parent."""
        return self.create(
            run_id=run_id,
            charter=charter,
            raw_response=raw_response,
            proposal=proposal,
            confirmed_result=confirmed_result,
            lineage_inputs=lineage_inputs,
            corrections=corrections,
            execution_mode=execution_mode,
            limitations=limitations,
            parent_run_id=parent_run_id,
            change_reason=change_reason,
            diff=diff,
        )

    def verify(self, run_id: str) -> FormalRunManifest:
        """Fail closed unless the complete bundle and its ancestry remain valid."""
        return self._verify(run_id, ancestry=frozenset())

    def _verify(self, run_id: str, *, ancestry: frozenset[str]) -> FormalRunManifest:
        if run_id in ancestry:
            raise FormalRunStorageError("formal run lineage contains a cycle")
        run_path = self._run_path(run_id)
        if run_path.is_symlink() or not run_path.is_dir():
            raise FormalRunStorageError(f"formal run does not exist safely: {run_id}")
        resolved_run_path = run_path.resolve()
        if resolved_run_path.parent != self.runs_root.resolve():
            raise FormalRunStorageError("formal run resolves outside its workspace")
        try:
            manifest = FormalRunManifest.model_validate(_load_json(run_path / "manifest.json"))
        except ValidationError as exc:
            raise FormalRunStorageError("formal run manifest is invalid") from exc
        if manifest.run_id != run_id:
            raise FormalRunStorageError("manifest run_id does not match its directory")
        expected_files = set(BASE_PAYLOAD_FILES)
        if manifest.parent_run_id is not None:
            expected_files.add("diff.json")
        if manifest.execution_mode == "live-reexecution":
            expected_files.add("codex_cli_result.json")
        if set(manifest.content_manifest) != expected_files:
            raise FormalRunStorageError("manifest does not declare the exact payload set")
        actual_files = {entry.name for entry in run_path.iterdir()}
        if actual_files != expected_files | {"manifest.json"}:
            raise FormalRunStorageError("formal run contains missing or undeclared files")
        for filename, expected_hash in manifest.content_manifest.items():
            source_path = run_path / filename
            if source_path.is_symlink():
                raise FormalRunStorageError("payload path escapes or aliases the run directory")
            try:
                payload_path = source_path.resolve(strict=True)
            except OSError as exc:
                raise FormalRunStorageError(f"declared payload is missing: {filename}") from exc
            if payload_path.parent != resolved_run_path:
                raise FormalRunStorageError("payload path escapes or aliases the run directory")
            if sha256_digest(payload_path.read_bytes()) != expected_hash:
                raise FormalRunStorageError(f"payload hash mismatch: {filename}")
        try:
            corrections = [
                CorrectionRecord.model_validate(value)
                for value in _load_json(run_path / "corrections.json")
            ]
        except (TypeError, ValidationError) as exc:
            raise FormalRunStorageError("correction history is invalid") from exc
        proposal = _load_json(run_path / "original_proposal.json")
        proposal_hash = sha256_digest(canonical_json_bytes(proposal))
        for correction in corrections:
            if correction.original_proposal_hash != proposal_hash:
                raise FormalRunStorageError("correction proposal hash does not match")
            if canonical_json_bytes(correction.original_proposal) != canonical_json_bytes(proposal):
                raise FormalRunStorageError("correction does not preserve the original proposal")
        if manifest.execution_mode == "live-reexecution":
            try:
                codex_result = CodexCLIResult.model_validate(
                    _load_json(run_path / "codex_cli_result.json")
                )
            except ValidationError as exc:
                raise FormalRunStorageError("stored Codex metadata is invalid") from exc
            if codex_result.model_identity != manifest.model_identity:
                raise FormalRunStorageError("stored Codex model identity does not match manifest")
            if codex_result.model_drift_limitation != manifest.model_drift_limitation:
                raise FormalRunStorageError("stored Codex drift limitation does not match manifest")
            raw_response = _load_json(run_path / "raw_response.json")
            if (
                not isinstance(raw_response, dict)
                or raw_response.get("raw_jsonl") != codex_result.raw_stdout_jsonl
                or canonical_json_bytes(raw_response.get("result"))
                != canonical_json_bytes(codex_result.structured_result)
            ):
                raise FormalRunStorageError("stored Codex raw response does not match metadata")
        if manifest.parent_run_id is not None:
            self._verify(
                manifest.parent_run_id,
                ancestry=ancestry | {run_id},
            )
        return manifest

    def payload(self, run_id: str, filename: str) -> Any:
        """Return a verified declared payload."""
        manifest = self.verify(run_id)
        if filename not in manifest.content_manifest:
            raise FormalRunStorageError("undeclared payload requested")
        return _load_json(self._run_path(run_id) / filename)
