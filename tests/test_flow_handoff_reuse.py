"""A fresh page uses saved materials without reviving its previous execution."""

# ruff: noqa: F811 -- imported pytest fixtures are injected as parameters

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from test_application_existing_handoff import attach, files, linked  # noqa: F401
from test_application_handoff import SHA, act, handoff, ready  # noqa: F401

from career_evidence_graph import application_flow
from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import PortalDataError


def test_new_page_attempt_keeps_the_same_flow_materials_and_previous_report(linked):
    flow, service, original, report, _calls = linked
    attached = attach(flow, original, report, service.root)
    previous_report = deepcopy(report["readbacks"])

    result = flow.request(
        "restart-existing-handoff",
        {"task_id": attached["id"], "task_revision": attached["revision"]},
    )

    assert result["id"] == attached["id"]
    assert result["resume_id"] == attached["resume_id"]
    assert result["resume_sha256"] == SHA
    assert result["artifacts"] == attached["artifacts"]
    assert result["stages"] == attached["stages"]
    assert result["status"] == "materials_ready"
    assert "codex_handoff_ref" not in result
    attempt = result["codex_handoff_attempt"]
    assert attempt["task_id"] != report["id"]
    assert attempt["origin_task_revision"] == attached["revision"]
    snapshot = service.snapshot()
    previous = next(task for task in snapshot["tasks"] if task["id"] == report["id"])
    assert previous["readbacks"] == previous_report
    assert previous["active"] is False
    assert snapshot["active_task"]["id"] == attempt["task_id"]
    assert snapshot["active_task"]["readbacks"] == []
    projected = flow.snapshot(attached["id"])["active_task"]
    assert projected["status"] == "materials_ready"
    assert projected["codex_handoff_attempt"]["status"] == "prepared"
    assert projected["codex_handoff_attempt"]["reuse_field_count"] == 1
    assert "Synthetic Person" in projected["codex_handoff_attempt"]["prompt"]
    assert "codex_handoff_ref" not in projected


def test_repeating_a_lost_response_returns_the_same_attempt_without_new_history(linked):
    flow, service, original, report, _calls = linked
    attached = attach(flow, original, report, service.root)
    request = {"task_id": attached["id"], "task_revision": attached["revision"]}

    first = flow.request("restart-existing-handoff", request)
    before = service.path.read_bytes()
    repeated = flow.request("restart-existing-handoff", request)

    assert repeated == first
    assert service.path.read_bytes() == before
    assert len(service.snapshot()["tasks"]) == 2
    assert len(repeated["codex_handoff_history"]) == 2


@pytest.mark.parametrize("write_then_lose_response", [False, True])
def test_parent_commit_failure_reopens_and_recovers_one_child(
    linked, monkeypatch, write_then_lose_response
):
    flow, service, original, report, _calls = linked
    attached = attach(flow, original, report, service.root)
    request = {"task_id": attached["id"], "task_revision": attached["revision"]}
    write = application_flow.helper.atomic_write_json
    failures = []

    def failing_write(path, value):
        if path == flow.path and value["tasks"][0].get("codex_handoff_attempt") and not failures:
            failures.append(True)
            if write_then_lose_response:
                write(path, value)
            raise OSError("Synthetic parent commit lost")
        write(path, value)

    monkeypatch.setattr(application_flow.helper, "atomic_write_json", failing_write)
    with pytest.raises(OSError, match="Synthetic parent commit lost"):
        flow.request("restart-existing-handoff", request)
    child = service.snapshot()["active_task"]
    assert child["status"] == "prepared"
    if not write_then_lose_response:
        waiting = flow.snapshot(attached["id"])["active_task"]
        assert waiting["codex_handoff_restart"]["status"] == "preparing"
        assert "codex_handoff_ref" not in waiting
        assert waiting["status"] == "needs_recheck"
    flow.close()
    reopened = ApplicationFlowService(
        flow.applications, flow.root, callbacks=flow.callbacks, preparation_only=True
    )
    try:
        recovered = reopened.request("restart-existing-handoff", request)
        assert recovered["codex_handoff_attempt"]["task_id"] == child["id"]
        assert recovered["resume_sha256"] == SHA
        assert len(service.snapshot()["tasks"]) == 2
        assert len(recovered["codex_handoff_history"]) == 2
        assert "codex_handoff_restart" not in recovered
    finally:
        reopened.close()


def test_new_report_is_projected_read_only_and_can_start_another_fresh_page(linked):
    flow, service, original, report, _calls = linked
    attached = attach(flow, original, report, service.root)
    first = flow.request(
        "restart-existing-handoff",
        {"task_id": attached["id"], "task_revision": attached["revision"]},
    )
    reply = act(service, service.snapshot()["active_task"], "claim", owner="fresh-page-executor")
    child = ready(service, reply["active_task"], reply["claim_token"])
    before = (files(flow.root), files(service.root), files(flow.applications.root))

    projected = flow.snapshot(first["id"])["active_task"]
    assert projected["status"] == "ready_for_review"
    assert projected["codex_handoff_ref"]["task_id"] == child["id"]
    assert projected["codex_handoff_attempt"]["current_attempt"] is True
    assert projected["codex_handoff_attempt"]["status"] == "ready_for_review"
    assert reply["claim_token"] not in str(projected)
    assert (files(flow.root), files(service.root), files(flow.applications.root)) == before

    second = flow.request(
        "restart-existing-handoff",
        {"task_id": first["id"], "task_revision": first["revision"]},
    )
    assert second["codex_handoff_attempt"]["task_id"] != child["id"]
    assert second["resume_id"] == original["resume_id"]
    assert second["artifacts"] == original["artifacts"]
    assert len(service.snapshot()["tasks"]) == 3
    assert len(second["codex_handoff_history"]) == 3
    assert service.snapshot()["active_task"]["readbacks"] == []
    before = (files(flow.root), files(service.root))
    with pytest.raises(PortalDataError) as error:
        flow.request(
            "restart-existing-handoff",
            {"task_id": attached["id"], "task_revision": attached["revision"]},
        )
    assert error.value.code == "conflict"
    assert (files(flow.root), files(service.root)) == before


def test_legacy_attach_cannot_replace_the_current_attempt_binding(linked):
    flow, service, original, report, _calls = linked
    attached = attach(flow, original, report, service.root)
    current = flow.request(
        "restart-existing-handoff",
        {"task_id": attached["id"], "task_revision": attached["revision"]},
    )
    reply = act(service, service.snapshot()["active_task"], "claim", owner="fresh-page-executor")
    child = ready(service, reply["active_task"], reply["claim_token"])
    before = (files(flow.root), files(service.root))

    with pytest.raises(PortalDataError) as error:
        attach(flow, current, child, service.root)

    assert error.value.code == "flow_handoff_bound"
    assert (files(flow.root), files(service.root)) == before


def test_current_attempt_prevents_regeneration_or_new_flow_and_parent_cancel_retains_it(linked):
    flow, service, original, report, _calls = linked
    attached = attach(flow, original, report, service.root)
    current = flow.request(
        "restart-existing-handoff",
        {"task_id": attached["id"], "task_revision": attached["revision"]},
    )
    before = (files(service.root), files(flow.applications.root))
    application = flow.applications.get_application(original["application_id"])
    assert flow.create(application["id"], application["revision"], force_new=True) == current
    for operation, extra in [
        ("start", {"stage": "resume", "retry": True}),
        ("update-inputs", {"application_revision": application["revision"]}),
        ("import-latex", {}),
    ]:
        with pytest.raises(PortalDataError) as error:
            if operation == "import-latex":
                flow.import_latex(application["id"], application["revision"], "/unused", "main.tex")
            else:
                flow.request(
                    operation,
                    {"task_id": current["id"], "task_revision": current["revision"], **extra},
                )
        assert error.value.code == "flow_handoff_bound"
    cancelled = flow.cancel(current["id"], current["revision"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["codex_handoff_attempt"] == current["codex_handoff_attempt"]
    projected = flow.snapshot(current["id"])["active_task"]
    assert projected["status"] == "cancelled" and "codex_handoff_ref" not in projected
    assert projected["codex_handoff_attempt"]["reason"] == "flow_cancelled"
    with pytest.raises(PortalDataError):
        flow.request(
            "restart-existing-handoff",
            {"task_id": cancelled["id"], "task_revision": cancelled["revision"]},
        )
    assert (files(service.root), files(flow.applications.root)) == before
    assert flow.create(application["id"], application["revision"], force_new=True) == cancelled
    assert len(flow.snapshot()["tasks"]) == 1


def test_unknown_new_page_result_never_inherits_the_previous_upload_or_restarts(linked):
    flow, service, original, report, _calls = linked
    attached = attach(flow, original, report, service.root)
    current = flow.request(
        "restart-existing-handoff",
        {"task_id": attached["id"], "task_revision": attached["revision"]},
    )
    reply = act(service, service.snapshot()["active_task"], "claim", owner="fresh-page-executor")
    act(
        service,
        reply["active_task"],
        "readback",
        claim_token=reply["claim_token"],
        result="unknown",
        page_url=report["job_url"],
        source="Synthetic upload response lost on the new page",
        fields=[],
        attachment=None,
        missing=["Attachment result unknown"],
    )
    before = (files(flow.root), files(service.root), files(flow.applications.root))
    projected = flow.snapshot(current["id"])["active_task"]
    assert projected["status"] == "needs_recheck"
    assert projected["codex_handoff_attempt"]["status"] == "needs_recheck"
    assert "codex_handoff_ref" not in projected
    with pytest.raises(PortalDataError) as error:
        flow.request(
            "restart-existing-handoff",
            {"task_id": current["id"], "task_revision": current["revision"]},
        )
    assert error.value.code == "handoff_not_ready"
    assert (files(flow.root), files(service.root), files(flow.applications.root)) == before


def test_declared_information_root_reuses_current_facts_without_an_extra_input_scan(
    linked, tmp_path
):
    flow, service, original, report, _calls = linked
    attached = attach(flow, original, report, service.root)
    library = application_flow.helper.Store(tmp_path / "declared-information")
    library.initialize()
    library.put_answer(
        {"question": "Email", "value": "current@example.invalid", "state": "confirmed", "scope": {}}
    )
    service.answers.put_answer(
        {
            "question": "Email",
            "value": "old-private@example.invalid",
            "state": "confirmed",
            "scope": {},
        }
    )
    old_answers = service.answers.answers_path.read_bytes()
    calls = []

    def inputs(application_id):
        calls.append(application_id)
        assert len(calls) == 1, "Only the existing material validation may read inputs"
        application = flow.applications.get_application(application_id)
        return {"application_revision": application["revision"], "inputs": original["inputs"]}

    flow.close()
    reopened = ApplicationFlowService(
        flow.applications,
        flow.root,
        callbacks=flow.callbacks,
        preparation_only=True,
        input_provider=inputs,
        information_library_root=library.root,
    )
    try:
        reopened.request(
            "restart-existing-handoff",
            {"task_id": attached["id"], "task_revision": attached["revision"]},
        )
        child = service.snapshot()["active_task"]
        assert child["information_library_root"] == str(library.root)
        assert [row["value"] for row in child["answers"]] == ["current@example.invalid"]
        assert service.answers.answers_path.read_bytes() == old_answers
        assert calls == [original["application_id"]]
    finally:
        reopened.close()


def test_second_fresh_page_commit_failure_reuses_latest_observed_values_once(linked, monkeypatch):
    flow, service, original, report, _calls = linked
    attached = attach(flow, original, report, service.root)
    first = flow.request(
        "restart-existing-handoff",
        {"task_id": attached["id"], "task_revision": attached["revision"]},
    )
    reply = act(service, service.snapshot()["active_task"], "claim", owner="first-fresh-executor")
    observed = act(
        service,
        reply["active_task"],
        "readback",
        claim_token=reply["claim_token"],
        result="ready",
        page_url=report["job_url"],
        source="Synthetic current-page manual wording readback",
        fields=[{"question": "Full name", "value": "Latest observed wording"}],
        attachment={"filename": "approved.pdf", "sha256": SHA},
        missing=[],
    )["active_task"]
    request = {"task_id": first["id"], "task_revision": first["revision"]}
    write = application_flow.helper.atomic_write_json
    failures = []

    def failing_write(path, value):
        task = value.get("tasks", [{}])[0] if isinstance(value, dict) else {}
        if (
            path == flow.path
            and task.get("codex_handoff_attempt", {}).get("task_id")
            not in {None, first["codex_handoff_attempt"]["task_id"]}
            and not failures
        ):
            failures.append(True)
            raise OSError("Synthetic second commit lost")
        write(path, value)

    monkeypatch.setattr(application_flow.helper, "atomic_write_json", failing_write)
    with pytest.raises(OSError, match="Synthetic second commit lost"):
        flow.request("restart-existing-handoff", request)
    successor = service.snapshot()["active_task"]
    assert successor["reuse_context"]["predecessor_id"] == observed["id"]
    assert successor["reuse_context"]["fields"] == [
        {"question": "Full name", "value": "Latest observed wording"}
    ]
    before = service.path.read_bytes()
    recovered = flow.request("restart-existing-handoff", request)
    assert recovered["codex_handoff_attempt"]["task_id"] == successor["id"]
    assert len(recovered["codex_handoff_history"]) == 3
    assert service.path.read_bytes() == before
    assert len(service.snapshot()["tasks"]) == 3


def test_missing_declared_information_stops_without_initializing_or_replacing_it(linked, tmp_path):
    flow, service, original, report, _calls = linked
    attached = attach(flow, original, report, service.root)
    missing = tmp_path / "missing-information"
    before = files(service.root)
    flow.close()
    reopened = ApplicationFlowService(
        flow.applications,
        flow.root,
        callbacks=flow.callbacks,
        preparation_only=True,
        information_library_root=missing,
    )
    try:
        with pytest.raises(PortalDataError) as error:
            reopened.request(
                "restart-existing-handoff",
                {"task_id": attached["id"], "task_revision": attached["revision"]},
            )
        assert error.value.code == "information_library_unavailable"
        assert not missing.exists()
        assert files(service.root) == before
        assert service.snapshot()["active_task"]["id"] == report["id"]
        projected = reopened.snapshot(attached["id"])["active_task"]
        assert projected["status"] == "needs_recheck"
        assert projected["codex_handoff_restart"]["status"] == "preparing"
        assert "codex_handoff_ref" not in projected
    finally:
        reopened.close()


def test_simultaneous_same_record_requests_prepare_only_one_current_attempt(linked):
    flow, service, original, report, _calls = linked
    attached = attach(flow, original, report, service.root)
    request = {"task_id": attached["id"], "task_revision": attached["revision"]}
    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(
            threads.map(lambda _: flow.request("restart-existing-handoff", request), range(2))
        )
    assert results[0] == results[1]
    assert len(service.snapshot()["tasks"]) == 2
    assert service.snapshot()["active_task"]["id"] == results[0]["codex_handoff_attempt"]["task_id"]
