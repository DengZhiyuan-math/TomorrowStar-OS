"""Command-line entrypoint for the offline validation tracer."""
# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .audit.models import AuditAction
from .audit.store import AuditStorageError, AuditStore
from .audit.workflow import AuditWorkflowError, inspect_contribution, start_audit, transition_audit
from .domain import (
    KNOWN_BAD_CASE_IDS,
    FixtureMutationError,
    FixtureValidationError,
    SealedFixtureRecord,
    SourceScopeError,
    evaluate_review_status,
    load_and_validate_fixture,
    load_candidate_packet,
    load_fixture_mutation_case,
    load_sealed_fixture,
    seal_reviewed_fixture,
    validate_mutation_suite,
    verify_source_manifest,
)
from .validation.provenance import ProvenanceValidationError, verify_provenance_registry
from .validation.replay import replay_recorded_response
from .validation.store import FormalRunStorageError, FormalRunStore, load_charter


def _json_file(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class LiveExecutionError(ValueError):
    """A guarded live-model invocation could not run."""


def _emit(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif isinstance(value, dict):
        value = {
            key: (item.model_dump(mode="json") if hasattr(item, "model_dump") else item)
            for key, item in value.items()
        }
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=lambda item: (
                item.model_dump(mode="json") if hasattr(item, "model_dump") else str(item)
            ),
        )
    )


def _audit_result(snapshot: Any, event_hash: str) -> dict[str, Any]:
    """The sole deterministic presentation for accepted and replayed audit results."""
    return {"event_hash": event_hash, "snapshot": snapshot.model_dump(mode="json")}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="career-evidence")
    commands = parser.add_subparsers(dest="command", required=True)

    charter = commands.add_parser("validate-charter")
    charter.add_argument("path")

    commands.add_parser("implementation-path")

    fixture = commands.add_parser("fixture")
    fixture_commands = fixture.add_subparsers(dest="fixture_command", required=True)
    fixture_validate = fixture_commands.add_parser("validate")
    fixture_validate.add_argument("path")
    fixture_validate_suite = fixture_commands.add_parser("validate-suite")
    fixture_validate_suite.add_argument("--known-good", required=True)
    fixture_validate_suite.add_argument("--known-bad-dir", required=True)
    fixture_seal = fixture_commands.add_parser("seal")
    fixture_seal.add_argument("--workspace", required=True)
    fixture_seal.add_argument("--run-id", required=True)
    fixture_seal.add_argument("--manifest", required=True)
    fixture_seal.add_argument("--candidates", required=True)
    fixture_seal.add_argument("--review", required=True)
    fixture_seal.add_argument("--output", required=True)
    fixture_seal.add_argument("--reissue", action="store_true")
    fixture_source = fixture_commands.add_parser("source")
    fixture_source_commands = fixture_source.add_subparsers(dest="source_command", required=True)
    fixture_source_verify = fixture_source_commands.add_parser("verify")
    fixture_source_verify.add_argument("--manifest", required=True)
    fixture_review_status = fixture_commands.add_parser("review-status")
    fixture_review_status.add_argument("--candidates", required=True)
    fixture_review_status.add_argument("--review", required=True)

    run = commands.add_parser("run")
    run_commands = run.add_subparsers(dest="run_command", required=True)
    create = run_commands.add_parser("create")
    create.add_argument("--workspace", required=True)
    create.add_argument("--charter", required=True)
    create.add_argument("--run-id", required=True)
    create.add_argument("--raw-response", required=True)
    create.add_argument("--proposal", required=True)
    create.add_argument("--confirmed-result", required=True)
    create.add_argument("--lineage", required=True)
    verify = run_commands.add_parser("verify")
    verify.add_argument("--workspace", required=True)
    verify.add_argument("--run-id", required=True)

    replay = commands.add_parser("replay")
    replay.add_argument("--workspace", required=True)
    replay.add_argument("--run-id", required=True)

    provenance = commands.add_parser("provenance")
    provenance_commands = provenance.add_subparsers(dest="provenance_command", required=True)
    provenance_verify = provenance_commands.add_parser("verify")
    provenance_verify.add_argument(
        "registry", nargs="?", default="validation/provenance/registry.json"
    )
    provenance_verify.add_argument("--readme", default="references/README.md")
    provenance_verify.add_argument("--project-root", default=".")

    live_run = commands.add_parser("live-run")
    live_run_commands = live_run.add_subparsers(dest="live_runtime", required=True)
    codex = live_run_commands.add_parser("codex")
    codex.add_argument("--workspace", required=True)
    codex.add_argument("--charter", required=True)
    codex.add_argument("--run-id", required=True)
    codex.add_argument("--prompt-file", required=True)
    codex.add_argument("--output-schema", required=True)
    codex.add_argument("--model-snapshot")
    codex.add_argument(
        "--drift-limitation",
        default="The gpt-5.6-luna alias may drift because no immutable snapshot was exposed.",
    )
    audit = commands.add_parser("audit")
    audit_commands = audit.add_subparsers(dest="audit_command", required=True)
    start = audit_commands.add_parser("start")
    start.add_argument("--workspace", required=True)
    start.add_argument("--fixture", required=True)
    start.add_argument("--manifest", default=None)
    start.add_argument("--contribution-id", required=True)
    start.add_argument("--audit-id")
    start.add_argument("--action-id", required=True)
    for name in ("answer", "skip", "pause", "resume", "review-entry", "review-conclusion"):
        command = audit_commands.add_parser(name)
        command.add_argument("--workspace", required=True)
        command.add_argument("--audit-id", required=True)
        command.add_argument("--action-id", required=True)
        command.add_argument("--expected-event-hash", required=True)
        if name in {"answer", "skip"}:
            command.add_argument("--answer", required=True)
            command.add_argument("--question-id")
        if name == "review-entry":
            command.add_argument("--entry-id", required=True)
            command.add_argument("--decision", choices=("confirm", "edit", "reject"), required=True)
            command.add_argument("--correction")
            command.add_argument("--reason", required=True)
            command.add_argument("--reviewer", required=True)
        if name == "review-conclusion":
            command.add_argument("--decision", choices=("confirm", "reject"), required=True)
            command.add_argument("--reason", required=True)
            command.add_argument("--reviewer", required=True)
        if name in {"review-entry", "review-conclusion"}:
            command.add_argument("--expected-effective-conclusion-hash", required=True)
    inspect = audit_commands.add_parser("inspect")
    inspect.add_argument("--fixture", required=True)
    inspect.add_argument("--manifest", required=True)
    inspect.add_argument("--contribution-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-charter":
            charter = load_charter(Path(args.path))
            _emit({"valid": True, "charter_version": charter.charter_version})
        elif args.command == "implementation-path":
            _emit({"package_path": str(Path(__file__).resolve())})
        elif args.command == "fixture" and args.fixture_command == "validate":
            path = Path(args.path)
            payload = _json_file(args.path)
            if payload.get("schema_version") == "sealed-stoa-known-good/v1":
                _emit(load_sealed_fixture(path, path.parent))
            else:
                _emit(load_and_validate_fixture(path))
        elif args.command == "fixture" and args.fixture_command == "validate-suite":
            known_good_path = Path(args.known_good)
            known_bad_dir = Path(args.known_bad_dir)
            if not known_bad_dir.is_dir():
                raise FixtureMutationError("known-bad directory is missing")
            case_paths = tuple(sorted(known_bad_dir.glob("*.json")))
            if {path.stem for path in case_paths} != KNOWN_BAD_CASE_IDS:
                raise FixtureMutationError(
                    "known-bad case files do not match the required inventory"
                )
            load_sealed_fixture(known_good_path, known_good_path.parent)
            sealed = SealedFixtureRecord.model_validate_json(known_good_path.read_bytes())
            cases = tuple(load_fixture_mutation_case(path) for path in case_paths)
            if {case.case_id for case in cases} != KNOWN_BAD_CASE_IDS:
                raise FixtureMutationError("known-bad case IDs do not match the required inventory")
            result = validate_mutation_suite(sealed, cases)
            if (
                not result.valid
                or result.case_count != len(KNOWN_BAD_CASE_IDS)
                or any(item.actual_codes != (item.expected_code,) for item in result.results)
            ):
                raise FixtureMutationError(
                    "known-bad suite did not produce one matching sole code per case"
                )
            _emit(result)
        elif args.command == "fixture" and args.fixture_command == "seal":
            candidates, review = load_candidate_packet(Path(args.candidates), Path(args.review))
            checkpoint_summary = (
                Path.cwd()
                / ".planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants"
                / "02-04-SUMMARY.md"
            )
            _emit(
                seal_reviewed_fixture(
                    workspace=Path(args.workspace),
                    run_id=args.run_id,
                    manifest_path=Path(args.manifest),
                    candidates=candidates,
                    review=review,
                    checkpoint_summary_bytes=checkpoint_summary.read_bytes(),
                    output_path=Path(args.output),
                    reissue=args.reissue,
                )
            )
        elif (
            args.command == "fixture"
            and args.fixture_command == "source"
            and args.source_command == "verify"
        ):
            _emit(verify_source_manifest(Path(args.manifest)))
        elif args.command == "fixture" and args.fixture_command == "review-status":
            candidates, review = load_candidate_packet(Path(args.candidates), Path(args.review))
            _emit(evaluate_review_status(candidates, review))
        elif args.command == "run" and args.run_command == "create":
            charter = load_charter(Path(args.charter))
            manifest = FormalRunStore(Path(args.workspace)).create(
                run_id=args.run_id,
                charter=charter,
                raw_response=_json_file(args.raw_response),
                proposal=_json_file(args.proposal),
                confirmed_result=_json_file(args.confirmed_result),
                lineage_inputs=_json_file(args.lineage),
            )
            _emit(manifest)
        elif args.command == "run" and args.run_command == "verify":
            _emit(FormalRunStore(Path(args.workspace)).verify(args.run_id))
        elif args.command == "replay":
            result = replay_recorded_response(FormalRunStore(Path(args.workspace)), args.run_id)
            _emit(result)
            return 0 if result.matched else 1
        elif args.command == "provenance" and args.provenance_command == "verify":
            registry = verify_provenance_registry(
                Path(args.registry),
                Path(args.readme),
                Path(args.project_root),
            )
            _emit({"valid": True, "record_count": len(registry.records)})
        elif args.command == "live-run" and args.live_runtime == "codex":
            if os.environ.get("CAREER_EVIDENCE_ENABLE_LIVE_MODEL") != "1":
                raise LiveExecutionError(
                    "live execution requires CAREER_EVIDENCE_ENABLE_LIVE_MODEL=1"
                )
            workspace = Path(args.workspace)
            prompt_path = Path(args.prompt_file)
            resolved_workspace = workspace.resolve(strict=True)
            if prompt_path.is_symlink():
                raise LiveExecutionError("prompt file cannot be a symlink")
            resolved_prompt = prompt_path.resolve(strict=True)
            if not resolved_prompt.is_relative_to(resolved_workspace):
                raise LiveExecutionError("prompt file must be inside workspace")
            prompt = resolved_prompt.read_text(encoding="utf-8")
            from .codex_cli import CodexCLIConfig, CodexCLIError, run_codex_exec

            config = CodexCLIConfig(
                schema_version="codex-cli-config/v1",
                workspace=workspace,
                output_schema=Path(args.output_schema),
                immutable_snapshot=args.model_snapshot,
                drift_limitation_reason=args.drift_limitation,
            )
            try:
                result = run_codex_exec(config, prompt)
            except CodexCLIError as exc:
                raise LiveExecutionError(str(exc)) from exc
            charter = load_charter(Path(args.charter))
            raw_response = {
                "raw_jsonl": result.raw_stdout_jsonl,
                "result": result.structured_result,
            }
            manifest = FormalRunStore(workspace).create(
                run_id=args.run_id,
                charter=charter,
                raw_response=raw_response,
                proposal=result.structured_result,
                confirmed_result=result.structured_result,
                lineage_inputs={
                    "fixture": {"kind": "live-technical-gate-only"},
                    "artifacts": [],
                    "prompt": {"hash": result.prompt_hash},
                    "model": result.model_identity.model_dump(mode="json"),
                    "configuration": result.requested_configuration,
                    "policy": {"charter": charter.charter_version},
                    "reviewer": {"kind": "unconfirmed-technical-gate"},
                },
                execution_mode="live-reexecution",
                limitations=[
                    "This run proves runtime/configuration viability only.",
                    *(
                        [result.model_drift_limitation.reason]
                        if result.model_drift_limitation
                        else []
                    ),
                ],
                codex_cli_result=result,
                model_identity=result.model_identity,
                model_drift_limitation=result.model_drift_limitation,
            )
            _emit(manifest)
        elif args.command == "audit" and args.audit_command == "start":
            manifest = (
                Path(args.manifest)
                if args.manifest
                else Path(args.fixture).with_name("source-manifest.json")
            )
            created = start_audit(
                workspace=Path(args.workspace),
                fixture_path=Path(args.fixture),
                manifest_path=manifest,
                contribution_id=args.contribution_id,
                audit_id=args.audit_id,
                action_id=args.action_id,
            )
            _emit(
                {
                    "audit_id": created.audit_id,
                    "question": created.questions[0],
                    "status": created.status,
                    "event_hash": AuditStore(Path(args.workspace)).latest_event_hash(
                        created.audit_id
                    ),
                }
            )
        elif args.command == "audit" and args.audit_command == "inspect":
            facts, limitations = inspect_contribution(
                Path(args.fixture), Path(args.manifest), args.contribution_id
            )
            _emit({"facts": facts, "limitations": limitations})
        elif args.command == "audit":
            store = AuditStore(Path(args.workspace))
            payload = {"action": args.audit_command}
            for field in (
                "answer",
                "question_id",
                "entry_id",
                "decision",
                "correction",
                "reason",
            ):
                if hasattr(args, field):
                    payload[field] = getattr(args, field)
            if hasattr(args, "reviewer"):
                payload["reviewer_id"] = args.reviewer
            if hasattr(args, "expected_event_hash"):
                payload["expected_event_hash"] = args.expected_event_hash
            if hasattr(args, "expected_effective_conclusion_hash"):
                payload["expected_effective_conclusion_hash"] = (
                    args.expected_effective_conclusion_hash
                )
            payload["action_id"] = args.action_id
            try:
                action = AuditAction.model_validate(payload)
            except ValidationError as exc:
                _emit_error(
                    {
                        "valid": False,
                        "error": "invalid_audit_action",
                        "message": str(exc),
                    }
                )
                return 2
            updated, _replayed = store.transact(
                args.audit_id, action, lambda current: transition_audit(store, current, action)
            )
            _emit(_audit_result(updated, store.latest_event_hash(args.audit_id)))
        return 0
    except AuditWorkflowError as exc:
        _emit_error({"valid": False, "error": "audit_workflow_error", "message": str(exc)})
        return 2
    except FixtureValidationError as exc:
        _emit_error(
            {
                "valid": False,
                "violations": [
                    violation.model_dump(exclude={"schema_version"}) for violation in exc.violations
                ],
            }
        )
        return 2
    except (
        FixtureMutationError,
        AuditStorageError,
        FormalRunStorageError,
        LiveExecutionError,
        ProvenanceValidationError,
        SourceScopeError,
        ValidationError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _emit_error(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
