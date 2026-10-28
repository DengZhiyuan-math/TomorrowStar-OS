"""Opt-in synthetic model trials. Private career sources are never loaded."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import Field  # noqa: E402

from career_evidence_graph.audit.decision import (  # noqa: E402
    BOUNDARY_INSTRUCTION,
    INTERVIEW_INSTRUCTION,
    validate_project_interview_plan,
)
from career_evidence_graph.audit.models import ArtifactFact, ProjectInterviewPlan  # noqa: E402
from career_evidence_graph.codex_cli import CodexCLIError, run_codex_exec  # noqa: E402
from career_evidence_graph.domain.models import MASTERY_ANCHORS  # noqa: E402
from career_evidence_graph.interview_calibration import (  # noqa: E402
    CalibrationCase,
    CalibrationObservation,
    evaluate_calibration,
)
from career_evidence_graph.validation.hashing import sha256_digest  # noqa: E402
from career_evidence_graph.validation.models import CodexCLIConfig, StrictModel  # noqa: E402
from career_evidence_graph.validation.store import create_only_file_bundle  # noqa: E402


class ObservationBatch(StrictModel):
    observations: tuple[CalibrationObservation, ...] = Field(min_length=1)


def strict_output_schema(model):
    schema = model.model_json_schema()

    def visit(value):
        if isinstance(value, dict):
            if value.get("type") == "object" and "properties" in value:
                value["required"] = list(value["properties"])
            value.pop("default", None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    if model is ProjectInterviewPlan:
        criteria = schema["$defs"]["ProbeArea"]["properties"]["evaluation_criteria"]
        criteria.pop("propertyNames", None)
        array = criteria.pop("additionalProperties")
        criteria.update(
            properties={d: array for d in ("hard", "intermediate", "simple")},
            required=["hard", "intermediate", "simple"],
            additionalProperties=False,
        )
    return schema


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    corpus_bytes = (root / "validation/calibration/interview-v2/corpus.json").read_bytes()
    corpus = json.loads(corpus_bytes)
    if corpus["authority"] != "synthetic-only":
        raise ValueError("synthetic trial only")
    cases = tuple(CalibrationCase.model_validate(c) for c in corpus["cases"])
    args.output.mkdir(parents=True, exist_ok=False)
    subprocess.run(["git", "init", "--quiet", str(args.output)], check=True)
    files = {"corpus.json": corpus_bytes, "runner.py": Path(__file__).read_bytes()}
    batches = []
    generation_errors = []
    try:
        for stage, model, instruction, payload in (
            (
                "generation",
                ProjectInterviewPlan,
                INTERVIEW_INSTRUCTION,
                {
                    "experience_id": corpus["generation"]["experience_id"],
                    "facts_by_contribution": {
                        corpus["generation"]["contribution_id"]: [corpus["generation"]["fact"]]
                    },
                    "context_notes": [
                        "Design is user-attributed. Implementation is agent-assisted. "
                        "Do not ask historical facts. Use exactly one technical-design area "
                        "in each depth and transfer plan."
                    ],
                    "prior_answers": [],
                },
            ),
            (
                "evaluation",
                ObservationBatch,
                BOUNDARY_INSTRUCTION
                + "\nReturn one observation per case. Route context requests without evaluating "
                "a capability boundary. Route attribution only when ownership is denied or needs "
                "clarification. A clear user design contribution with agent-assisted execution "
                "remains a capability answer. For attribution route, return a BoundaryDecision "
                "with outcome attribution-signal and both capability fields null. This is a "
                "workflow routing signal, not negative capability evidence. Use inspected context "
                "to judge attribution. Report a "
                "supported mastery anchor only if the supplied observations establish performed "
                "practical capability at that exact accepted anchor. Overview fluency, a "
                "hypothetical transfer answer, and isolated design explanation do not establish "
                "practical task completion. Use null when no anchor is established. No exact "
                "numeric score or confidence value is authorized. Retain alternative sound "
                "explanations and agent-assisted design understanding.\n",
                {
                    "cases": [
                        {
                            k: v
                            for k, v in c.model_dump(mode="json").items()
                            if not k.startswith("expected_")
                        }
                        for c in cases
                    ],
                    "accepted_anchors": [a.model_dump(mode="json") for a in MASTERY_ANCHORS],
                },
            ),
        ):
            schema_path = args.output / f"{stage}.schema.json"
            schema = strict_output_schema(model)
            if stage == "generation":
                # Native constraints bind identity; the domain validator still rechecks it.
                schema["properties"]["experience_id"]["enum"] = [payload["experience_id"]]
                schema["$defs"]["ProbePlan"]["properties"]["contribution_id"]["enum"] = [
                    corpus["generation"]["contribution_id"]
                ]
                schema["$defs"]["ProbeArea"]["properties"]["inspected_fact_ids"]["items"][
                    "enum"
                ] = [corpus["generation"]["fact"]["evidence_id"]]
                schema["$defs"]["AuditQuestion"]["properties"]["inspection_reference"] = {
                    "type": "string",
                    "enum": [corpus["generation"]["fact"]["source_locator"]],
                }
            schema_path.write_text(json.dumps(schema))
            files[schema_path.name] = schema_path.read_bytes()
            config = CodexCLIConfig(
                schema_version="codex-cli-config/v1",
                workspace=args.output,
                output_schema=schema_path,
                drift_limitation_reason=(
                    "Alias identity can drift; each raw response and exact "
                    "configuration are retained."
                ),
            )
            prompt = (
                instruction
                + "\nUse supplied data only. Do not use tools. Return the required JSON.\n"
                + json.dumps(payload, ensure_ascii=False)
            )
            files[f"{stage}.prompt.txt"] = prompt.encode()
            for attempt in range(1, 4):
                result = run_codex_exec(config, prompt, timeout_seconds=240)
                files[f"{stage}-{attempt}.json"] = result.model_dump_json(indent=2).encode() + b"\n"
                if stage == "generation":
                    try:
                        validate_project_interview_plan(
                            model.model_validate(result.structured_result),
                            experience_id=payload["experience_id"],
                            facts_by_contribution={
                                corpus["generation"]["contribution_id"]: (
                                    ArtifactFact.model_validate(corpus["generation"]["fact"]),
                                )
                            },
                        )
                    except ValueError as exc:
                        generation_errors.append({"attempt": attempt, "reason": str(exc)})
                        print(f"{stage} attempt {attempt}: rejected and retained", flush=True)
                        continue
                else:
                    parsed = model.model_validate(result.structured_result)
                    batches.append(parsed.observations)
                print(f"{stage} attempt {attempt}: validated", flush=True)
        report = evaluate_calibration(cases, tuple(batches))
        report.update(
            corpus_hash=sha256_digest(corpus_bytes),
            generation_attempts=3,
            generation_errors=generation_errors,
            question_semantic_review="required on retained plans",
            real_user_expert_calibration="pending",
        )
        report["passed"] = report["passed"] and not generation_errors
        files["report.json"] = json.dumps(report, ensure_ascii=False, indent=2).encode() + b"\n"
    except Exception as exc:
        if isinstance(exc, CodexCLIError):
            files["failed-call.stdout.jsonl"] = exc.raw_stdout_jsonl.encode()
            files["failed-call.stderr.txt"] = exc.redacted_stderr.encode()
        files["failure.json"] = json.dumps(
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "reason": str(exc),
                "corpus_hash": sha256_digest(corpus_bytes),
            },
            ensure_ascii=False,
        ).encode()
        create_only_file_bundle(args.output, "evidence", files)
        print("trial failed; exact completed evidence retained", flush=True)
        return 2
    create_only_file_bundle(args.output, "evidence", files)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "critical_failure_count": report["critical_failure_count"],
                "personal_scoring_authorized": False,
            }
        ),
        flush=True,
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
