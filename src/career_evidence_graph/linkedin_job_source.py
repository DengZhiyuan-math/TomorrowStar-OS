"""Read a LinkedIn job once in the App's own Chrome (2026-11-20, user decision).

The plain job-source read identified itself as a script and was followed by a
second logged-in read before matching; LinkedIn answered both with 429. The job
page is now opened once in a visible Chrome with the logins saved through the
App, as a person would, and that one read names the JD, title, company,
location and apply route (company site, Easy Apply or closed).

LinkedIn's page markup is obfuscated, so the reader goes by visible structure:
the top card's first lines, the "About the job" block and the apply control.
"""

from __future__ import annotations

from contextlib import suppress
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from . import job_listing_links
from .application_automation import recommendation_key
from .application_job_source import _finish, _text
from .cua_driver import load_login_state

PAGE_WAIT_MS = 20_000

_PAGE_JS = """() => {
  const main = document.querySelector('main') || document.body;
  const lines = main.innerText.split('\\n').map(line => line.trim()).filter(Boolean);
  const about = Array.from(document.querySelectorAll('h2'))
    .find(heading => /^About the job$/i.test(heading.innerText.trim()));
  let block = about;
  while (block && block.innerText.trim().length < 200) block = block.parentElement;
  const apply = Array.from(main.querySelectorAll('a, button')).map(control => ({
    text: control.innerText.trim(),
    label: control.getAttribute('aria-label') || '',
    href: control.getAttribute('href') || '',
  })).filter(control => /apply|bewerb/i.test(control.label + ' ' + control.text.slice(0, 30)));
  return {top: lines.slice(0, 12), description: block ? block.innerText : '', apply};
}"""


def linkedin_job_key(url) -> str | None:
    key = recommendation_key(url)
    return key[1] if key and key[0] == "linkedin" else None


def read_linkedin_job(url, *, read=None) -> dict:
    """One job-page read in the App's Chrome, as a job-source receipt."""
    job_id = linkedin_job_key(url)
    page_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
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
        page = (read or _read_in_browser)(page_url)
    except Exception as error:  # noqa: BLE001 - a routine page failure stays a receipt.
        capture.update(
            error_code="browser_error", browser_error=f"{type(error).__name__}: {error}"[:300]
        )
        return _finish(capture)
    return linkedin_capture(capture, page)


def linkedin_capture(capture: dict, page: dict) -> dict:
    """Turn what the job page showed into a receipt; an unreadable page stays one."""
    top = [str(line) for line in page.get("top") or []]
    if any("No longer accepting applications" in line for line in top):
        return _finish(capture | {"acquisition_status": "expired"})
    description = _text(str(page.get("description") or ""))
    description = description.removeprefix("About the job").strip()
    description = description.removesuffix("… more").strip()
    if len(top) < 3 or len(description) < 200:
        return _finish(capture)
    company, title = _text(top[0]), _text(top[1])
    location = _text(top[2].split(" · ", 1)[0])
    fields = {"title": title, "company": company}
    if location:
        fields["location"] = location
        if location.casefold() not in description.casefold():
            description += f"\n\nJob location\n{location}"
    controls = page.get("apply") or []
    offsite = next(
        (
            control["href"]
            for control in controls
            if "company website" in control.get("label", "").casefold() and control.get("href")
        ),
        None,
    )
    if offsite:
        fields["linkedin_posting"] = "open"
        target = parse_qs(urlsplit(offsite).query).get("url", [offsite])[0]
        if target.startswith("https://"):
            fields["linkedin_apply_url"] = target
    elif any(control.get("text", "").casefold() == "easy apply" for control in controls):
        fields["linkedin_posting"] = "easy_apply"
    else:
        # Read once already; matching does not open LinkedIn again for the route.
        fields["linkedin_posting"] = "unknown"
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


def saved_posting(fields: dict | None) -> tuple[str | None, str | None]:
    """The apply route the one browser read saved, as posting_status names it."""
    fields = fields or {}
    status = fields.get("linkedin_posting")
    if status == "easy_apply":
        return "easy_apply", None
    if status == "open" and str(fields.get("linkedin_apply_url", "")).startswith("https://"):
        return "open", fields["linkedin_apply_url"]
    return None, None


def _read_in_browser(url: str) -> dict:
    from playwright.sync_api import TimeoutError, sync_playwright  # noqa: A004

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=False)
        try:
            saved = load_login_state(job_listing_links.LOGIN_ROOT)
            context = browser.new_context(**({"storage_state": saved} if saved else {}))
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            with suppress(TimeoutError):
                page.wait_for_function(
                    "() => /About the job|No longer accepting applications/"
                    ".test((document.querySelector('main') || document.body).innerText)",
                    timeout=PAGE_WAIT_MS,
                )
            return page.evaluate(_PAGE_JS)
        finally:
            browser.close()
