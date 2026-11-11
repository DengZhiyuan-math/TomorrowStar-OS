"""Current-job selection stops a pending send and retains historical pages."""

from contextlib import suppress
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_worker import job
from test_single_application_worker import single_worker as single_worker
from test_worker_current_job import prepare, retained_page

from career_evidence_graph import hosted_ats
from career_evidence_graph.application_worker import digest
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError


def test_switching_current_job_before_fill_keeps_old_page_unchanged(single_worker, monkeypatch):
    service, first, _checks, _launches = single_worker
    application = service.store.applications.get_application(first["application_id"])
    monkeypatch.setattr(
        service.store,
        "single_material_source_provider",
        lambda *_: {
            "application": deepcopy(application),
            "sources": {"items": [], "revision": digest({"items": []})},
        },
    )
    runner, original_page = retained_page(service, first)
    service.store.answers.put_answer(
        {"question": "Full name", "value": "Confirmed name", "scope": {}, "state": "confirmed"}
    )
    service.request("resume", {"controller": "synthetic-controller"})
    field = {
        "id": "name",
        "type": "text",
        "question": "Full name",
        "value": "",
        "valid": False,
        "required": True,
        "options": [],
        "multiple": False,
    }
    reads, writes, selected = [], [], []

    def observe(page, current):
        assert page is original_page
        reads.append(current["application_id"])
        # The page read yields to the user's Skip and the next current job.
        if len(reads) == 2:
            service.request(
                "skip-current",
                {"application_id": first["application_id"], "request_id": "skip-before-fill"},
            )
            second = job(service, 2)
            second["single_binding"] = {"task_id": "second-task"}
            prepare(service, second)
            service.request("resume", {"controller": "synthetic-controller"})
            selected.append(second["application_id"])
        return {"fields": [deepcopy(field)]}

    class Control:
        def is_editable(self):
            return True

        def fill(self, value):
            writes.append(value)
            field.update(value=value, valid=True)

    monkeypatch.setattr(hosted_ats, "observe", observe)
    monkeypatch.setattr(hosted_ats, "control", lambda *_args: Control())
    import time

    from career_evidence_graph.application_form_state import sample

    # The race concerns dispatch after parsing is already stable.
    before = service.store.load()
    binding = {
        "run_id": runner.run_id,
        "page_id": runner.page_ids[original_page],
        "step": before["jobs"][0]["job_url"],
        "document_token": None,
    }
    observation = {"fields": [deepcopy(field)]}
    form_state = None
    for offset in (2, 1.5, 1):
        form_state = sample(form_state, observation, binding=binding, now=time.time() - offset)
    before["jobs"][0]["form_state"] = form_state
    service.store.save(before)
    with suppress(PortalDataError):
        runner.process(deepcopy(before["jobs"][0]), before["batch_id"])

    after = service.store.load()
    assert selected and after["current_job_id"] == selected[0]
    assert writes == [] and field["value"] == ""
    assert after["jobs"][0]["intent"]["action"] == "fill"
    assert not any(row.get("action") == "fill" for row in after["jobs"][0]["observations"])


def test_retaining_three_skipped_pages_does_not_block_the_next_current_job(single_worker):
    service, first, _checks, _launches = single_worker
    retained = []
    for index in range(1, 5):
        item = first if index == 1 else job(service, index)
        item["single_binding"] = {"task_id": f"task-{index}"}
        prepare(service, item)
        if index < 4:
            retained.append(item["application_id"])
            service.request(
                "skip-current",
                {"application_id": item["application_id"], "request_id": f"skip-{index}"},
            )
    service.request("resume", {"controller": "synthetic-controller"})
    runner = ApplicationRunner(service.store, None)
    original_pages = {identifier: object() for identifier in retained}
    runner.pages.update(original_pages)
    opened = []

    class OpenedCurrentPage(Exception):
        """Stop at the browser boundary, before any navigation or external I/O."""

    def new_page():
        opened.append(service.store.load()["current_job_id"])
        raise OpenedCurrentPage

    runner.context = SimpleNamespace(new_page=new_page)
    before = service.store.load()
    with pytest.raises(OpenedCurrentPage):
        runner.process(deepcopy(before["jobs"][-1]), before["batch_id"])

    after = service.store.load()
    assert opened == [item["application_id"]]
    assert runner.pages == original_pages
    assert after["jobs"][:-1] == before["jobs"][:-1]
    assert after["current_job_id"] == item["application_id"]
