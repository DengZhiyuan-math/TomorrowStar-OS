"""Resolve a LinkedIn job to the employer's own application page (decided 2026-10-31).

With the login saved through 登录领英, LinkedIn's job page names the job's
offsite apply URL. One read per recommended job; nothing is clicked or sent.
Easy Apply jobs, pages without that field and missing logins keep LinkedIn.
"""

from __future__ import annotations

import json
import re
import socket
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from .application_automation import recommendation_key
from .application_job_source import fetch_job_source
from .cua_driver import load_login_state

LOGIN_ROOT: Path | None = None
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"
)


def configure(worker_root: Path | None) -> None:
    global LOGIN_ROOT
    LOGIN_ROOT = None if worker_root is None else Path(worker_root)


def _linkedin(host: str) -> bool:
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def linkedin_posting(page: str, job_id: str) -> tuple[str | None, str | None]:
    """('open', employer URL), ('easy_apply', None), ('closed', None) or (None, None).

    A closed posting has no apply entry for its job and says so on the page.
    """
    text = page.replace('\\"', '"')
    for match in re.finditer(rf'"jobId":"{re.escape(job_id)}"([^{{}}]{{0,2000}})', text):
        fields = match.group(1)
        if '"isOnsiteApply":true' in fields:
            return "easy_apply", None
        found = re.search(r'"offsiteApplyUrl":"(https://(?:[^"\\]|\\.)+)"', fields)
        if found:
            return "open", json.loads(f'"{found.group(1)}"')
    if "No longer accepting applications" in text:
        return "closed", None
    return None, None


def offsite_apply_url(page: str, job_id: str) -> str | None:
    """The offsite apply URL LinkedIn names for this job ID, or None (Easy Apply)."""
    return linkedin_posting(page, job_id)[1]


def posting_status(url: str, *, read=None) -> tuple[str | None, str | None]:
    """Read a LinkedIn job once with the saved login; (None, None) when it cannot."""
    key = recommendation_key(url)
    if not key or key[0] != "linkedin" or LOGIN_ROOT is None:
        return None, None
    saved = load_login_state(LOGIN_ROOT) or {"cookies": []}
    cookies = {
        cookie["name"]: cookie["value"]
        for cookie in saved["cookies"]
        if _linkedin(str(cookie.get("domain", "")).lstrip("."))
    }
    if "li_at" not in cookies:
        return None, None
    try:
        page = (read or _read)(f"https://www.linkedin.com/jobs/view/{key[1]}/", cookies)
    except (OSError, ValueError):
        return None, None
    return linkedin_posting(page, key[1])


def resolve_apply_url(url: str, *, read=None, fetch=fetch_job_source) -> str | None:
    """Return the employer page's final URL for a LinkedIn job, or None to keep LinkedIn."""
    status, target = posting_status(url, read=read)
    return employer_url(target, fetch=fetch) if status == "open" else None


def employer_url(target: str, *, fetch=fetch_job_source, read_page=None) -> str | None:
    """Follow LinkedIn's offsite URL to the employer's final page."""
    try:
        capture = fetch(target)
    except (OSError, ValueError):
        return None
    if capture.get("error_code") == "unsafe_url":
        return None
    # A site that refuses a direct read still opens in the worker's browser.
    final = target if capture.get("error_code") else capture.get("final_url") or target
    if _linkedin(urlsplit(final).hostname or ""):
        return None
    # LinkedIn's links to Phenom career sites carry utm_medium=phenom-feeds.
    if "phenom" not in urlsplit(target).query.casefold():
        return final
    return external_apply_url(final, read=read_page) or final


def external_apply_url(url: str, *, read=None) -> str | None:
    """The other site a Phenom job page names for applying, or None (2026-11-05).

    BCG Platinion's Phenom page renders no Apply button; its data names Avature.
    Opening that page directly keeps the native takeover on one site: the driver
    refused a handoff after the open page itself had moved to another site.
    """
    try:
        page = (read or _read_page)(url)
    except (OSError, ValueError):
        return None
    if "phApp.ddo" not in page or '"isExternalApply":true' not in page:
        return None
    found = re.search(r'"applyUrl":"(https://(?:[^"\\]|\\.)+)"', page)
    if not found:
        return None
    target = json.loads(f'"{found.group(1)}"')
    host = urlsplit(target).hostname or ""
    return target if host and host != urlsplit(url).hostname else None


def _read_page(url: str) -> str:
    from .application_job_source import MAX_RESPONSE_BYTES, _addresses, _https_get, _url

    url = _url(url)
    result = _https_get(
        url,
        addresses=_addresses(socket.getaddrinfo, url, 20),
        timeout=20,
        max_bytes=MAX_RESPONSE_BYTES,
    )
    if result["status"] != 200:
        raise ValueError("page_unavailable")
    return result["body"].decode("utf-8", "replace")


def _read(url: str, cookies: dict) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Cookie": "; ".join(f"{name}={value}" for name, value in cookies.items()),
            "User-Agent": _USER_AGENT,
            "Accept-Language": "en",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if _linkedin(urlsplit(response.geturl()).hostname or "") is False:
            raise ValueError("left_linkedin")
        return response.read(5_000_000).decode("utf-8", "replace")
