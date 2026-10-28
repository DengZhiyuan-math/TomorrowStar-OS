"""The default flow must compare the configured library's business evidence."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from test_application_match import model_output, model_runner
from test_career_portal_http import portal as portal

from career_evidence_graph.application_career_library import CareerLibrary
from career_evidence_graph.application_information import (
    material_information_library,
    read_information_library,
)
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog


def test_default_flow_analysis_reads_bound_finance_library(portal, tmp_path, monkeypatch):
    contributions = portal.career / "contributions"
    contributions.mkdir()
    (contributions / "ai.md").write_text(
        "# Synthetic AI model\n\n## Scope\nImplemented an AI model.\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n"
    )
    library_root = tmp_path / "finance-library"
    library_root.mkdir()

    def save(name, value):
        raw = json.dumps(value).encode()
        (library_root / name).write_bytes(raw)
        return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}

    catalog = save(
        "catalog.json",
        {
            "records": [
                {
                    "candidate_id": "options",
                    "title": "Synthetic option research",
                    "record_class": "current-confirmed-identity",
                }
            ]
        },
    )
    finance_text = "Compared option premium income with transaction costs and drawdowns."
    capture = save("capture.json", {"research": finance_text})
    manifest = tmp_path / "finance-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "root": str(library_root),
                "catalog": catalog,
                "evidence": [{**capture, "candidate_id": "options", "pointer": "/research"}],
            }
        )
    )
    base = career_source_snapshot(CareerCatalog(portal.career))
    assert finance_text not in json.dumps(base)
    complete = CareerLibrary(manifest).snapshot_for_analysis(base)
    finance = next(row for row in complete["items"] if row["source_name"] == "capture.json")
    output = model_output(base)
    output["role_understanding"] = {
        "business_objective": "Assess trading strategy returns and risk.",
        "work_outputs": ["Investment research"],
        "methods_role": "Mathematical methods support investment decisions.",
    }
    output["requirements"][0].update(
        text="Assess investment returns and risk",
        source_ids=[finance["source_id"]],
        citations=[{"source_id": finance["source_id"], "quote": finance_text}],
        claim_scope="documentary",
    )
    output["selected_source_ids"] = [finance["source_id"]]
    output["selection_rationale"] = [
        {
            "source_id": finance["source_id"],
            "business_relevance": "Option income, costs and drawdowns inform investment research.",
            "evidence_role": "direct_domain",
        }
    ]
    calls = []
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic trading firm",
            "role_title": "Quantitative Research Intern",
            "job_description": "Research trading strategies, investment returns and risk.",
        }
    )

    def runner(config, prompt, **kwargs):
        schema = json.loads(config.output_schema.read_text())
        if set(schema["properties"]) == {"business_object", "role_understanding", "groups"}:
            brief = {
                "business_object": "Trading strategy research",
                "role_understanding": output["role_understanding"],
                "groups": [
                    {
                        "label": "Investment research",
                        "jd_quote": job["job_description"],
                        "operator": "all",
                        "importance": "required",
                        "hard_condition": False,
                        "weight": 100,
                        "weight_reason": "The stated business output.",
                        "requirements": [
                            {
                                "text": output["requirements"][0]["text"],
                                "jd_quote": job["job_description"],
                            }
                        ],
                    }
                ],
            }
            return model_runner(brief, calls)(config, prompt, **kwargs)
        return model_runner(output, calls)(config, prompt, **kwargs)

    server = create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "business-flow",
        career_library_manifest=manifest,
        flow_match_runner=runner,
        write_admission_policy="development",
    )
    try:
        flow = server.application_flow_service
        task = flow.create(job["id"], job["revision"])
        result = flow.callbacks["analysis"](task)
        assert finance_text in calls[-1][-1], "Default analysis omitted configured finance evidence"
        assert result["selected_source_ids"] == [finance["source_id"]]
        assert result["job_brief"]["role_understanding"] == output["role_understanding"]
        assert result["retrieval"]["index_status"] == "not_configured"
        assert result["retrieval"]["selected_candidate_ids"] == []
        assert len(server.analysis_context(job["id"], ["options"])[1]["items"]) == 3

        project = tmp_path / "synthetic-base"
        project.mkdir()
        (project / "main.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section*{Research}\nSynthetic research.\n\\end{document}\n"
        )
        request = tmp_path / "handoff-request.json"
        arguments = {
            "identifier": job["id"],
            "revision": job["revision"],
            "analysis": result,
            "task_inputs": task["inputs"],
            "information_library": material_information_library(
                job, read_information_library(None)
            ),
            "latex_base": source_snapshot(project, "main.tex"),
        }
        request.write_text(json.dumps(arguments))
        official = server.application_resume_store.generate_for_task(
            **arguments, source_snapshot=complete
        )
        assert official["kind"] == "experience_handoff"
        command = [
            sys.executable,
            "-B",
            str(Path(__file__).parents[1] / "scripts/run_experience_generation.py"),
            "--applications",
            str(portal.applications),
            "--career-workspace",
            str(portal.career),
            "--career-library-manifest",
            str(manifest),
            "--resume-root",
            str(server.application_resume_store.root),
        ]
        prepared = subprocess.run(
            [*command, "prepare", "--request", str(request)], capture_output=True, text=True
        )
        assert prepared.returncode == 0, prepared.stderr
        handoff = json.loads(prepared.stdout)
        context_command = [*command, "context", "--generation-id", handoff["id"]]
        context = subprocess.run(context_command, capture_output=True, text=True)
        assert context.returncode == 0, context.stderr
        context = json.loads(context.stdout)
        assert finance["source_id"] in context["selected_source_ids"]
        assert context["role_understanding"] == output["role_understanding"]
        assert len(context["sources"]) == 3

        # P05 keeps the delivered facts; a later capture change is not a new input.
        (library_root / "capture.json").write_text('{"research":"Changed synthetic fact"}')
        changed = subprocess.run(context_command, capture_output=True, text=True)
        assert changed.returncode == 0, changed.stderr
        retained = json.loads(changed.stdout)
        assert retained["generation_contract"] == "fixed-writing/v1"
        assert retained["material_packet"] == context["material_packet"]
        assert retained["fixed_inputs_revision"] == context["fixed_inputs_revision"]
        assert changed.stderr == ""
    finally:
        server.server_close()
