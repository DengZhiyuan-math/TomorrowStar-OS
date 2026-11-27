"""Read an eFinancialCareers job once in the App's own Chrome (2026-11-27, user decision).

eFinancialCareers refuses the plain job-source read (403/405). The job page opened
in a visible Chrome, as a person would, carries the job and its application data
in Angular's ``ng-state`` script: title, company, location, description and, for
an external application, the employer's own application page.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from . import job_listing_links
from .application_automation import recommendation_key
from .application_job_source import _finish, _text
from .cua_driver import load_login_state

PAGE_WAIT_MS = 20_000
_STATE_JS = (
    "() => { const node = document.getElementById('ng-state');"
    " return node ? JSON.parse(node.textContent) : null; }"
)


def efinancialcareers_job_key(url) -> str | None:
    key = recommendation_key(url)
    return key[1] if key and key[0] == "efinancialcareers" else None


def internal_apply(record: dict | None) -> bool:
    """A read eFinancialCareers job that names no external application page is
    applied for on eFinancialCareers itself (2026-11-27, user decision: skipped)."""
    fields = (record or {}).get("documentary_fields") or {}
    return bool(
        efinancialcareers_job_key((record or {}).get("url"))
        and fields.get("title")
        and not fields.get("employer_apply_url")
    )


def read_efinancialcareers_job(url, *, read=None) -> dict:
    """One job-page read in the App's Chrome, as a job-source receipt."""
    job_id = efinancialcareers_job_key(url)
    parts = urlsplit(url)
    page_url = f"https://{parts.hostname}{parts.path}"
    capture = {
        "capture_id": uuid4().hex,
        "url": url,
        "final_url": page_url,
        "body_text": "",
        "acquisition_status": "unavailable",
        "jd_completeness": "unknown",
        "source_format": "page",
        "redirects": [],
        "job_fields": {},
        "reader": "app_browser",
    }
    try:
        state = (read or _read_in_browser)(page_url)
    except Exception as error:  # noqa: BLE001 - a routine page failure stays a receipt.
        capture.update(
            error_code="browser_error", browser_error=f"{type(error).__name__}: {error}"[:300]
        )
        return _finish(capture)
    return efinancialcareers_capture(capture, state, job_id)


def _body(state: dict, prefix: str) -> dict:
    entry = next((value for key, value in state.items() if key.startswith(prefix)), None)
    data = ((entry or {}).get("body") or {}).get("data") if isinstance(entry, dict) else None
    return data if isinstance(data, dict) else {}


def efinancialcareers_capture(capture: dict, state, job_id: str) -> dict:
    """Turn the page's job data into a receipt; an unreadable page stays one."""
    if not isinstance(state, dict):
        return _finish(capture)
    job = _body(state, f"https://job-branding-facade.efinancialcareers.com/job/{job_id}")
    if not job:
        return _finish(capture)
    expires = str(job.get("expiration_date") or "")
    with suppress(ValueError):
        if expires and datetime.fromisoformat(expires.replace("Z", "+00:00")) < datetime.now(UTC):
            return _finish(capture | {"acquisition_status": "expired"})
    description = _text(str(job.get("description") or ""))
    title = _text(str(job.get("title") or ""))
    company = _text(str((job.get("brand") or {}).get("name") or ""))
    if not all((description, title, company)):
        return _finish(capture)
    fields = {"title": title, "company": company}
    place = job.get("location") or {}
    location = ", ".join(str(place[key]) for key in ("city", "country") if place.get(key))
    if location:
        fields["location"] = location
        if location.casefold() not in description.casefold():
            description += f"\n\nJob location\n{location}"
    apply = _body(state, f"https://job-application.efinancialcareers.com/v1/jobs/{job['jobId']}")
    target = apply.get("external_job_application_url")
    if apply.get("is_external_job_application") and str(target or "").startswith("https://"):
        # The employer's own application page, as an Indeed company-site job keeps it.
        fields |= {"employer_apply_url": target, "employer_found_by": "efinancialcareers"}
    return _finish(
        capture
        | {
            "body_text": description,
            "acquisition_status": "available",
            "jd_completeness": "full",
            "source_format": "job_posting",
            "job_fields": fields,
        }
    )


def _read_in_browser(url: str):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=False)
        try:
            saved = load_login_state(job_listing_links.LOGIN_ROOT)
            context = browser.new_context(**({"storage_state": saved} if saved else {}))
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_function(_STATE_JS, timeout=PAGE_WAIT_MS)
            return page.evaluate(_STATE_JS)
        finally:
            browser.close()
