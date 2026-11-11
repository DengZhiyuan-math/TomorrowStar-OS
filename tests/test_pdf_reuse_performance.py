"""Opt-in offline rendering benchmark; no real-model performance acceptance."""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_application_match import model_output, model_runner

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_full_latex import generate_full_latex
from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_pdf_reuse import read_reuse, try_reuse, verify_reuse
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import ApplicationResumeStore, career_source_snapshot
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog
from career_evidence_graph.codex_cli import run_codex_exec

pytestmark = pytest.mark.skipif(
    os.environ.get("TOMORROWSTAR_RENDER_REUSE_BENCHMARK") != "1",
    reason="Explicit opt-in for actual connected LaTeX compilation; semantic model remains offline",
)


def _run_pairs(tmp_path):
    """Preserve baseline caches; report actual LaTeX compiler cost separately from model latency."""
    application_root, career = tmp_path / "applications", tmp_path / "career"
    application_root.mkdir()
    (career / "contributions").mkdir(parents=True)
    (career / "contributions/python.md").write_text(
        "# Synthetic Python service\n\n## Scope\nImplemented a Python service.\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n\n## Boundaries\nNo GPU training claim.\n"
    )
    (career / "sources").mkdir()
    (career / "sources/profile.json").write_text(
        json.dumps({"name": "Synthetic Applicant", "title": "Python Engineer"})
    )
    applications, catalog = ApplicationStore(application_root), CareerCatalog(career)
    snapshot = career_source_snapshot(catalog)
    store = ApplicationResumeStore(applications, catalog, tmp_path / "resumes")
    project = tmp_path / "latex-template"
    project.mkdir()
    (project / "main.tex").write_text(
        "\\documentclass[a4paper]{article}\n\\begin{document}\n"
        "Synthetic Applicant\n\\section*{Python service}\n"
        "Implemented a Python service.\n\\end{document}\n"
    )
    binding = source_snapshot(project, "main.tex")
    identity = snapshot["profile_source"]["id"] + ":profile.identity"
    contribution = snapshot["items"][0]["source_id"]

    def literal_model(*_args, **_kwargs):
        output = {
            "groups": [
                {
                    "title": "Identity",
                    "start_line": 1,
                    "end_line": 1,
                    "source_ids": [identity],
                    "latex": "Synthetic Applicant\n",
                    "disposition": "include",
                    "reason": "Synthetic literal identity",
                },
                {
                    "title": "Python service",
                    "start_line": 2,
                    "end_line": 3,
                    "source_ids": [contribution],
                    "latex": "\\section*{Python service}\nImplemented a Python service.\n",
                    "disposition": "include",
                    "reason": "Synthetic literal contribution",
                },
            ],
            "limitations": [],
        }
        return SimpleNamespace(
            structured_result=output, model_dump=lambda **_kwargs: {"synthetic": True}
        )

    if os.environ.get("TOMORROWSTAR_REUSE_BENCHMARK_LIVE") != "1":
        store.model_runner = literal_model
    inputs = {"sources_revision": snapshot["revision"]}

    def generate_pdf(job, analysis):
        draft = generate_full_latex(
            store,
            job["id"],
            job["revision"],
            source_snapshot=snapshot,
            analysis=analysis,
            task_inputs=inputs,
            latex_base=binding,
        )
        return store.export_for_draft(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            export_id=uuid4().hex,
            prism={
                key: value
                for key, value in draft["source_checkpoint"].items()
                if key != "archive_sha256"
            },
            automatic_materials=True,
        )

    seed_job = applications.create_application(
        {
            "company": "Synthetic Original",
            "role_title": "Python Engineer",
            "job_description": (
                "Implement reliable Python services for backend software development."
            ),
        }
    )
    seed_analysis = analyze_job(
        seed_job,
        snapshot,
        tmp_path / "analysis-seed",
        runner=model_runner(model_output(snapshot), []),
    )
    seed = generate_pdf(seed_job, seed_analysis)
    seed_raw = store.pdf(seed["id"])
    sha = hashlib.sha256(seed_raw).hexdigest()
    groups = {
        "draft_id": "d" * 32,
        "draft_sha256": "d" * 64,
        "input_revision": digest(inputs),
        "source_revision": "e" * 64,
        "preview_id": "f" * 32,
    }
    groups["revision"] = digest(groups)
    source = {
        "id": "synthetic-history",
        "application_id": "synthetic-old-job",
        "application_revision": "origin-v1",
        "origin": "generated_latex",
        "factual_review": "groups_reviewed",
        "draft_id": "d" * 32,
        "draft_sha256": "d" * 64,
        "prism": {"source_revision": "e" * 64},
        "job_description": ("Implement reliable Python services for backend software development."),
        "inputs": inputs,
        "materials_confirmed": True,
        "status": "materials_ready",
        "resume_id": seed["id"],
        "resume_sha256": sha,
        "material_reviews": [
            {
                "id": "b" * 32,
                "at": 1.0,
                "actor": "user",
                "scope": "current_pdf_materials",
                "draft_id": "d" * 32,
                "draft_sha256": "d" * 64,
                "source_revision": "e" * 64,
                "group_review_revision": groups["revision"],
                "preview_id": "f" * 32,
                "resume_id": seed["id"],
                "pdf_sha256": sha,
                "input_revision": digest(inputs),
                "reviewed": ["complete_pdf_content", "pdf_layout", "full_source_consistency"],
            }
        ],
        "artifacts": [
            {
                "stage": "export",
                "adopted": True,
                "result": {
                    "id": seed["id"],
                    "pdf_sha256": sha,
                    "draft_id": "d" * 32,
                    "draft_sha256": "d" * 64,
                    "group_review": groups,
                    "application_id": "synthetic-old-job",
                    "revision": "origin-v1",
                    "task_inputs": inputs,
                    "prism_source_revision": "e" * 64,
                },
            }
        ],
    }
    manifest = {
        "status": "complete",
        "application_id": "synthetic-old-job",
        "application_revision": "origin-v1",
        "prism": {"source_revision": "e" * 64},
        "id": seed["id"],
        "draft_id": "d" * 32,
        "draft_sha256": "d" * 64,
        "task_inputs": inputs,
        "pdf_sha256": sha,
        "group_review": groups,
    }
    manifest_path = store.root / seed["id"] / "export.json"
    helper.atomic_write_json(manifest_path, manifest)
    source["artifacts"][0]["result"]["export_manifest_sha256"] = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    live = os.environ.get("TOMORROWSTAR_REUSE_BENCHMARK_LIVE") == "1"
    pair_count = int(os.environ.get("TOMORROWSTAR_REUSE_BENCHMARK_PAIRS", "3"))
    assert 1 <= pair_count <= 5
    rows = []
    semantic_observations = []
    for pair in range(pair_count):
        job = applications.create_application(
            {
                "company": f"Synthetic {pair}",
                "role_title": "Python Engineer",
                "job_description": (
                    "Implement reliable Python services for backend software development."
                ),
            }
        )
        analysis = analyze_job(
            job,
            snapshot,
            tmp_path / f"analysis-{pair}",
            runner=model_runner(model_output(snapshot), []),
        )
        started = time.perf_counter_ns()
        cold = generate_pdf(job, analysis)
        assert store.pdf(cold["id"]).startswith(b"%PDF-")
        cold_ms = (time.perf_counter_ns() - started) / 1e6
        started = time.perf_counter_ns()
        warm = store.read_export(cold["id"])
        assert warm["id"] == cold["id"]
        assert store.pdf(warm["id"]).startswith(b"%PDF-")
        warm_ms = (time.perf_counter_ns() - started) / 1e6
        target = {
            "id": f"synthetic-target-{pair}",
            "application_id": job["id"],
            "inputs": inputs,
            "job_description": job["job_description"],
            "input_epoch": 0,
            "analysis_id": analysis["id"],
        }
        outputs = iter(
            [
                {
                    "profiles": [
                        {
                            "id": source["id"],
                            "content": "Build Python services",
                            "core_work_confirmed": True,
                            "locators": ["Implement reliable Python"],
                        }
                    ],
                    "task_ids": [source["id"]],
                },
                {
                    "approved": True,
                    "source_task_id": source["id"],
                    "reason": "Synthetic deterministic acceptance of original PDF.",
                },
            ]
        )

        def runner(*_args, _outputs=outputs, _pair=pair, **_kwargs):
            output = next(_outputs)
            # Cached historical profiles omit the first call on later pairs.
            if "profiles" in output and (store.root / ".pdf-reuse-index").is_dir() and _pair:
                output = next(_outputs)
            return SimpleNamespace(structured_result=output)

        def live_runner(config, prompt, **kwargs):
            title = json.loads(config.output_schema.read_text()).get("title", "unknown")
            stage = {
                "_Retrieval": "retrieval",
                "_Suitability": "suitability",
            }.get(title, title)
            observation = {"stage": stage}
            observed_start = time.perf_counter_ns()
            deadline = time.monotonic() + kwargs["timeout_seconds"]

            def bounded_process(*args, **options):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(args[0] if args else "codex", 0)
                options["timeout"] = min(options.get("timeout", remaining), remaining)
                return subprocess.run(*args, **options)

            try:
                outcome = run_codex_exec(config, prompt, runner=bounded_process, **kwargs)
                payload = outcome.structured_result
                if isinstance(payload, dict):
                    for key in ("approved", "source_task_id", "reason", "task_ids", "profiles"):
                        if key in payload:
                            observation[key] = payload[key]
                observation["status"] = "complete"
                return outcome
            except Exception as error:
                observation.update(status="failed", error_type=type(error).__name__)
                raise
            finally:
                observation["elapsed_ms"] = (time.perf_counter_ns() - observed_start) / 1e6
                semantic_observations.append(observation)

        observation_start = len(semantic_observations)
        started = time.perf_counter_ns()
        result = try_reuse(
            store, target, snapshot, analysis, [source], runner=live_runner if live else runner
        )
        reuse_hit = result is not None
        if reuse_hit:
            verify_reuse(store, target, result, [source])
            assert read_reuse(store, result) == seed_raw
        else:
            fallback = store.read_export(cold["id"])
            assert store.pdf(fallback["id"]).startswith(b"%PDF-")
        reuse_ms = (time.perf_counter_ns() - started) / 1e6
        rows.append(
            {
                "pair": pair + 1,
                "cold_ms": cold_ms,
                "warm_manifest_read_ms": warm_ms,
                "reuse_ms": reuse_ms,
                "reuse_hit": reuse_hit,
                "miss_fallback_uses_preserved_baseline_cache": not reuse_hit,
                "semantic_calls": semantic_observations[observation_start:],
                "semantic_call_count": len(semantic_observations) - observation_start,
                "failure_stage": next(
                    (
                        row["stage"]
                        for row in semantic_observations[observation_start:]
                        if row["status"] == "failed"
                    ),
                    None,
                ),
            }
        )
    report = {
        "scope": "LaTeX generation/compile versus immutable export read and standalone reuse",
        "model": "configured live models"
        if live
        else "deterministic outputs; no real-model latency",
        "acceptance": "synthetic receipt; no real acceptance or confirmation measurement",
        "cache_policy": "new target per pair; same-job immutable export read measured separately",
        "pairs": rows,
        "production_speed_accepted": False,
    }
    return report


def test_offline_cold_warm_and_reuse_rendering_pairs(tmp_path):
    output_path = os.environ.get("TOMORROWSTAR_REUSE_BENCHMARK_OUTPUT")
    report = {"status": "started", "production_speed_accepted": False}
    try:
        report = _run_pairs(tmp_path) | {"status": "complete"}
    except Exception as error:
        report.update(
            status="failed",
            error_type=type(error).__name__,
            error_code=getattr(error, "code", "benchmark_failed"),
        )
        raise
    finally:
        if output_path:
            helper.atomic_write_json(Path(output_path), report)
        print(json.dumps(report, indent=2))
