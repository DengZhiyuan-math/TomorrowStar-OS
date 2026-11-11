"""Real imported-LaTeX checkpoints with an injected local compiler for UI tests."""

from contextlib import contextmanager

from test_job_explanation_browser import explanation_portal
from test_pdf_export_http import SyntheticLatexClient, create_authorized_latex

from career_evidence_graph.career_portal_data import ApplicationStore


@contextmanager
def authorized_latex_portal(portal, tmp_path, *, count=1):
    applications = ApplicationStore(portal.applications)
    jobs = [
        applications.create_application(
            {
                "company": f"Synthetic {index + 1}",
                "role_title": "Engineer",
                "job_description": f"Build Python services. JOB_{index + 1}",
            }
        )
        for index in range(count)
    ]
    with explanation_portal(portal, tmp_path) as (active, work):
        store = active.server.application_resume_store
        store.prism_client = SyntheticLatexClient(lambda: work["exports"].append("compile"))
        tasks = [create_authorized_latex(active, job) for job in jobs]
        yield active, jobs, tasks, work


def review_all_groups(page):
    """Review each actual saved group after a real local technical preview."""
    from playwright.sync_api import expect
    from test_job_explanation_browser import reveal_control

    reveal_control(page, "#flow-begin-group-review")
    page.locator("#flow-begin-group-review").click()
    expect(page.locator("#flow-capture-group-review")).to_be_enabled()
    page.locator("#flow-capture-group-review").click()
    expect(page.locator("#flow-grouped-review iframe")).to_be_visible()
    buttons = page.locator("[data-group-review]")
    identifiers = [button.get_attribute("data-group-review") for button in buttons.all()]
    assert identifiers
    for index, identifier in enumerate(identifiers):
        review = page.locator(f'[data-group-review="{identifier}"]')
        reveal_control(page, review)
        expect(review).to_be_enabled()
        review.click()
        expect(page.get_by_text("此组当前版本已确认。", exact=True)).to_have_count(index + 1)
        expect(page.locator("#flow-root")).to_have_attribute("aria-busy", "false")
        expect(review).to_be_disabled()
    expect(page.locator("#flow-draft")).to_contain_text("经历组已审核")
