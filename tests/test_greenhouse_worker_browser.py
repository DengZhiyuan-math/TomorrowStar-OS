"""Greenhouse rounds share the Lever process, HTTP harness and answer library."""

from __future__ import annotations

import base64
import hashlib
import time
from pathlib import Path

import pytest
from worker_preview_support import running_preview, stop_worker

from career_evidence_graph.application_worker import digest, fact_for

pytestmark = pytest.mark.worker_browser


def seed_qualifications(p) -> None:
    for country in ("CHE", "USA"):
        p.seed("Are you currently authorized to work in this country?", "Yes", {"country": country})


def test_greenhouse_round_1_fields_attachments_and_handoff(tmp_path: Path) -> None:
    with running_preview(tmp_path, 2, ("greenhouse",) * 2) as p:
        seed_qualifications(p)
        p.seed("Will you now or in the future require visa sponsorship?", "No", {"country": "CHE"})
        items = p.prepare(["CHE", "CHE"])
        p.post("resume", controller=p.controller)
        state = p.wait(lambda s: all(j["status"] == "ready_for_review" for j in s["jobs"]))
        assert all(j["platform"] == "greenhouse" for j in state["jobs"])
        assert state["input_items"] == []
        assert {e["sha256"] for e in p.events()["uploads"]} == {
            hashlib.sha256(base64.b64decode(i["file_base64"])).hexdigest() for i in items
        }
        for job in state["jobs"]:
            refs = {r["field_id"]: r for r in job["answer_refs"]}
            assert set(refs) == {
                "first_name",
                "last_name",
                "email",
                "question_1001",
                "question_1002",
            }
            assert refs["question_1001"]["fact"] == "sponsorship_now_future"
            assert refs["question_1002"]["fact"] == "work_authorization_now"
        assert all(a["status"] == "drafting" for a in p.get("/api/state")["applications"])
        p.post("review", application_id=state["jobs"][0]["application_id"])
        state = p.wait(lambda s: s["jobs"][0]["handed_off"])
        p.post("pause", controller=p.controller)
        assert p.get("/api/worker/state")["jobs"][0]["page_open"]
        assert len(p.events()["uploads"]) == 2 and p.events()["submissions"] == []
        p.report(
            "greenhouse-round-1-complete",
            state,
            [
                "shared_independent_process",
                "separate_confirmed_first_last_names",
                "numeric_option_values_label_readback",
                "authorization_not_sponsorship",
                "per_job_file_digest",
                "manual_handoff",
                "pause_retains_page",
                "zero_final_actions",
            ],
        )


def test_greenhouse_round_2_cross_platform_answer_loop(tmp_path: Path) -> None:
    with running_preview(tmp_path, 3, ("lever", "greenhouse", "greenhouse")) as p:
        seed_qualifications(p)
        p.seed("Will you now or in the future require visa sponsorship?", "No", {"country": "USA"})
        p.prepare(["USA", "CHE", "CHE"])
        p.post("resume", controller=p.controller)
        state = p.wait(
            lambda s: (
                [j["status"] for j in s["jobs"]]
                == [
                    "ready_for_review",
                    "needs_input",
                    "needs_input",
                ]
            )
        )
        assert [j["platform"] for j in state["jobs"]] == ["greenhouse", "greenhouse", "lever"]
        assert len(state["input_items"]) == 1
        assert len(state["input_items"][0]["jobs"]) == 2
        before_uploads = p.events()["uploads"]
        assert len(before_uploads) == 3
        assert len({row["id"] for row in before_uploads}) == 3
        p.post("pause", controller=p.controller)
        p.post(
            "answer",
            application_id=state["jobs"][1]["application_id"],
            question_id="question_1001",
            value="Yes",
            scope={"country": "CHE"},
        )
        paused = p.get("/api/worker/state")
        assert paused["control"] == "paused"
        assert [j["status"] for j in paused["jobs"]] == ["ready_for_review", "queued", "queued"]
        time.sleep(0.6)
        assert p.events()["uploads"] == before_uploads
        p.post("resume", controller=p.controller)
        p.wait(lambda s: all(j["status"] == "ready_for_review" for j in s["jobs"]))
        sponsor = next(
            r
            for r in p.store.library()
            if fact_for(r["question"]) == "sponsorship_now_future"
            and r["scope"] == {"country": "CHE"}
        )
        p.post("library", key=sponsor["key"], revision=digest(sponsor), value="No")
        changed = p.wait(
            lambda s: (
                [j["status"] for j in s["jobs"]]
                == [
                    "ready_for_review",
                    "needs_recheck",
                    "needs_recheck",
                ]
            )
        )
        revised = p.store.answers.get_answer(sponsor["key"])
        for job in changed["jobs"][1:]:
            p.post("recheck", application_id=job["application_id"], acknowledge=True)
        state = p.wait(
            lambda s: (
                [j["status"] for j in s["jobs"]]
                == ["ready_for_review", "needs_input", "needs_input"]
            )
        )
        # This retained legacy batch has no current-job choice authority.
        # Recheck observes both differences; it cannot authorize replacing Yes.
        for job in state["jobs"][1:]:
            assert job["reason"] == "form_differences"
            form = job["form_state"]
            assert len(form["differences"]) == 1
            difference = form["differences"][0]
            assert difference["current_value"] == "Yes"
            assert difference["proposed_value"] == "No"
            assert form["snapshot"]["fields"]
            field = next(
                row for row in form["snapshot"]["fields"] if row["id"] == difference["field_id"]
            )
            assert field["value"] == "Yes"
            refs = [r for r in job["answer_refs"] if r["fact"] == "sponsorship_now_future"]
            assert all(ref["revision"] == digest(sponsor) != digest(revised) for ref in refs)
            assert difference["source"]["revision"] == digest(revised)
        assert p.events()["uploads"] == before_uploads and p.events()["submissions"] == []
        p.report(
            "greenhouse-round-2-shared-answers",
            state,
            [
                "one_library_for_two_platforms",
                "same_country_equivalent_questions_group",
                "different_country_not_reused",
                "answer_saved_while_paused_only_queues",
                "automatic_waiting_resume",
                "legacy_recheck_preserves_nonempty_values_and_reports_both_differences",
                "no_duplicate_upload",
                "zero_final_actions",
            ],
        )


def test_greenhouse_round_3_new_required_question_and_restart(tmp_path: Path) -> None:
    with running_preview(tmp_path, 1, ("greenhouse",)) as p:
        seed_qualifications(p)
        p.seed("Will you now or in the future require visa sponsorship?", "No", {"country": "CHE"})
        app = p.store.applications.list_applications()[0]
        p.server.worker_fixtures.fixture_overrides[app["id"]] = {"new_required_after_upload": True}
        p.prepare(["CHE"])
        p.post("resume", controller=p.controller)
        state = p.wait(lambda s: s["jobs"][0]["status"] == "needs_input")
        assert [q["id"] for q in state["jobs"][0]["questions"]] == ["notice_period"]
        assert len(p.events()["uploads"]) == 1
        p.post(
            "answer",
            application_id=app["id"],
            question_id="notice_period",
            value="30",
            only_this=True,
        )
        p.wait(lambda s: s["jobs"][0]["status"] == "ready_for_review")
        notice = [r for r in p.store.library() if r["question"] == "Notice period in days"]
        assert len(notice) == 1
        assert notice[0]["value"] == "30"
        assert notice[0]["scope"] == {"application_id": app["id"]}
        assert len(p.events()["uploads"]) == 1
        stop_worker(p)
        p.worker.spawn()
        state = p.wait(
            lambda s: s["control"] == "paused" and s["jobs"][0]["status"] == "needs_recheck"
        )
        assert state["jobs"][0]["reason"] == "worker_restarted"
        time.sleep(0.4)
        assert len(p.events()["uploads"]) == 1 and p.events()["submissions"] == []
        p.report(
            "greenhouse-round-3-dynamic-recovery",
            state,
            [
                "new_required_field_returns_to_input_loop",
                "one_use_not_in_library",
                "resume_not_uploaded_twice",
                "restart_requires_explicit_recheck",
                "zero_final_actions",
            ],
        )


@pytest.mark.parametrize(
    "control,reason,uploads",
    [
        ("extra_attachment", "unsupported_attachments", 0),
        ("unsupported_control", "unsupported_structure", 0),
        ("wrong_upload_digest", "action_result_unknown", 1),
        ("upload_error", "action_result_unknown", 1),
        ("identity_changed_after_upload", "identity_changed", 1),
    ],
)
def test_greenhouse_fault_stops_only_affected_job(tmp_path: Path, control, reason, uploads) -> None:
    with running_preview(tmp_path, 2, ("greenhouse",) * 2) as p:
        seed_qualifications(p)
        p.seed("Will you now or in the future require visa sponsorship?", "No", {"country": "CHE"})
        first = p.store.applications.list_applications()[0]
        p.server.worker_fixtures.fixture_overrides[first["id"]] = {control: True}
        p.prepare(["CHE", "CHE"])
        p.post("resume", controller=p.controller)
        state = p.wait(
            lambda s: (
                [j["status"] for j in s["jobs"]]
                == [
                    "needs_recheck",
                    "ready_for_review",
                ]
            )
        )
        assert state["jobs"][0]["reason"] == reason
        assert state["jobs"][0]["page_open"]
        if uploads:
            assert state["jobs"][0]["intent"]["action"] == "upload"
        assert len(p.events()["uploads"]) == 1 + uploads
        time.sleep(0.5)
        assert len(p.events()["uploads"]) == 1 + uploads
        assert p.events()["submissions"] == []


def test_greenhouse_full_name_does_not_supply_unknown_name_parts(tmp_path: Path) -> None:
    with running_preview(tmp_path, 1, ("greenhouse",)) as p:
        for record in p.store.library():
            if fact_for(record["question"]) in {"first_name", "last_name"}:
                p.post("library", key=record["key"], revision=digest(record), withdraw=True)
        seed_qualifications(p)
        p.seed("Will you now or in the future require visa sponsorship?", "No", {"country": "CHE"})
        p.prepare(["CHE"])
        p.post("resume", controller=p.controller)
        state = p.wait(lambda s: s["jobs"][0]["status"] == "needs_input")
        assert {q["id"] for q in state["jobs"][0]["questions"]} == {"first_name", "last_name"}
        uploads_before = p.events()["uploads"]
        assert len(uploads_before) == 1
        for key, value in (("first_name", "Confirmed Given"), ("last_name", "Confirmed Family")):
            p.post(
                "answer",
                application_id=state["jobs"][0]["application_id"],
                question_id=key,
                value=value,
            )
        p.wait(lambda s: s["jobs"][0]["status"] == "ready_for_review")
        assert p.events()["uploads"] == uploads_before and p.events()["submissions"] == []
