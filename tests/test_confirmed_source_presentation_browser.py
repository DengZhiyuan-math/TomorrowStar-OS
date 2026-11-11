"""Human explanations retain facts while internal citation bindings remain in the API."""

import json

import pytest
from test_career_portal_http import portal as portal
from test_job_explanation_browser import (
    explanation_portal,
    open_internal_management,
    reveal_control,
    select_saved_job,
)
from test_job_explanation_browser import (
    isolated_model_context as isolated_model_context,
)
from test_portal_workflow_browser import browser_page as browser_page

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_information import put_information_answer
from career_evidence_graph.career_portal_data import ApplicationStore

pytestmark = pytest.mark.worker_browser


def test_fact_citation_ids_stay_internal_when_matching_details_are_expanded(
    portal, tmp_path, browser_page
):
    from playwright.sync_api import expect

    store = helper.Store(tmp_path / "information")
    record = put_information_answer(
        store,
        {"question": "English fluency", "value": "professional", "state": "confirmed", "scope": {}},
    )
    ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Be fluent in English.",
        }
    )
    requirement = {
        "text": "Be fluent in English.",
        "importance": "required",
        "judgment": "unknown",
        "hard_condition": True,
        "explanation": "Applicant fact is unknown.",
        "source_ids": [],
        "citations": [],
        "claim_scope": "unknown",
    }
    page = browser_page
    with explanation_portal(
        portal,
        tmp_path,
        extra_requirements={"Synthetic": [requirement]},
        information_library_root=store.root,
    ) as (instance, _):
        page.goto(instance.origin + "/#flow")
        open_internal_management(page)
        select_saved_job(
            page, page.locator("#flow-saved-jobs").get_by_role("button", name="选择已有岗位")
        )
        reveal_control(page, "#flow-start-analysis")
        page.locator("#flow-start-analysis").click()
        reveal_control(page, "#flow-fit-details")
        page.locator("#flow-fit-details > summary").click()
        row = page.locator(".flow-requirement").filter(
            has=page.get_by_role("heading", name="Be fluent in English.", exact=True)
        )
        expect(row).to_contain_text("已复用信息库中适用且已确认的英语流利度答案。")
        status, _, raw = instance.request("GET", "/api/flow/state")
        assert status == 200
        explanation = json.loads(raw)["active_explanation"]
        references = next(
            reason["library"]["references"]
            for reason in explanation["reasons"]
            if reason["text"] == "Be fluent in English."
        )
        assert references[0]["key"] == record["key"]
        assert len(references[0]["revision"]) == 64
        expect(row).not_to_contain_text(references[0]["key"])
        expect(row).not_to_contain_text(references[0]["revision"])
        expect(row).to_contain_text("依据：信息库中已确认的资料。")
