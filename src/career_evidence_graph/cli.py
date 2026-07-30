"""Command-line entrypoint for the offline validation tracer."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .codex_cli import CodexCLIConfig, CodexCLIError, run_codex_exec
from .validation.provenance import ProvenanceValidationError, verify_provenance_registry
from .validation.replay import replay_recorded_response
from .validation.store import FormalRunStorageError, FormalRunStore, load_charter


def _json_file(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="career-evidence")
    commands = parser.add_subparsers(dest="command", required=True)

    charter = commands.add_parser("validate-charter")
    charter.add_argument("path")

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-charter":
            charter = load_charter(Path(args.path))
            _emit({"valid": True, "charter_version": charter.charter_version})
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
                raise CodexCLIError("live execution requires CAREER_EVIDENCE_ENABLE_LIVE_MODEL=1")
            workspace = Path(args.workspace)
            prompt_path = Path(args.prompt_file)
            resolved_workspace = workspace.resolve(strict=True)
            if prompt_path.is_symlink():
                raise CodexCLIError("prompt file cannot be a symlink")
            resolved_prompt = prompt_path.resolve(strict=True)
            if not resolved_prompt.is_relative_to(resolved_workspace):
                raise CodexCLIError("prompt file must be inside workspace")
            prompt = resolved_prompt.read_text(encoding="utf-8")
            config = CodexCLIConfig(
                schema_version="codex-cli-config/v1",
                workspace=workspace,
                output_schema=Path(args.output_schema),
                immutable_snapshot=args.model_snapshot,
                drift_limitation_reason=args.drift_limitation,
            )
            result = run_codex_exec(config, prompt)
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
        return 0
    except (
        FormalRunStorageError,
        CodexCLIError,
        ProvenanceValidationError,
        ValidationError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
