"""Known snapshot adoption preserves unresolved ancestry and the application pause."""

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_existing_latex import authorize, export, import_existing
from test_existing_latex import existing_latex as existing_latex
from test_standalone_prism_review import FakePrism

from career_evidence_graph.application_prism import PrismClient, source_snapshot
from career_evidence_graph.application_prism_review import PrismReviewStore
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def recoverable(existing_latex, tmp_path):
    service, store, job, project = existing_latex
    service.input_provider = lambda _: {
        "application_revision": job["revision"],
        "inputs": {"v": "1", "resume_configuration_revision": "old-engine"},
    }
    task = authorize(service, import_existing(service, job, project))
    client = FakePrism()
    client.configuration = lambda: PrismClient().configuration()
    reviews = PrismReviewStore(
        tmp_path / "reviews",
        client=client,
        binding_provider=lambda: source_snapshot(project, "main.tex"),
    )
    version = reviews.capture(reviews.binding()["source_revision"])["latest"]

    def unknown(_binding):
        client.calls.append("unknown_compile")
        raise TimeoutError("idle exit")

    client.compile = unknown
    store.prism_client = client
    export(service, task)
    task = wait_for(service, task["id"], lambda row: row["status"] == "needs_recheck")

    def adopt(task, **arguments):
        return store.adopt_review_snapshot(
            task["draft_id"],
            task["draft_sha256"],
            task_inputs=task["inputs"],
            review_store=reviews,
            **arguments,
        )

    service.callbacks["adopt_review_snapshot"] = adopt
    payload = {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "review_version_id": version["id"],
        "expected_pdf_sha256": version["pdf_sha256"],
    }
    return service, store, client, task, payload, project


def test_adopt_known_snapshot_preserves_unknown_attempt_and_does_not_approve_application(
    recoverable,
):
    service, store, client, previous, payload, _project = recoverable
    task = service.request("adopt-review-snapshot", payload)
    assert task["status"] == "resume_ready"
    assert task["resume_id"] != previous["stages"]["export"]["attempt_id"]
    assert task["resume_sha256"] == payload["expected_pdf_sha256"]
    assert task["export_recoveries"][-1]["prior_export_stage"] == previous["stages"]["export"]
    assert task["export_recoveries"][-1]["status"] == "needs_recheck"
    assert task["materials_confirmed"] is False and task["worker_ref"] is None
    assert task["factual_review"] == "pending"
    assert store.read_export(task["resume_id"])["operation_kind"] == "reuse_completed_review"
    assert client.calls == ["compile", "unknown_compile"]
    with pytest.raises(PortalDataError) as stale:
        service.request("adopt-review-snapshot", payload)
    assert stale.value.code == "conflict"


def test_existing_latex_can_reuse_snapshot_after_only_generator_code_revision_changes(recoverable):
    service, _store, client, _previous, payload, _project = recoverable
    provider = service.input_provider
    service.input_provider = lambda identifier: (
        provider(identifier)
        | {"inputs": {"v": "1", "resume_configuration_revision": "updated-engine"}}
    )
    task = service.request("adopt-review-snapshot", payload)
    assert task["status"] == "resume_ready"
    assert task["inputs"]["resume_configuration_revision"] == "old-engine"
    assert client.calls == ["compile", "unknown_compile"]


@pytest.mark.parametrize(
    "damage",
    [
        "inputs",
        "information_library",
        "career_source",
        "job",
        "source",
        "configuration",
        "version",
        "pdf_hash",
        "path_injection",
    ],
)
def test_adoption_rejects_changed_inputs_and_untrusted_receipts_without_task_adoption(
    recoverable, damage
):
    service, _store, client, previous, payload, project = recoverable
    if damage in {"inputs", "information_library", "career_source"}:
        provider = service.input_provider
        changed = {"v": "2"} if damage == "inputs" else {damage + "_revision": "changed"}
        service.input_provider = lambda identifier: (
            provider(identifier) | {"inputs": provider(identifier)["inputs"] | changed}
        )
    elif damage == "job":
        current = service.applications.get_application(previous["application_id"])
        service.applications.update_application(
            current["id"], {"job_description": "Changed JD"}, current["revision"]
        )
    elif damage == "source":
        (project / "main.tex").write_text("Changed source")
    elif damage == "configuration":
        service.callbacks["prism_export_configuration"] = lambda: "changed-compiler"
    elif damage == "version":
        payload["review_version_id"] = "../version"
    elif damage == "pdf_hash":
        payload["expected_pdf_sha256"] = "0" * 64
    else:
        payload["review_root"] = str(project)
    with pytest.raises(PortalDataError):
        service.request("adopt-review-snapshot", payload)
    task = service.snapshot(previous["id"])["active_task"]
    assert task["revision"] == previous["revision"]
    assert task["stages"]["export"] == previous["stages"]["export"]
    assert not task.get("export_recoveries")
    assert client.calls == ["compile", "unknown_compile"]


@pytest.mark.parametrize(
    "operation",
    ["cancel", "export", "import", "authorize", "refresh", "open", "analysis", "resume", "worker"],
)
def test_unresolved_original_request_blocks_execution_and_source_replacement_after_reuse(
    recoverable, operation
):
    service, _store, client, previous, payload, project = recoverable
    task = service.request("adopt-review-snapshot", payload)
    before = service.path.read_bytes()
    calls = {
        "cancel": lambda: service.cancel(task["id"], task["revision"]),
        "export": lambda: service.export_pdf(
            task["id"], task["revision"], task["draft_id"], task["draft_sha256"], retry=True
        ),
        "import": lambda: service.import_latex(
            task["application_id"], task["application_revision"], str(project), "main.tex"
        ),
        "authorize": lambda: service.authorize_latex_export(
            task["id"], task["revision"], task["draft_id"], task["draft_sha256"]
        ),
        "refresh": lambda: service.refresh_prism(task["id"], task["revision"]),
        "open": lambda: service.open_prism(task["id"], task["revision"]),
        "analysis": lambda: service.start(task["id"], task["revision"], "analysis"),
        "resume": lambda: service.start(task["id"], task["revision"], "resume"),
        "worker": lambda: service.prepare_worker(task["id"], task["revision"], "Germany", True),
    }
    with pytest.raises(PortalDataError):
        calls[operation]()
    assert service.path.read_bytes() == before
    assert client.calls == ["compile", "unknown_compile"]
    assert task["materials_confirmed"] is False and task["worker_ref"] is None


def test_another_job_cannot_bypass_global_unknown_request_by_importing_same_project(recoverable):
    service, _store, client, _previous, payload, project = recoverable
    service.request("adopt-review-snapshot", payload)
    another = service.applications.create_application(
        {
            "company": "Other Synthetic Employer",
            "role_title": "Python Engineer",
            "job_description": "Build documented Python tools.",
        }
    )
    service.input_provider = lambda identifier: {
        "application_revision": service.applications.get_application(identifier)["revision"],
        "inputs": {"v": "1", "resume_configuration_revision": "old-engine"},
    }
    before = service.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        service.import_latex(another["id"], another["revision"], str(project), "main.tex")
    assert error.value.code == "flow_latex_import_blocked"
    assert service.path.read_bytes() == before
    assert client.calls == ["compile", "unknown_compile"]
