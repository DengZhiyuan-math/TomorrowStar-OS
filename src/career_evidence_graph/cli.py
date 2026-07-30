"""Command-line entrypoint for the offline validation tracer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

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
        return 0
    except (
        FormalRunStorageError,
        ProvenanceValidationError,
        ValidationError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
