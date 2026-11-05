"""Read an Indeed job in the App's own Chrome when a direct read is refused (2026-11-05).

Indeed answers the plain job-source read with 401. A visible system Chrome with
the logins saved through the App opens the job page once, as a person would; the
page's own view-job model names the title, company, location, description and
apply route. A verification page is never answered: the window stays open for the
user until the time limit, then the job keeps its refused receipt.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from . import job_listing_links
from .application_automation import recommendation_key
from .application_job_source import _finish, _text, fetch_job_source
from .cua_driver import load_login_state

# Long enough for the user to finish a verification Indeed shows in the window.
PAGE_WAIT_MS = 120_000
ROUTES = {"indeed_apply", "company_site"}


class VerificationRequired(Exception):
    """Indeed kept its verification page; only the user may complete it."""


def indeed_job_key(url) -> str | None:
    key = recommendation_key(url)
    return key[1] if key and key[0] == "indeed" else None


def fetch_job_source_or_browser(url, *, read=None):
    """The direct read, or for a refused Indeed job the page read in the App's Chrome."""
    capture = fetch_job_source(url)
    job_key = indeed_job_key(capture.get("url"))
    if (
        job_key is None
        or capture.get("jd_completeness") == "full"
        or capture.get("acquisition_status") != "login_required"
        or (read is None and job_listing_links.LOGIN_ROOT is None)
    ):
        return capture
    host = urlsplit(capture["url"]).hostname
    try:
        model = (read or _read_in_browser)(f"https://{host}/viewjob?jk={job_key}")
    except Exception as error:  # noqa: BLE001 - a routine page failure stays a receipt.
        # The refused receipt keeps why the browser read failed.
        failed = {"browser_error": f"{type(error).__name__}: {error}"[:300]}
        if isinstance(error, VerificationRequired):
            failed["error_code"] = "verification_required"
        return _finish(capture | failed)
    return indeed_capture(capture, model, job_key)


def indeed_capture(capture: dict, model, job_key: str) -> dict:
    """Turn Indeed's view-job model into a job-posting receipt; else keep the receipt."""
    try:
        info = model["jobInfoWrapperModel"]["jobInfoModel"]
        header = info["jobInfoHeaderModel"]
        same = str(model.get("jobKey", "")).casefold() == job_key
    except (KeyError, TypeError):
        return capture
    if not same:
        return capture
    result = {
        key: capture[key]
        for key in ("capture_id", "url", "final_url", "redirects")
        if key in capture
    } | {"reader": "app_browser", "source_format": "page", "jd_completeness": "unknown"}
    if info.get("showExpiredHeader") or info.get("expiredJobMetadataModel"):
        return _finish(
            result | {"body_text": "", "acquisition_status": "expired", "job_fields": {}}
        )
    description = info.get("sanitizedJobDescription")
    values = [header.get(key) for key in ("jobTitle", "companyName")]
    if not all(isinstance(value, str) and value.strip() for value in (description, *values)):
        return capture
    description, title, company = _text(description), _text(values[0]), _text(values[1])
    if not all((description, title, company)):
        return capture
    link = (model.get("viewJobButtonLinkContainerModel") or {}).get("viewJobButtonLinkModel") or {}
    route = (
        "indeed_apply"
        if model.get("indeedApplyButtonContainer")
        else "company_site"
        if isinstance(link.get("href"), str) and link["href"]
        else ""
    )
    fields = {"title": title, "company": company}
    location = header.get("formattedLocation")
    if isinstance(location, str) and location.strip():
        fields["location"] = _text(location)
        if fields["location"].casefold() not in description.casefold():
            description += f"\n\nJob location\n{fields['location']}"
    if route:
        fields["indeed_apply_route"] = route
    return _finish(
        result
        | {
            "body_text": description,
            "acquisition_status": "available",
            "jd_completeness": "full",
            "source_format": "job_posting",
            "job_fields": fields,
        }
    )


def apply_route(record: dict | None) -> str:
    """'indeed_apply', 'company_site' or '' as the saved Indeed page named it."""
    fields = (record or {}).get("documentary_fields") or {}
    route = fields.get("indeed_apply_route")
    return route if route in ROUTES else ""


def _read_in_browser(url: str):
    from playwright.sync_api import TimeoutError, sync_playwright  # noqa: A004

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=False)
        try:
            saved = load_login_state(job_listing_links.LOGIN_ROOT)
            context = browser.new_context(**({"storage_state": saved} if saved else {}))
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_function(
                    "() => window._initialData?.viewJobClientSideModel?.jobKey",
                    timeout=PAGE_WAIT_MS,
                )
            except TimeoutError as error:
                # Cloudflare's check usually clears by itself; one that stays needs the user.
                if "__cf_chl" in page.url or page.title().casefold() == "just a moment...":
                    raise VerificationRequired(page.url.split("?", 1)[0]) from error
                raise
            return page.evaluate("() => window._initialData.viewJobClientSideModel")
        finally:
            browser.close()
