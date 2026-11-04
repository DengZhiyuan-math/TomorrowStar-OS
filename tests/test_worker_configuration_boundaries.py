"""Directory custody and current-mode authorization use synthetic records only."""

import shutil
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_application_worker import job
from test_application_worker import service as _service
from test_generic_worker import URL
from test_hosted_ats import LEVER, PDF

from career_evidence_graph.application_worker import (
    WorkerService,
    WorkerStore,
    start_run,
)
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError

service = _service


def test_copied_applications_cannot_reuse_the_original_runtime(service, tmp_path):
    service.request("prepare", {"jobs": [job(service)]})
    start_run(service.store)
    state = service.store.load()
    state["jobs"][0].update(
        page_open=True,
        handed_off=True,
        intent={"action": "upload", "attempt_id": "retained-upload"},
    )
    service.store.save(state)
    before = {
        path.relative_to(service.store.root): path.read_bytes()
        for path in service.store.root.rglob("*")
        if path.is_file()
    }
    copied = tmp_path / "copied-applications"
    shutil.copytree(service.store.applications.root, copied)
    copied_before = {
        path.name: path.read_bytes() for path in copied.glob("*") if path.suffix in {".md", ".json"}
    }

    assert copied_before
    with pytest.raises(PortalDataError) as error:
        WorkerService(
            ApplicationStore(copied), service.store.root, fixture_origin=service.fixture_origin
        )

    assert error.value.code == "runtime_applications_mismatch"
    assert {
        path.relative_to(service.store.root): path.read_bytes()
        for path in service.store.root.rglob("*")
        if path.is_file()
    } == before
    assert {
        path.name: path.read_bytes() for path in copied.glob("*") if path.suffix in {".md", ".json"}
    } == copied_before
    assert service.store.load()["jobs"][0] == state["jobs"][0]


def test_runtime_records_the_actual_applications_directory(service):
    service.request("prepare", {"jobs": [job(service)]})
    start_run(service.store)
    state = service.store.load()
    assert state["applications_root"] == str(service.store.applications.root)
    assert state["runtime"]["applications_root"] == state["applications_root"]
    reopened = WorkerStore(service.store.applications, service.store.root)
    assert reopened.load() == state


def test_unbound_historical_checkpoint_requires_an_independent_runtime(service):
    import json

    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    del state["applications_root"]
    service.store.path.write_text(json.dumps(state))
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        WorkerStore(service.store.applications, service.store.root)
    assert error.value.code == "runtime_applications_mismatch"
    assert service.store.path.read_bytes() == before


def test_an_independent_runtime_can_use_the_selected_applications_directory(service, tmp_path):
    service.request("prepare", {"jobs": [job(service)]})
    copied = tmp_path / "copied-applications"
    shutil.copytree(service.store.applications.root, copied)
    before = service.store.path.read_bytes()
    separate = WorkerStore(ApplicationStore(copied), tmp_path / "separate-worker")
    assert separate.load()["applications_root"] == str(copied)
    assert separate.load()["jobs"] == []
    assert service.store.path.read_bytes() == before


def live_batch(tmp_path, monkeypatch):
    import base64

    applications = tmp_path / "applications"
    applications.mkdir()
    enabled = WorkerService(
        ApplicationStore(applications), tmp_path / "worker", live=True, generic=True
    )
    monkeypatch.setattr(enabled, "spawn", lambda: None)
    records = [
        enabled.store.applications.create_application(
            {
                "company": f"Synthetic {index}",
                "role_title": "Engineer",
                "status": "drafting",
                "url": url,
                "application_strategy": "batch",
            }
        )
        for index, url in enumerate((URL, LEVER))
    ]
    enabled.request(
        "prepare",
        {
            "jobs": [
                {
                    "application_id": record["id"],
                    "revision": record["revision"],
                    "country": "CHE",
                    "filename": "resume.pdf",
                    "file_base64": base64.b64encode(PDF).decode(),
                }
                for record in records
            ]
        },
    )
    return enabled


def disable_generic(enabled, monkeypatch):
    strict = WorkerService(enabled.store.applications, enabled.store.root, live=True)
    monkeypatch.setattr(strict, "spawn", lambda: None)
    return strict


def test_current_mode_pauses_old_generic_job_and_preserves_known_platform(tmp_path, monkeypatch):
    enabled = live_batch(tmp_path, monkeypatch)
    strict = disable_generic(enabled, monkeypatch)
    state = strict.request("resume", {"controller": "synthetic-controller"})
    generic, lever = state["jobs"]
    assert generic["status"] == "needs_recheck"
    assert generic["reason"] == "generic_disabled"
    assert lever["status"] == "queued"
    assert not state["generic_enabled"]
    assert not enabled.snapshot()["generic_enabled"]


def test_current_mode_preserves_generic_unknown_intent_and_attachment(tmp_path, monkeypatch):
    enabled = live_batch(tmp_path, monkeypatch)
    state = enabled.store.load()
    current = state["jobs"][0]
    current.update(page_open=True, intent={"action": "upload", "attempt_id": "unknown-upload"})
    enabled.store.save(state)
    before = deepcopy(current)
    attachment = Path(current["file_path"])
    strict = disable_generic(enabled, monkeypatch)

    strict.request("resume", {"controller": "synthetic-controller"})

    after = strict.store.load()["jobs"][0]
    assert after["intent"] == before["intent"]
    assert after["page_open"] == before["page_open"]
    assert after["file_path"] == before["file_path"]
    assert after["observations"] == before["observations"]
    assert attachment.read_bytes() == PDF
    assert after["status"] == "needs_recheck" and after["reason"] == "generic_disabled"


def test_generic_can_resume_after_current_mode_is_explicitly_enabled(tmp_path, monkeypatch):
    enabled = live_batch(tmp_path, monkeypatch)
    strict = disable_generic(enabled, monkeypatch)
    state = strict.request("resume", {"controller": "synthetic-controller"})
    restored = WorkerService(
        enabled.store.applications, enabled.store.root, live=True, generic=True
    )
    monkeypatch.setattr(restored, "spawn", lambda: None)

    restored.request(
        "recheck", {"application_id": state["jobs"][0]["application_id"], "acknowledge": True}
    )
    current = restored.request("resume", {"controller": "synthetic-controller"})

    assert current["generic_enabled"]
    assert [entry["status"] for entry in current["jobs"]] == ["queued", "queued"]


def test_stale_enabled_service_cannot_prepare_generic_after_mode_is_disabled(tmp_path, monkeypatch):
    import base64

    enabled = live_batch(tmp_path, monkeypatch)
    disable_generic(enabled, monkeypatch)
    enabled.request("cancel", {"controller": "synthetic-controller"})
    state = enabled.store.load()
    app = enabled.store.applications.get_application(state["jobs"][0]["application_id"])
    with pytest.raises(PortalDataError) as error:
        enabled.request(
            "prepare",
            {
                "jobs": [
                    {
                        "application_id": app["id"],
                        "revision": app["revision"],
                        "country": "CHE",
                        "filename": "resume.pdf",
                        "file_base64": base64.b64encode(PDF).decode(),
                    }
                ]
            },
        )
    assert error.value.code == "unsupported_platform"
    assert enabled.store.load()["batch_id"] == state["batch_id"]
    assert all(entry["status"] == "cancelled" for entry in enabled.store.load()["jobs"])


@pytest.mark.parametrize("operation", ["recheck", "review"])
def test_disabled_generic_cannot_be_rechecked_or_handed_off(tmp_path, monkeypatch, operation):
    enabled = live_batch(tmp_path, monkeypatch)
    state = enabled.store.load()
    current = state["jobs"][0]
    current.update(
        status="ready_for_review" if operation == "review" else "needs_recheck", page_open=True
    )
    enabled.store.save(state)
    strict = disable_generic(enabled, monkeypatch)
    before = deepcopy(strict.store.load()["jobs"][0])
    with pytest.raises(PortalDataError) as error:
        strict.request(
            operation, {"application_id": current["application_id"], "acknowledge": True}
        )
    assert error.value.code == "generic_disabled"
    assert strict.store.load()["jobs"][0] == before
    assert strict.store.load()["commands"] == []


@pytest.mark.parametrize("action", ["open", "fill", "upload"])
def test_existing_runner_uses_current_generic_mode_before_actions(tmp_path, monkeypatch, action):
    enabled = live_batch(tmp_path, monkeypatch)
    start_run(enabled.store)
    enabled.request("resume", {"controller": "synthetic-controller"})
    runner = ApplicationRunner(enabled.store, None)
    disable_generic(enabled, monkeypatch)
    state = enabled.store.load()
    generic, lever = state["jobs"]

    with pytest.raises(PortalDataError) as error:
        runner.authorize(generic, state["batch_id"], {"action": action})
    assert error.value.code == "generic_disabled"
    assert enabled.store.load()["jobs"][0]["intent"] is None
    assert runner.authorize(lever, state["batch_id"], {"action": "open"})


def test_current_runner_aborts_requests_if_checkpoint_directory_binding_changes(
    tmp_path, monkeypatch
):
    import json

    enabled = live_batch(tmp_path, monkeypatch)
    runner = ApplicationRunner(enabled.store, None)
    state = enabled.store.load()
    state["applications_root"] = str(tmp_path / "different-applications")
    enabled.store.path.write_text(json.dumps(state))
    page = object()
    outcomes = []
    route = SimpleNamespace(
        request=SimpleNamespace(frame=SimpleNamespace(page=page)),
        continue_=lambda: outcomes.append("continue"),
        abort=lambda *_: outcomes.append("abort"),
    )

    runner._live_guard(route)

    assert outcomes == ["abort"]
    assert runner.storage_stopped


@pytest.mark.parametrize("operation", ["review", "recheck"])
def test_old_generic_commands_cannot_reclaim_or_release_guards_after_mode_change(
    tmp_path, monkeypatch, operation
):
    enabled = live_batch(tmp_path, monkeypatch)
    state = enabled.store.load()
    current = state["jobs"][0]
    current.update(status="ready_for_review", page_open=True)
    state["commands"] = [{"action": operation, "id": current["application_id"]}]
    enabled.store.save(state)
    runner = ApplicationRunner(enabled.store, None)

    class Page:
        def is_closed(self):
            return False

        def unroute(self, *_):
            pytest.fail("Must retain send guard")

    page = Page()
    runner.pages[current["application_id"]] = page
    runner.guards[current["application_id"]] = object()
    disable_generic(enabled, monkeypatch)
    state = enabled.store.load()

    runner.commands(state)

    assert state["jobs"][0]["status"] == "needs_recheck"
    assert state["jobs"][0]["reason"] == "generic_disabled"
    assert page not in runner.handed_off_pages
    assert runner.pages[current["application_id"]] is page
