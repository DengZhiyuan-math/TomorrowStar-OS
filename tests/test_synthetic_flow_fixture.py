"""Synthetic native fixtures stay external and exercise the real offline CLI boundary."""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from career_evidence_graph.career_portal_data import ApplicationStore
from career_evidence_graph.codex_cli import validate_codex_executable

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/create_synthetic_flow.py"


def create(root):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)], capture_output=True, text=True, check=False
    )


def test_generator_seeds_only_isolated_inputs_and_a_valid_synthetic_executable(tmp_path):
    root = tmp_path / "native-fixture"
    result = create(root)
    assert result.returncode == 0, result.stderr
    marker = json.loads((root / "synthetic-flow.json").read_text())
    assert marker == {
        "schemaVersion": 1,
        "purpose": "single-job-synthetic",
        "codex_sha256": hashlib.sha256((root / "codex-fixture").read_bytes()).hexdigest(),
    }
    assert json.loads((root / "portal.json").read_text()) == {
        "applications": str(root / "applications"),
        "career_workspace": str(root / "career"),
    }
    for name in ["home", "tmp", "runtime/single-job-flow", "runtime/single-job-worker"]:
        assert (root / name).is_dir()
        assert list((root / name).iterdir()) == []
    assert (root / "career/.git").is_dir()
    assert (root / "career/.gitignore").read_text() == ".career-evidence/raw/\n"
    applications = ApplicationStore(root / "applications").list_applications()
    assert len(applications) == 1
    assert applications[0]["company"] == "Synthetic Employer"
    assert applications[0]["url"].startswith("https://jobs.lever.co/synthetic/")
    assert applications[0]["job_description"] == ""
    executable = validate_codex_executable(root / "codex-fixture")
    version = subprocess.run([executable, "--version"], capture_output=True, text=True, check=True)
    assert "synthetic" in version.stdout and "new_model_calls=0" in version.stdout


def test_default_analysis_and_resume_use_real_driver_with_offline_synthetic_cli(
    tmp_path, monkeypatch
):
    from career_evidence_graph.application_match import analyze_job
    from career_evidence_graph.application_resume import (
        ApplicationResumeStore,
        career_source_snapshot,
        resume_configuration_revision,
    )
    from career_evidence_graph.career_portal_data import CareerCatalog

    root = tmp_path / "default-chain"
    assert create(root).returncode == 0
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(root / "codex-fixture"))
    applications = ApplicationStore(root / "applications")
    job = applications.list_applications()[0]
    job = applications.update_application(
        job["id"], {"job_description": "Python\nunit tests"}, job["revision"]
    )
    catalog = CareerCatalog(root / "career")
    snapshot = career_source_snapshot(catalog)
    report = analyze_job(job, snapshot, root / "runtime/single-job-flow/analysis-one")
    assert report["score"] == {
        "lower": 100,
        "upper": 100,
        "coverage": 100,
        "eligibility": "not_specified",
    }
    assert report["selected_source_ids"] == [snapshot["items"][0]["source_id"]]
    assert "synthetic" in report["model"]["cli_version"]
    from career_evidence_graph.application_full_latex import generate_full_latex
    from career_evidence_graph.application_prism import source_snapshot

    binding = source_snapshot(root / "latex-base", "main.tex")
    store = ApplicationResumeStore(
        applications,
        catalog,
        root / "runtime/single-job-flow/resumes",
    )
    result = generate_full_latex(
        store,
        job["id"],
        job["revision"],
        source_snapshot=snapshot,
        analysis=report,
        task_inputs={"sources_revision": snapshot["revision"]},
        latex_base=binding,
    )
    assert result["origin"] == "generated_latex"
    assert snapshot["items"][0]["text"] in result["latex_source"]
    assert not list(store.root.glob("*/resume.pdf"))
    assert result["resume_configuration_revision"] == resume_configuration_revision()
    assert store.configuration()["tailorer"] == "codex"
    assert store.configuration()["model_runner"] == "codex"
    for directory in [root / "runtime/single-job-flow/analysis-one", store.root / result["id"]]:
        raw = json.loads((directory / "model-result.json").read_text())["raw_stdout_jsonl"]
        assert '"new_model_calls": 0' in raw


def test_generator_never_changes_existing_directory(tmp_path):
    root = tmp_path / "existing"
    root.mkdir()
    original = root / "preserved.txt"
    original.write_bytes(b"Preserve the existing fixture and its history.\n")
    result = create(root)
    assert result.returncode == 1 and "already exists" in result.stderr
    assert list(root.iterdir()) == [original]
    assert original.read_bytes() == b"Preserve the existing fixture and its history.\n"


@pytest.mark.parametrize("descendant", [False, True])
def test_generator_rejects_symlink_root_and_symlink_parent(tmp_path, descendant):
    target = tmp_path / "actual"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    result = create(alias / "new" if descendant else alias)
    assert result.returncode == 1 and "symbolic links" in result.stderr
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("kind", ["checkout", "child", "ancestor"])
def test_generator_rejects_every_system_checkout_overlap(kind):
    checkout = SCRIPT.parents[1]
    root = {
        "checkout": checkout,
        "child": checkout / "forbidden-fixture",
        "ancestor": checkout.parent,
    }[kind]
    result = create(root)
    assert result.returncode == 1 and "outside the system checkout" in result.stderr


def test_unmatched_jd_keeps_unknown_and_does_not_fabricate_resume_material(tmp_path, monkeypatch):
    from career_evidence_graph.application_match import analyze_job
    from career_evidence_graph.application_resume import career_source_snapshot
    from career_evidence_graph.career_portal_data import CareerCatalog

    root = tmp_path / "unknown"
    assert create(root).returncode == 0
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(root / "codex-fixture"))
    store = ApplicationStore(root / "applications")
    job = store.list_applications()[0]
    job = store.update_application(
        job["id"], {"job_description": "German C1\nGPU training"}, job["revision"]
    )
    report = analyze_job(
        job,
        career_source_snapshot(CareerCatalog(root / "career")),
        root / "runtime/single-job-flow/unknown-analysis",
    )
    assert report["selected_source_ids"] == []
    assert [row["judgment"] for row in report["requirements"]] == ["unknown", "unknown"]
    assert report["score"]["lower"] == 0 and report["score"]["upper"] == 100


def test_fixture_rejects_gmail_and_other_unsupported_schema_without_fallback(tmp_path):
    root = tmp_path / "unsupported"
    assert create(root).returncode == 0
    schema = root / "runtime/gmail-schema.json"
    schema.write_text(json.dumps({"type": "object", "properties": {"emails": {"type": "array"}}}))
    result = subprocess.run(
        [str(root / "codex-fixture"), "exec", "--json", "--output-schema", str(schema), "{}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert not result.stdout
    assert "Gmail and other tool transports are disabled" in result.stderr


@pytest.mark.parametrize("availability", [None, True, False])
@pytest.mark.parametrize("scope_contract", ["legacy", "trusted_inline", "trusted_reference"])
def test_fixture_accepts_projected_sources_and_respects_explicit_unavailability(
    tmp_path, availability, scope_contract
):
    root = tmp_path / "source-projection"
    assert create(root).returncode == 0
    schema = root / "runtime/schema.json"
    contract = {
        "properties": {
            key: {}
            for key in (
                "role_understanding",
                "requirements",
                "selected_source_ids",
                "selection_rationale",
                "extracted_fields",
                "limitations",
            )
        }
    }
    if scope_contract != "legacy":
        requirement = {"properties": {"claim_scope": {"enum": ["documentary", "unknown"]}}}
        if scope_contract == "trusted_reference":
            contract["$defs"] = {"_Requirement": requirement}
            requirement = {"$ref": "#/$defs/_Requirement"}
        contract["properties"]["requirements"] = {"items": requirement}
    schema.write_text(json.dumps(contract))
    source = {
        "source_id": "synthetic-source",
        "text": "Implemented Python checks.",
        "attribution": "User",
        "match_eligible": True,
        "resume_eligible": True,
        "rewrite_allowed": True,
    }
    if availability is not None:
        source["available"] = availability
    result = subprocess.run(
        [
            str(root / "codex-fixture"),
            "exec",
            "--json",
            "--output-schema",
            str(schema),
            json.dumps({"job": {"job_description": "Python"}, "sources": [source]}),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    output = json.loads(result.stdout.splitlines()[-1])["result"]
    assert output["selected_source_ids"] == ([] if availability is False else ["synthetic-source"])
    expected_scope = "personal_completed" if scope_contract == "legacy" else "documentary"
    assert output["requirements"][0]["claim_scope"] == (
        "unknown" if availability is False else expected_scope
    )


def test_new_worker_child_accepts_default_binding_without_an_injected_model_nonce(
    tmp_path, monkeypatch
):
    from career_evidence_graph.application_resume import ApplicationResumeStore
    from career_evidence_graph.career_portal import create_server

    root = tmp_path / "child-binding"
    assert create(root).returncode == 0
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(root / "codex-fixture"))
    monkeypatch.setenv("HOME", str(root / "home"))
    monkeypatch.setenv("TMPDIR", str(root / "tmp"))
    applications = ApplicationStore(root / "applications")
    job = applications.list_applications()[0]
    job = applications.update_application(
        job["id"], {"job_description": "Python\nunit tests"}, job["revision"]
    )

    from types import SimpleNamespace

    from career_evidence_graph.application_full_latex import generate_full_latex

    class FullLatexFixtureStore(ApplicationResumeStore):
        # Exercise the default CLI/configuration binding through the complete-source
        # generator; the experience handoff protocol is covered in its own tests.
        def generate_for_task(self, identifier, revision, **options):
            from career_evidence_graph.application_information import (
                material_information_library,
                read_information_library,
            )

            options.pop("force_regenerate", None)
            options.pop("draft_only", None)
            # This explicit legacy producer owns its synthetic empty library.
            # Fixed production handoffs never fetch current information inputs.
            options["information_library"] = material_information_library(
                self.applications.get_application(identifier), read_information_library(None)
            )
            return generate_full_latex(self, identifier, revision, **options)

    def resume_factory(applications, catalog, directory):
        raw = (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
        return FullLatexFixtureStore(
            applications,
            catalog,
            directory,
            prism_client=SimpleNamespace(
                configuration=lambda: {"synthetic": "latex-compiler-boundary"},
                compile=lambda binding: {
                    "build": {"main": binding["main"], "exit": 0, "pdf_updated": True},
                    "pdf": raw,
                },
            ),
        )

    server = create_server(
        root / "applications",
        root / "career",
        write_admission_policy="development",
        flow_root=root / "runtime/single-job-flow",
        worker_root=root / "runtime/single-job-worker",
        worker_fixtures=True,
        worker_headless=True,
        flow_resume_factory=resume_factory,
    )
    try:
        flow = server.application_flow_service
        task = flow.create(job["id"], job["revision"])
        assert task["material_contract"] == "content-writing/v1"
        # The complete-source producer above replays a saved pre-JSON task.
        # Preserve the current default and limit this restoration to that task.
        with flow.applications.write_lock():
            state = flow._load()
            saved = flow._task(state, task["id"])
            assert saved["revision"] == task["revision"]
            assert all(stage["status"] == "pending" for stage in saved["stages"].values())
            saved.pop("material_contract")
            flow._save(state)
        task = flow.snapshot(task["id"])["active_task"]
        for stage, expected in [
            ("analysis", "analysis_ready"),
            ("resume", "draft_ready"),
            ("export", "materials_ready"),
        ]:
            if stage == "resume":
                task = flow.prepare_automatic_materials(
                    task["id"], task["revision"], str(root / "latex-base"), "main.tex"
                )
            flow.start(task["id"], task["revision"], stage)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                task = flow.snapshot()["active_task"]
                if task["status"] == expected:
                    break
                if task["stages"][stage]["status"] == "failed":
                    pytest.fail(str(task["stages"][stage]))
                time.sleep(0.005)
            assert task["status"] == expected
        flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert server.worker_service.snapshot()["control"] == "paused"
        assert server.worker_service.process is None
        child_code = """import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from career_evidence_graph.application_single_binding import check_single_binding
from career_evidence_graph.application_worker import WorkerStore
from career_evidence_graph.career_portal_data import ApplicationStore
root = Path(sys.argv[2])
applications = ApplicationStore(root / "applications")
store = WorkerStore(applications, root / "runtime/single-job-worker")
state = store.load()
check_single_binding(applications, root / "runtime/single-job-flow", root / "career",
                     state["jobs"][0], state["batch_id"], worker_root=store.root)
print("default child binding verified; synthetic; new_model_calls=0")
"""
        child = subprocess.run(
            [sys.executable, "-c", child_code, str(SCRIPT.parents[1] / "src"), str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert child.returncode == 0, child.stderr
        assert "default child binding verified" in child.stdout
    finally:
        server.server_close()


def test_fixed_jd_intake_uses_synthetic_cli_and_rejects_unknown_source(tmp_path, monkeypatch):
    from career_evidence_graph.application_jd_extract import extract_job_fields
    from career_evidence_graph.application_worker_fixtures import SOURCE_INTAKE_JD
    from career_evidence_graph.career_portal_data import PortalDataError

    root = tmp_path / "source-intake"
    assert create(root).returncode == 0
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(root / "codex-fixture"))
    extracted = extract_job_fields(SOURCE_INTAKE_JD, root / "runtime" / "intake")
    assert extracted["company"] == "Synthetic Employer"
    assert extracted["role_title"] == "Software Engineer"
    assert extracted["is_full_jd"] is True
    result = json.loads((root / "runtime" / "intake" / "model-result.json").read_text())
    assert '"new_model_calls": 0' in result["raw_stdout_jsonl"]
    with pytest.raises(PortalDataError) as error:
        extract_job_fields(SOURCE_INTAKE_JD + "\nUnknown change", root / "runtime" / "unknown")
    assert error.value.code == "intake_extraction_failed"
