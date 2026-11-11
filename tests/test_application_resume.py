"""Job-specific resume drafts use existing documentary sources, never mastery guesses."""

import json
import subprocess
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_career_portal_http import portal as portal

from career_evidence_graph.application_flow import job_input_revision
from career_evidence_graph.application_match import match_configuration_revision
from career_evidence_graph.application_resume import (
    ApplicationResumeStore,
    draft_resume,
    tailor_resume,
)
from career_evidence_graph.career_portal_data import (
    ApplicationStore,
    CareerCatalog,
    PortalDataError,
)
from career_evidence_graph.codex_cli import run_codex_exec


@pytest.fixture
def cached_resume(tmp_path):
    apps = tmp_path / "apps"
    apps.mkdir()
    career = tmp_path / "career"
    profile = career / "reports/public-site/site-content.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        json.dumps(
            {"schema_version": "public-site-source/v1", "profile": {"name": "Synthetic Person"}}
        )
    )
    applications = ApplicationStore(apps)
    job = applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "status": "drafting",
            "url": "https://careers.example.test/jobs/42",
        }
    )
    calls = []

    def tailor(draft, *args):
        calls.append("model_double")
        return draft | {"generation": "codex"}

    store = ApplicationResumeStore(
        applications,
        CareerCatalog(career),
        tmp_path / "resumes",
        tailorer=tailor,
        exporter=lambda html, pdf: pdf.write_bytes(b"%PDF-1.4 Synthetic original"),
    )
    store.model_mode = "synthetic"
    return store, job, calls


def test_draft_preserves_sources_without_keyword_filter_ranking_or_top_forty(cached_resume):
    from career_evidence_graph.application_resume import career_source_snapshot

    store, job, _ = cached_resume
    snapshot = career_source_snapshot(store.catalog)
    snapshot["items"] = [
        {
            "source_id": f"source-{index}",
            "resume_eligible": True,
            "source_kind": "contribution",
            "source_name": f"experience-{index}",
            "locator": "statement",
            "text": (
                "Compared option premiums with costs and drawdowns."
                if index == 0
                else "Quantitative AI mathematical modeling."
            ),
        }
        for index in range(42)
    ]
    job = job | {
        "role_title": "Quantitative Research",
        "job_description": "AI mathematical modeling for trading decisions.",
    }
    draft = draft_resume(job, store.catalog, source_snapshot=snapshot)
    assert len(draft["items"]) == 42
    assert draft["items"][0]["source_id"] == "source-0"
    assert draft["items"][-1]["source_id"] == "source-41"
    assert all("match_terms" not in item for item in draft["items"])


def test_job_draft_ranks_user_work_and_preserves_source_and_attribution(tmp_path):
    root = tmp_path / "career"
    (root / "reports/public-site").mkdir(parents=True)
    (root / "contributions").mkdir()
    (root / "skill-graph").mkdir()
    (root / "reports/public-site/site-content.json").write_text(
        json.dumps(
            {
                "schema_version": "public-site-source/v1",
                "profile": {
                    "name": "Synthetic Person",
                    "education": [
                        {
                            "institution": "Synthetic University",
                            "degree": "Mathematics",
                            "period": "2020–2024",
                            "detail": "",
                        }
                    ],
                },
            }
        )
    )
    for name, text, owner in [
        ("gpu", "Defined a GPU inference profiling protocol.", "User"),
        ("quant", "Defined an options risk protocol.", "User"),
        ("code", "Implemented a GPU kernel.", "Codex"),
    ]:
        (root / f"contributions/{name}.md").write_text(
            f"# {name}\n\n## Scope\n\n{text}\n\n## Responsibility attribution\n\n"
            f"| Area | Attribution |\n| --- | --- |\n| Protocol | {owner} |\n"
        )
    (root / "skill-graph/pending.md").write_text(
        "# Expert CUDA\n\nCandidate only; no mastery score."
    )
    job = {
        "id": "synthetic",
        "revision": "bound-note",
        "company": "Synthetic Co",
        "role_title": "AI Inference Researcher",
        "job_description": "GPU inference and profiling",
    }
    draft = draft_resume(job, CareerCatalog(root))
    assert draft["status"] == "draft"
    assert [item["title"] for item in draft["items"]][:1] == ["gpu"]
    assert all(item["attribution"] == "User" for item in draft["items"])
    assert all(item["source_revision"] for item in draft["items"])
    assert draft["application_revision"] == "bound-note"
    assert "skill-graph/pending.md" in [item["source_name"] for item in draft["context"]]


def test_design_scope_keeps_mixed_implementation_ownership_internal(tmp_path):
    root = tmp_path / "career"
    profile = root / "reports/public-site/site-content.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        json.dumps(
            {"schema_version": "public-site-source/v1", "profile": {"name": "Synthetic Person"}}
        )
    )
    (root / "contributions").mkdir()
    (root / "contributions/design.md").write_text(
        "# Design\n\n## Scope\n\nDefined a GPU evaluation protocol.\n\n"
        "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
        "| Protocol design | User |\n| Implementation | Codex |\n\n"
        "## Boundaries\n\nNot a claim of kernel implementation or production validation.\n"
    )
    draft = draft_resume(
        {
            "id": "synthetic",
            "revision": "rev",
            "company": "Synthetic",
            "role_title": "GPU Engineer",
            "job_description": "evaluation",
        },
        CareerCatalog(root),
    )
    assert len(draft["items"]) == 1
    item = draft["items"][0]
    assert item["text"] == "Defined a GPU evaluation protocol."
    assert "Codex" in item["attribution"]
    assert "Not a claim of kernel implementation" in item["boundaries"]
    from types import SimpleNamespace

    def model(*args, **kwargs):
        return SimpleNamespace(
            structured_result={
                "items": [{"source_index": 0, "text": "Implemented a kernel."}],
                "limitations": [],
            },
            model_dump=lambda **kwargs: {},
        )

    result = tailor_resume(
        draft, {"role_title": "GPU", "job_description": "evaluation"}, tmp_path, runner=model
    )
    assert result["items"][0]["text"] == item["text"]


@pytest.mark.parametrize(
    "description",
    ["GPU", "Build ML.\n\n## History\n\n" + "Details. " * 4000 + "French C1 required."],
    ids=["short", "long"],
)
def test_tailoring_binds_each_rewrite_to_an_available_source(tmp_path, description):
    from types import SimpleNamespace

    draft = {
        "items": [
            {
                "title": "Protocol",
                "text": "Designed a GPU protocol.",
                "attribution": "User",
                "evidence_id": "synthetic",
                "locator": "Scope",
            }
        ],
        "context": [{"kind": "candidate-skill", "title": "Expert CUDA"}],
        "limitations": [],
        "profile": {"name": "Synthetic Person", "links": []},
    }
    calls = []

    def model(config, prompt, **kwargs):
        calls.append(prompt)
        return SimpleNamespace(
            structured_result={
                "items": [{"source_index": 0, "text": "Designed a protocol for GPU profiling."}],
                "limitations": ["Runtime experience remains unverified."],
            },
            model_dump=lambda **kwargs: {"synthetic": True},
        )

    result = tailor_resume(
        draft, {"role_title": "AI Engineer", "job_description": description}, tmp_path, runner=model
    )
    assert result["items"][0]["source_text"] == "Designed a GPU protocol."
    assert result["items"][0]["attribution"] == "User"
    assert result["items"][0]["text"] == "Designed a protocol for GPU profiling."
    assert "Synthetic Person" not in calls[0]
    assert "Expert CUDA" not in calls[0]
    assert json.loads(calls[0][calls[0].index("{") :])["jd"] == description
    assert (tmp_path / "model-result.json").is_file()

    def invalid(*args, **kwargs):
        return SimpleNamespace(
            structured_result={
                "items": [{"source_index": 8, "text": "Implemented a kernel."}],
                "limitations": [],
            },
            model_dump=lambda **kwargs: {"synthetic": True},
        )

    with pytest.raises(PortalDataError) as error:
        tailor_resume(
            draft, {"role_title": "AI", "job_description": "GPU"}, tmp_path, runner=invalid
        )
    assert error.value.code == "resume_model_invalid"


@pytest.mark.worker_browser
def test_pdf_export_without_downloaded_playwright_browsers(tmp_path):
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location("macos_build", root / "macos/build.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    site = tmp_path / "site-packages"
    builder.copy_dependencies(site)
    assert not (site / "playwright/driver/package/.local-browsers").exists()
    html = tmp_path / "resume.html"
    html.write_text("<!doctype html><html><body>Synthetic resume</body></html>")
    destination = tmp_path / "resume.pdf"

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-S",
            "-c",
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path[:0] = sys.argv[1:3]\n"
            "import playwright\n"
            "assert Path(playwright.__file__).is_relative_to(sys.argv[1])\n"
            "from career_evidence_graph.application_resume import export_pdf\n"
            "export_pdf(Path(sys.argv[3]), Path(sys.argv[4]))\n",
            str(site),
            str(root / "src"),
            str(html),
            str(destination),
        ],
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(tmp_path),
            "TMPDIR": str(tmp_path),
            "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "missing-browsers"),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert destination.read_bytes().startswith(b"%PDF-")
    assert destination.stat().st_mode & 0o777 == 0o600


def test_source_snapshot_retains_all_contributions_without_a_profile_or_job_filter(tmp_path):
    from career_evidence_graph.application_resume import career_source_snapshot

    root = tmp_path / "career"
    contributions = root / "contributions"
    contributions.mkdir(parents=True)
    for index in range(41):
        (contributions / f"work-{index:02}.md").write_text(
            f"# Work {index}\n\n## Scope\n\nBuilt synthetic system {index}.\n\n"
            "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
            "| Implementation | User |\n"
        )

    snapshot = career_source_snapshot(CareerCatalog(root))

    assert len(snapshot["documents"]) == 41
    assert len(snapshot["items"]) == 41
    assert snapshot["items"][-1]["text"] == "Built synthetic system 40."
    assert snapshot["documents"][-1]["content"].startswith("# Work 40\n")
    assert snapshot["profile"] is None


def test_source_snapshot_keeps_nonpersonal_and_unknown_work_ineligible(tmp_path):
    from career_evidence_graph.application_resume import career_source_snapshot

    root = tmp_path / "career"
    contributions = root / "contributions"
    contributions.mkdir(parents=True)
    for name, scope, rows, boundaries in [
        ("user", "Built a synthetic service.", "| Implementation | User |", ""),
        (
            "mixed",
            "Defined a synthetic service protocol.",
            "| Design | User |\n| Implementation | Codex |",
            "Design only; implementation belongs to Codex.",
        ),
        ("team", "Built a synthetic service.", "| Implementation | Team |", ""),
        ("unknown", "Built a synthetic service.", "", ""),
    ]:
        (contributions / f"{name}.md").write_text(
            f"# {name}\n\n## Scope\n\n{scope}\n\n"
            "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
            f"{rows}\n\n## Boundaries\n\n{boundaries}\n"
        )

    snapshot = career_source_snapshot(CareerCatalog(root))
    items = {item["title"]: item for item in snapshot["items"]}

    assert set(items) == {"user", "mixed", "team", "unknown"}
    assert items["user"]["resume_eligible"] is True
    assert items["user"]["attribution"] == "User"
    assert items["user"]["review_status"] == "documentary"
    assert items["mixed"]["resume_eligible"] is True
    assert items["mixed"]["rewrite_allowed"] is False
    assert "Implementation | Codex" in items["mixed"]["attribution"]
    assert items["mixed"]["boundaries"] == "Design only; implementation belongs to Codex."
    assert items["team"]["resume_eligible"] is False
    assert items["unknown"]["resume_eligible"] is False
    assert items["unknown"]["review_status"] == "unknown"
    assert all(item["source_id"] == f"{item['evidence_id']}:Scope" for item in items.values())


def test_source_snapshot_retains_unavailable_document_identity_and_coverage(tmp_path):
    from career_evidence_graph.application_resume import career_source_snapshot

    root = tmp_path / "career"
    reports = root / "reports"
    reports.mkdir(parents=True)
    (reports / "invalid.md").write_bytes(b"\xff\xfe")
    (reports / "large.md").write_text("a" * 2_000_001)
    (reports / "available.md").write_text("# Available\n\nSynthetic documentary context.")

    snapshot = career_source_snapshot(CareerCatalog(root))
    documents = {document["source_name"]: document for document in snapshot["documents"]}

    assert len(documents) == 3
    assert documents["reports/available.md"]["available"] is True
    for name, code in [
        ("reports/invalid.md", "invalid-document"),
        ("reports/large.md", "document-too-large"),
    ]:
        assert documents[name]["available"] is False
        assert documents[name]["error_code"] == code
        assert documents[name]["review_status"] == "unknown"
        assert documents[name]["revision"] is None
        assert documents[name]["id"]
        assert "content" not in documents[name]
    assert snapshot["coverage"] == {
        "total_documents": 3,
        "available_documents": 1,
        "unavailable_documents": [
            documents["reports/invalid.md"]["id"],
            documents["reports/large.md"]["id"],
        ],
        "truncated": False,
    }
    assert snapshot["items"] == []


def test_private_profile_supplies_resume_sources_without_public_site_setup(tmp_path):
    from career_evidence_graph.application_resume import career_source_snapshot

    root = tmp_path / "career"
    profile = root / "sources/profile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        json.dumps(
            {
                "name": "Synthetic Private Person",
                "experience": [
                    {
                        "role": "Engineer",
                        "organization": "Synthetic Company",
                        "period": "2025–2026",
                        "detail": "Built a synthetic <b>service</b>.",
                    }
                ],
            }
        )
    )
    legacy = root / "reports/public-site/site-content.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {"schema_version": "public-site-source/v1", "profile": {"name": "Legacy Person"}}
        )
    )

    snapshot = career_source_snapshot(CareerCatalog(root))
    document = next(d for d in snapshot["documents"] if d["source_name"] == "sources/profile.json")

    assert snapshot["profile"]["name"] == "Synthetic Private Person"
    assert snapshot["profile_source"] == {
        "id": document["id"],
        "revision": document["revision"],
        "source_name": "sources/profile.json",
        "locator": "profile",
    }
    assert len(snapshot["items"]) == 1
    item = snapshot["items"][0]
    assert item["text"] == "Built a synthetic service."
    assert item["source_name"] == "sources/profile.json"
    assert item["source_id"] == f"{document['id']}:profile.experience[0]"
    assert item["attribution"] == "Editorial statement; review required"
    assert item["review_status"] == "documentary"
    assert item["resume_eligible"] is True


def test_resume_draft_reuses_private_snapshot_identity_and_unrelated_source_revision(tmp_path):
    from career_evidence_graph.application_resume import career_source_snapshot

    root = tmp_path / "career"
    profile = root / "sources/profile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        json.dumps(
            {
                "name": "Synthetic Private Person",
                "experience": [
                    {
                        "role": "Engineer",
                        "organization": "Synthetic Company",
                        "period": "2025–2026",
                        "detail": "Built a synthetic service.",
                    }
                ],
            }
        )
    )
    context = root / "sources/background.md"
    context.write_text("# Background\n\nA documentary fact without JD terms.")
    job = {
        "id": "synthetic",
        "revision": "same-job-revision",
        "company": "Synthetic",
        "role_title": "Service Engineer",
        "job_description": "Build a service.",
    }
    catalog = CareerCatalog(root)
    snapshot = career_source_snapshot(catalog)

    first = draft_resume(job, catalog)

    assert first["profile"]["name"] == "Synthetic Private Person"
    assert first["items"][0]["source_id"] == snapshot["items"][0]["source_id"]
    assert first["source_snapshot_revision"] == snapshot["revision"]
    context.write_text("# Background\n\nChanged documentary context without JD terms.")
    second = draft_resume(job, catalog)
    assert second["items"] == first["items"]
    assert second["input_digest"] != first["input_digest"]


@pytest.mark.parametrize("profile_data", [{}, {"name": 12}, {"name": "  "}])
def test_invalid_private_profile_is_explicit_and_cannot_fall_back_to_legacy(tmp_path, profile_data):
    from career_evidence_graph.application_resume import career_source_snapshot

    root = tmp_path / "career"
    profile = root / "sources/profile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(json.dumps(profile_data))
    legacy = root / "reports/public-site/site-content.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {"schema_version": "public-site-source/v1", "profile": {"name": "Legacy Person"}}
        )
    )
    catalog = CareerCatalog(root)

    snapshot = career_source_snapshot(catalog)

    assert snapshot["profile"] is None
    assert snapshot["profile_source"] is None
    assert snapshot["profile_issue"] == {
        "code": "resume_profile_invalid",
        "source_name": "sources/profile.json",
    }
    assert len(snapshot["documents"]) == 2
    assert snapshot["coverage"]["available_documents"] == 2
    with pytest.raises(PortalDataError) as failure:
        draft_resume(
            {
                "id": "synthetic",
                "revision": "rev",
                "company": "Synthetic",
                "role_title": "Engineer",
            },
            catalog,
        )
    assert failure.value.code == "resume_profile_invalid"
    assert "sources/profile.json" in failure.value.message


def test_unknown_responsibility_cannot_become_an_eligible_bounded_design(tmp_path):
    from career_evidence_graph.application_resume import career_source_snapshot

    root = tmp_path / "career"
    contribution = root / "contributions/design.md"
    contribution.parent.mkdir(parents=True)
    contribution.write_text(
        "# Design\n\n## Scope\n\nDefined a synthetic protocol.\n\n"
        "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
        "| Design | User |\n| Implementation | Unknown |\n\n"
        "## Boundaries\n\nImplementation responsibility is unresolved.\n"
    )

    snapshot = career_source_snapshot(CareerCatalog(root))

    assert len(snapshot["items"]) == 1
    item = snapshot["items"][0]
    assert "Implementation | Unknown" in item["attribution"]
    assert item["review_status"] == "unknown"
    assert item["resume_eligible"] is False
    assert item["rewrite_allowed"] is False


def test_snapshot_hashes_complete_selected_sources_and_ignores_unselected_notes(tmp_path):
    from career_evidence_graph.application_resume import career_source_snapshot

    root = tmp_path / "career"
    report = root / "reports/long.md"
    report.parent.mkdir(parents=True)
    long_text = "# Long source\n\n" + "Synthetic context. " * 5_000 + "Retained tail."
    report.write_text(long_text)
    ignored = root / "notes/private.md"
    ignored.parent.mkdir()
    ignored.write_text("An unrelated note must not reach model context.")
    outside = tmp_path / "outside.md"
    outside.write_text("A symlink target must not reach model context.")
    (report.parent / "linked.md").symlink_to(outside)
    catalog = CareerCatalog(root)

    first = career_source_snapshot(catalog)

    assert len(first["documents"]) == 1
    assert first["documents"][0]["content"] == long_text
    assert first["coverage"]["truncated"] is False
    ignored.write_text("Changed unrelated preparation note.")
    assert career_source_snapshot(catalog)["revision"] == first["revision"]
    report.write_text(long_text + " Changed tail.")
    changed = career_source_snapshot(catalog)
    assert changed["documents"][0]["id"] == first["documents"][0]["id"]
    assert changed["documents"][0]["revision"] != first["documents"][0]["revision"]
    assert changed["revision"] != first["revision"]


def test_missing_profile_keeps_analysis_sources_and_explains_private_profile_requirement(tmp_path):
    from career_evidence_graph.application_resume import career_source_snapshot

    root = tmp_path / "career"
    report = root / "reports/background.md"
    report.parent.mkdir(parents=True)
    report.write_text("# Background\n\nSynthetic context.")
    catalog = CareerCatalog(root)

    snapshot = career_source_snapshot(catalog)

    assert snapshot["profile"] is None
    assert len(snapshot["documents"]) == 1
    with pytest.raises(PortalDataError) as failure:
        draft_resume(
            {
                "id": "synthetic",
                "revision": "rev",
                "company": "Synthetic",
                "role_title": "Engineer",
            },
            catalog,
        )
    assert failure.value.code == "resume_profile_missing"
    assert "sources/profile.json" in failure.value.message
    assert "name" in failure.value.message


@pytest.fixture
def task_resume(tmp_path):
    from career_evidence_graph.application_resume import career_source_snapshot

    applications_root = tmp_path / "applications"
    applications_root.mkdir()
    applications = ApplicationStore(applications_root)
    job = applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Service Engineer",
            "job_description": "Operate service systems.",
        }
    )
    career = tmp_path / "career"
    profile = career / "sources/profile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(json.dumps({"name": "Synthetic Person"}))
    contributions = career / "contributions"
    contributions.mkdir()
    (contributions / "selected.md").write_text(
        "# Recovery design\n\n## Scope\n\nDefined a recovery protocol.\n\n"
        "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
        "| Design | User |\n| Implementation | Codex |\n\n"
        "## Boundaries\n\nDesign only; Codex performed implementation.\n"
    )
    (contributions / "keyword.md").write_text(
        "# Service operations\n\n## Scope\n\nBuilt service systems.\n\n"
        "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
        "| Implementation | User |\n"
    )
    catalog = CareerCatalog(career)
    sources = career_source_snapshot(catalog)
    selected = next(item for item in sources["items"] if item["title"] == "Recovery design")
    analysis = {
        "id": "synthetic-analysis",
        "policy_version": "documentary-match/v1",
        "application_id": job["id"],
        "application_revision": job["revision"],
        "jd_revision": job_input_revision(job),
        "source_snapshot_revision": sources["revision"],
        "configuration_revision": match_configuration_revision(),
        "selected_source_ids": [selected["source_id"]],
        "requirements": [{"source_ids": [selected["source_id"]], "sources": [selected]}],
        "limitations": [],
    }
    calls = []

    def model(config, prompt, **kwargs):
        calls.append(json.loads(prompt[prompt.index("{") :]))
        return SimpleNamespace(
            structured_result={
                "items": [{"source_index": 0, "text": "Implemented a service."}],
                "limitations": [],
            },
            model_dump=lambda **kwargs: {"synthetic": True},
        )

    store = ApplicationResumeStore(
        applications,
        catalog,
        tmp_path / "resumes",
        exporter=lambda html, pdf: pdf.write_bytes(b"%PDF-1.4 Synthetic task resume"),
        model_runner=model,
    )
    return store, job, sources, analysis, calls


def test_resume_configuration_ignores_cli_bytes_and_isolates_injected_stores(task_resume, tmp_path):
    from career_evidence_graph.application_resume import resume_configuration_revision

    store, _, _, _, _ = task_resume
    executable = tmp_path / "synthetic-codex"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    environment = {"TOMORROWSTAR_CODEX_EXECUTABLE": str(executable), "PATH": ""}
    first = resume_configuration_revision(environment=environment)
    assert resume_configuration_revision(environment=environment) == first
    # The Codex executable is provenance (batch 1-A): a CLI update keeps the revision.
    executable.write_text("#!/bin/sh\nexit 1\n")
    assert resume_configuration_revision(environment=environment) == first
    duplicate = ApplicationResumeStore(
        store.applications,
        store.catalog,
        store.root,
        model_runner=store.model_runner,
        exporter=store.exporter,
    )
    assert resume_configuration_revision(store) != resume_configuration_revision(duplicate)
    assert resume_configuration_revision(store) == resume_configuration_revision(store)
    default = ApplicationResumeStore(store.applications, store.catalog, store.root)
    assert resume_configuration_revision(
        default, environment=environment
    ) == resume_configuration_revision(environment=environment)


def test_resume_configuration_uses_a_known_partial_runners_actual_cli_environment(
    task_resume, tmp_path
):
    store, _, _, _, _ = task_resume
    executable = tmp_path / "configured-codex"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    environment = {
        "TOMORROWSTAR_CODEX_EXECUTABLE": str(executable),
        "PATH": "",
        "OPENAI_API_KEY": "synthetic-secret",
    }
    store.model_runner = partial(run_codex_exec, environment=environment)

    configuration = store.configuration()

    assert configuration["cli_identity"]["resolved_executable"] == str(executable.resolve())
    assert "synthetic-secret" not in json.dumps(configuration)


def test_tailoring_uses_jd_and_keeps_confirmed_education_fixed(tmp_path):
    education = [
        {
            "institution": "Synthetic University",
            "degree": "Ph.D. in Mathematics",
            "period": "2023–2027",
            "detail": "Confirmed doctoral record.",
        }
    ]
    draft = {
        "profile": {"name": "Synthetic Person", "education": education},
        "items": [
            {
                "title": "Protocol",
                "text": "Designed a research evaluation protocol.",
                "attribution": "User design; Codex implementation",
            }
        ],
        "limitations": ["Internal synthetic review."],
    }
    prompts = []

    def model(config, prompt, **kwargs):
        prompts.append(prompt)
        return SimpleNamespace(
            structured_result={
                "items": [
                    {"source_index": 0, "text": "Designed an evaluation protocol for research."}
                ],
                "limitations": [],
            },
            model_dump=lambda **kwargs: {},
        )

    for number, jd in enumerate(("Python evaluation", "Research software engineering")):
        directory = tmp_path / str(number)
        directory.mkdir()
        result = tailor_resume(
            draft, {"role_title": "Engineer", "job_description": jd}, directory, runner=model
        )
        assert result["profile"]["education"] == education
        assert result["items"][0]["source_text"] == "Designed a research evaluation protocol."
        assert result["items"][0]["attribution"] == "User design; Codex implementation"
        assert json.loads(prompts[-1][prompts[-1].index("{") :])["jd"] == jd
        assert "Keep confirmed education fixed" in prompts[-1]
        assert "Select and order supported skills and work experiences" in prompts[-1]
        assert "not employer-facing resume disclosures" in prompts[-1]


def test_tailoring_rejects_tool_assistance_and_retains_private_model_receipt(tmp_path):
    draft = {
        "items": [{"title": "Protocol", "text": "Designed a protocol.", "attribution": "User"}],
        "limitations": [],
    }

    def model(*args, **kwargs):
        return SimpleNamespace(
            structured_result={
                "items": [
                    {"source_index": 0, "text": "Designed a protocol with Codex assistance."}
                ],
                "limitations": [],
            },
            model_dump=lambda **kwargs: {"synthetic": "private model receipt"},
        )

    with pytest.raises(PortalDataError) as failure:
        tailor_resume(draft, {"role_title": "Engineer"}, tmp_path, runner=model)
    assert failure.value.code == "resume_tool_attribution_disclosure"
    assert json.loads((tmp_path / "model-result.json").read_text()) == {
        "synthetic": "private model receipt"
    }


def test_new_existing_latex_export_rejects_tool_disclosure_before_intent_or_compile(cached_resume):
    from career_evidence_graph.application_prism import source_snapshot

    store, job, _ = cached_resume
    job = store.applications.update_application(
        job["id"], {"job_description": "Synthetic engineering JD."}, job["revision"]
    )
    project = store.root.parent / "existing-latex"
    project.mkdir()
    (project / "main.tex").write_text(
        r"\begin{document}Codex-assisted implementation.\end{document}"
    )
    binding = source_snapshot(project, "main.tex")
    compiled = []
    store.prism_client = SimpleNamespace(
        configuration=lambda: {"kind": "synthetic"},
        compile=lambda value: compiled.append(value),
    )
    draft = store.import_latex_for_task(
        job["id"], job["revision"], task_inputs={"v": "1"}, prism=binding
    )
    before = {path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()}
    with pytest.raises(PortalDataError) as failure:
        store.export_for_draft(
            draft["id"],
            draft["draft_sha256"],
            task_inputs={"v": "1"},
            export_id="a" * 32,
            prism=binding,
        )
    assert failure.value.code == "resume_tool_attribution_disclosure"
    assert compiled == []
    assert not (store.root / ("a" * 32)).exists()
    assert before == {path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()}
    assert store.draft(draft["id"])["factual_review"] == "pending"


def test_new_existing_latex_export_allows_ai_technology_and_private_comments(cached_resume):
    from career_evidence_graph.application_prism import source_snapshot

    store, job, _ = cached_resume
    job = store.applications.update_application(
        job["id"], {"job_description": "Synthetic AI engineering JD."}, job["revision"]
    )
    project = store.root.parent / "existing-technology-latex"
    project.mkdir()
    source = (
        "\\begin{document}\nBuilt AI education systems with PyTorch and OpenAI API.\n"
        "% Internal provenance: Codex-assisted implementation.\n\\end{document}\n"
    )
    (project / "main.tex").write_text(source)
    binding = source_snapshot(project, "main.tex")
    compiled = []

    def compile_synthetic(value):
        compiled.append(value)
        return {
            "source_revision": value["source_revision"],
            "pdf": (
                Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"
            ).read_bytes(),
            "build": {"main": value["main"], "exit": 0, "pdf_updated": True},
        }

    store.prism_client = SimpleNamespace(
        configuration=lambda: {"kind": "synthetic"}, compile=compile_synthetic
    )
    draft = store.import_latex_for_task(
        job["id"], job["revision"], task_inputs={"v": "1"}, prism=binding
    )
    result = store.export_for_draft(
        draft["id"],
        draft["draft_sha256"],
        task_inputs={"v": "1"},
        export_id="b" * 32,
        prism=binding,
    )
    assert compiled == [binding]
    assert result["factual_review"] == "pending"
    assert (store.root / result["id"] / "resume.tex").read_text() == source
    assert store.read_export(result["id"]) == result
    assert store.draft(draft["id"])["factual_review"] == "pending"


def test_catalog_display_label_does_not_invalidate_retained_source_receipts(
    cached_resume, monkeypatch
):
    from career_evidence_graph.application_resume import career_source_snapshot

    store = cached_resume[0]
    before = career_source_snapshot(store.catalog)
    original = store.catalog._record

    def relabeled(*args, **kwargs):
        return {**original(*args, **kwargs), "summary": "Accepted career-library content"}

    monkeypatch.setattr(store.catalog, "_record", relabeled)
    assert career_source_snapshot(store.catalog) == before
