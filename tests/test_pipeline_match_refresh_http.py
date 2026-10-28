"""Real HTTP admission keeps retained materials behind the current-job guard."""

import json
from copy import deepcopy
from uuid import uuid4

from test_application_information import tree_bytes
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_match_recheck_preservation import original_fields
from test_match_recheck_preservation import retained_match as retained_match
from test_normal_match_refresh import setup_callback


def test_skipped_materials_cannot_refresh_or_recover_while_other_job_waits(
    retained_match, tmp_path
):
    _, source, job, task, sources, library, work = retained_match
    with _running_portal(
        retained_match[0].applications,
        retained_match[0].career,
        flow_root=tmp_path / "default-flow",
        worker_root=tmp_path / "default-worker",
    ) as active:
        flow = active.server.application_flow_service
        pipeline = active.server.application_pipeline_service
        assert pipeline is not None
        flow.input_provider = source.input_provider
        flow.information_provider = source.information_provider
        with flow.applications.write_lock():
            state = deepcopy(source._load())
            state["mode"] = "application"
            flow._save(state)
        setup = (active, flow, job, task, sources, library, work)
        *_, calls = setup_callback(setup)
        other = flow.snapshot()["tasks"][1]
        with pipeline._guard, flow.applications.write_lock():
            state = pipeline._load()
            state.update(
                id=uuid4().hex,
                queue_mode=True,
                status="needs_input",
                control="paused",
                active_task_id=task["id"],
                current_recommendation_id="application:" + job["id"],
                items=[
                    {
                        "recommendation_id": "application:" + job["id"],
                        "application_id": job["id"],
                        "task_id": task["id"],
                        "status": "needs_input",
                    },
                    {
                        "recommendation_id": "application:" + other["application_id"],
                        "application_id": other["application_id"],
                        "task_id": other["id"],
                        "status": "needs_input",
                    },
                ],
            )
            pipeline._save(state)
            pipeline.skip_current(request_id="retain-first-materials")
            state = pipeline._load()
            assert state["items"][0]["status"] == "skipped"
            state.update(
                active_task_id=other["id"],
                current_recommendation_id=state["items"][1]["recommendation_id"],
                status="needs_input",
                control="paused",
                wait_reason="material_facts_required",
            )
            pipeline._save(state)
        task = flow.task_snapshot(task["id"])
        original = original_fields(task)
        before = tree_bytes(flow.root)
        pipeline_before = pipeline.path.read_bytes()
        request_id = uuid4().hex
        payload = {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "request_id": request_id,
        }
        raw = json.dumps(payload).encode()
        assert active.request("POST", "/api/flow/refresh-match", body=raw)[0] == 403
        assert (
            active.request(
                "POST",
                "/api/flow/refresh-match",
                body=raw,
                headers={**active.write_headers(), "Origin": "http://unrelated.invalid"},
            )[0]
            == 403
        )
        for action, fields in [
            ("refresh-match", payload),
            (
                "start-cover-letter",
                {"task_id": task["id"], "task_revision": task["revision"], "retry": True},
            ),
            (
                "retry-material-consistency",
                {"task_id": task["id"], "task_revision": task["revision"]},
            ),
        ]:
            status, _, response = active.request(
                "POST",
                "/api/flow/" + action,
                body=json.dumps(fields).encode(),
                headers=active.write_headers(),
            )
            assert status == 409, response
            assert json.loads(response)["error"] == "pipeline_current_material_required"
        assert calls == []
        assert tree_bytes(flow.root) == before
        assert pipeline.path.read_bytes() == pipeline_before
        assert original_fields(flow.task_snapshot(task["id"])) == original
        assert active.request("GET", "/api/pipeline/state")[0] == 200
        pipeline.return_to(job["id"], request_id="return-retained-materials")
        assert pipeline.snapshot()["active_task_id"] == task["id"]
        stale = {**payload, "task_revision": "stale"}
        assert (
            active.request(
                "POST",
                "/api/flow/refresh-match",
                body=json.dumps(stale).encode(),
                headers=active.write_headers(),
            )[0]
            == 409
        )
        assert calls == []
        for _ in range(2):
            status, _, response = active.request(
                "POST",
                "/api/flow/refresh-match",
                body=raw,
                headers=active.write_headers(),
            )
            assert status == 200, response
        assert len(calls) == 1
        assert original_fields(flow.task_snapshot(task["id"])) == original
