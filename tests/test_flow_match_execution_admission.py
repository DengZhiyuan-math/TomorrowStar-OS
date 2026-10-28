"""Match refresh shares physical job ownership with preparation stages and root aliases."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from test_application_flow import wait_for
from test_career_portal_http import portal as portal
from test_match_recheck_preservation import original_fields
from test_match_recheck_preservation import retained_match as retained_match
from test_normal_match_refresh import setup_callback

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_match_refresh import match_refresh_running
from career_evidence_graph.career_portal_data import PortalDataError


def post(active, action, payload):
    status, _, raw = active.request(
        "POST",
        "/api/flow/" + action,
        body=json.dumps(payload).encode(),
        headers=active.write_headers(),
    )
    return status, json.loads(raw)


@pytest.mark.parametrize("variant", ["exact", "case_alias", "different_root"])
def test_actual_root_identity_preserves_only_same_directory_callback_ownership(
    retained_match, variant, tmp_path
):
    _, original, _, task, *_ = retained_match
    setup_callback(retained_match)
    callback = original.callbacks["refresh_match"]
    entered, release, analysis_entered = Event(), Event(), Event()
    calls = []
    alias = original.root
    if variant == "case_alias":
        alias = original.root.with_name(original.root.name.upper())
        if alias == original.root or not alias.exists() or not alias.samefile(original.root):
            pytest.skip("Requires a real case-insensitive directory alias")
        assert str(alias.resolve()) != str(original.root.resolve())
        assert (alias / ".flow.lock").samefile(original.root / ".flow.lock")
    elif variant == "different_root":
        alias = tmp_path / "separate-preparation"

    def refresh(*args, **kwargs):
        entered.set()
        assert release.wait(15)
        return callback(*args, **kwargs)

    def analyze(request):
        calls.append(request["id"])
        analysis_entered.set()
        raise PortalDataError("synthetic_analysis_stop", "No real model", 409)

    original.callbacks["refresh_match"] = refresh
    replacement = None
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(original.refresh_match, task["id"], task["revision"], uuid4().hex)
        try:
            assert entered.wait(5)
            if variant != "different_root":
                original.close()
            replacement = ApplicationFlowService(
                original.applications,
                alias,
                callbacks={"analysis": analyze},
                input_provider=original.input_provider,
                information_provider=original.information_provider,
                recheck_source_provider=original.recheck_source_provider,
                preparation_only=original.preparation_only,
            )
            assert replacement._owner
            if variant == "different_root":
                other = original.applications.create_application(
                    {
                        "company": "Separate Synthetic Employer",
                        "role_title": "Engineer",
                        "job_description": "Build reliable Python systems.",
                    }
                )
                target = replacement.create(other["id"], other["revision"])
                assert not alias.samefile(original.root)
                assert not match_refresh_running(replacement)
                replacement.start(target["id"], target["revision"], "analysis")
                assert analysis_entered.wait(5)
            else:
                assert alias.samefile(original.root)
                assert match_refresh_running(replacement)
                target = next(
                    row for row in replacement.snapshot()["tasks"] if row["id"] != task["id"]
                )
                before = replacement.task_snapshot(target["id"])
                with pytest.raises(PortalDataError) as blocked:
                    replacement.start(target["id"], target["revision"], "analysis")
                assert blocked.value.code == "match_refresh_other_job_running"
                assert calls == []
                assert replacement.task_snapshot(target["id"]) == before
        finally:
            release.set()
        try:
            if variant == "different_root":
                assert pending.result(timeout=10)["id"] == task["id"]
            else:
                with pytest.raises(PortalDataError):
                    pending.result(timeout=10)
                assert not match_refresh_running(replacement)
                target = replacement.task_snapshot(target["id"])
                replacement.start(target["id"], target["revision"], "analysis")
                assert analysis_entered.wait(5)
        finally:
            if replacement:
                replacement.close()


@pytest.mark.parametrize("entry", ["direct", "http"])
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("stage", ["analysis", "resume"])
def test_fresh_match_waits_for_other_physical_stage_and_preserves_saved_reads(
    retained_match, entry, cancel, stage
):
    active, flow, _, task, *_ = retained_match
    assert flow.preparation_only and active.server.application_pipeline_service is None
    setup_callback(retained_match)
    callback = flow.callbacks["refresh_match"]
    # This known result remains a read-only/idempotent route during other work.
    saved_id = uuid4().hex
    task = flow.refresh_match(task["id"], task["revision"], saved_id)
    other = next(row for row in flow.snapshot()["tasks"] if row["id"] != task["id"])
    if stage == "resume":
        flow.start(other["id"], other["revision"], "analysis")
        other = wait_for(flow, other["id"], lambda row: row["status"] == "analysis_ready")
    entered, release = Event(), Event()
    match_calls = []

    def work(request):
        entered.set()
        assert release.wait(15)
        raise PortalDataError("synthetic_stage_stop", "No real model", 409)

    def refresh(*args, **kwargs):
        match_calls.append(args)
        return callback(*args, **kwargs)

    flow.callbacks[stage] = work
    flow.callbacks["refresh_match"] = refresh
    if entry == "http":
        status, response = post(
            active,
            "start",
            {
                "task_id": other["id"],
                "task_revision": other["revision"],
                "stage": stage,
            },
        )
        assert status == 200, response
    else:
        flow.start(other["id"], other["revision"], stage)
    request_id = uuid4().hex
    try:
        assert entered.wait(5)
        if cancel:
            other = flow.task_snapshot(other["id"])
            if entry == "http":
                status, response = post(
                    active,
                    "cancel",
                    {
                        "task_id": other["id"],
                        "task_revision": other["revision"],
                    },
                )
                assert status == 200, response
            else:
                flow.cancel(other["id"], other["revision"])
            assert flow.task_snapshot(other["id"])["stages"][stage]["status"] == "cancelled"
        before = flow.witness(task["id"])[1]
        assert flow.refresh_match(task["id"], before["revision"], saved_id)["id"] == task["id"]
        assert match_calls == []
        if entry == "http":
            status, rejected = post(
                active,
                "refresh-match",
                {
                    "task_id": task["id"],
                    "task_revision": before["revision"],
                    "request_id": request_id,
                },
            )
            assert status == 409, rejected
            assert rejected["error"] == "flow_other_job_running"
        else:
            with pytest.raises(PortalDataError) as rejected:
                flow.refresh_match(task["id"], before["revision"], request_id)
            assert rejected.value.code == "flow_other_job_running"
        assert match_calls == []
        assert flow.witness(task["id"])[1] == before
        assert not (flow.root / "match-refreshes" / request_id).exists()
        assert active.request("GET", "/api/flow/state")[0] == 200
    finally:
        release.set()
    if not cancel:
        wait_for(flow, other["id"], lambda row: row["stages"][stage]["status"] == "failed")
    deadline = time.monotonic() + 5
    while True:
        latest = flow.task_snapshot(task["id"])
        try:
            returned = flow.refresh_match(task["id"], latest["revision"], request_id)
            break
        except PortalDataError as error:
            assert cancel and error.code == "flow_other_job_running"
            assert time.monotonic() < deadline
            time.sleep(0.01)
    assert returned["id"] == task["id"]
    assert len(match_calls) == 1
    assert original_fields(flow.witness(task["id"])[1]) == original_fields(task)


@pytest.mark.parametrize("branch", ["cover_letter", "material_consistency"])
def test_fresh_match_waits_for_other_material_callback(retained_match, branch):
    from test_application_cover_letter_flow import material

    from career_evidence_graph.application_resume import validate_prepared_result

    active, flow, _, task, *_ = retained_match
    setup_callback(retained_match)
    callback = flow.callbacks["refresh_match"]
    other = next(row for row in flow.snapshot()["tasks"] if row["id"] != task["id"])
    entered, release = Event(), Event()
    matches = []

    def analysis(request):
        return {
            "id": "fixed-other-analysis",
            "application_id": request["application_id"],
            "job_brief": {"requirements": []},
            "material_packet": {"sources": {}},
            "inference_result": {},
        }

    def letter(request):
        if branch == "cover_letter":
            entered.set()
            assert release.wait(15)
        return material(request)

    def consistency(request):
        entered.set()
        assert release.wait(15)
        return {
            "status": "passed",
            **{
                key: request["material_consistency"][key]
                for key in ("resume_content_revision", "letter_content_revision")
            },
        }

    def refresh(*args, **kwargs):
        matches.append(args)
        return callback(*args, **kwargs)

    flow.callbacks.update(
        analysis=analysis,
        cover_letter=letter,
        material_consistency=consistency,
        resume=lambda request: {
            "id": "synthetic-other-draft",
            "kind": "draft",
            "draft_sha256": "a" * 64,
            "content_revision": "c" * 64,
            "resume_content": {"revision": "c" * 64},
        },
        # This scheduling fixture supplies an in-memory material owner alongside
        # its synthetic draft; archive integrity is covered by Resume tests.
        verify_prepared_resume=validate_prepared_result,
        refresh_match=refresh,
    )
    flow.start(other["id"], other["revision"], "analysis")
    other = wait_for(flow, other["id"], lambda row: row["status"] == "analysis_ready")
    flow.start(other["id"], other["revision"], "resume")
    try:
        assert entered.wait(5)
        wait_for(flow, other["id"], lambda row: row["status"] == "draft_ready")
        assert flow.task_snapshot(other["id"])[branch]["status"] == "running"
        before = flow.witness(task["id"])[1]
        identifier = uuid4().hex
        with pytest.raises(PortalDataError) as rejected:
            flow.refresh_match(task["id"], before["revision"], identifier)
        assert rejected.value.code == "letter_other_job_pending"
        assert not (flow.root / "match-refreshes" / identifier).exists()
        assert flow.witness(task["id"])[1] == before
        assert matches == []
        assert active.request("GET", "/api/flow/state")[0] == 200
    finally:
        release.set()
    wait_for(
        flow, other["id"], lambda row: row.get("material_consistency", {}).get("status") == "passed"
    )
    latest = flow.task_snapshot(task["id"])
    assert flow.refresh_match(task["id"], latest["revision"], identifier)["id"] == task["id"]
    assert len(matches) == 1
