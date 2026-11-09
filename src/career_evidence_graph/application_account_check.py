"""Whether a job's application needs an account, judged while the match runs.

The user's decision (2026-11-09): an application behind a sign-in or account creation
leaves the automatic path and needs the user's own time, so a job that needs an account
and does not match well is not worth materials. The check runs beside the analysis, in a
headless browser with no cookies: it opens the job page and follows its Apply link or
button, never fills or sends anything. Known application systems are decided by their
address; page rules decide most others; only an unclear page goes to a model with a
screenshot. A fill that meets a sign-in teaches the site (``learn_host``).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from ._vendor import job_apply_store as helper

DIRECT, ACCOUNT, UNCLEAR = "direct", "account", "unclear"

# Application systems that open a form without an account.
NO_ACCOUNT_HOSTS = (
    "ashbyhq.com",
    "greenhouse.io",
    "lever.co",
    "personio.com",
    "personio.de",
    "workable.com",
    "smartrecruiters.com",
    "recruitee.com",
    "teamtailor.com",
    "join.com",
)
# Application systems that ask for an account before the form.
ACCOUNT_HOSTS = (
    "myworkdayjobs.com",
    "myworkdaysite.com",
    "successfactors.com",
    "successfactors.eu",
    "jobs.sap.com",
    "taleo.net",
    "icims.com",
    "avature.net",
    "oraclecloud.com",
)
LOGIN_HOSTS = (
    "login.microsoftonline.com",
    "accounts.google.com",
    "auth0.com",
    "okta.com",
    "idmsa.apple.com",
)
# A sign-in address, wherever the job page or Apply led (2026-11-09: Apple's job link).
_SIGN_IN_PATH = re.compile(r"/(sign-?in|log-?in|sso|idmswebauth)\b", re.I)
_ACCOUNT_TEXT = re.compile(
    r"\b(sign in|log ?in|create (an |your )?account|register|forgot (your )?password|"
    r"anmelden|registrieren|konto erstellen|passwort vergessen|se connecter|"
    r"créer un compte)\b",
    re.I,
)
_FORM_TEXT = re.compile(
    r"\b(first name|last name|e-?mail|resume|cv|vorname|nachname|lebenslauf|prénom)\b", re.I
)


def _host(url):
    return (urlsplit(str(url or "")).hostname or "").lower()


def _matches(host, suffixes):
    return any(host == suffix or host.endswith("." + suffix) for suffix in suffixes)


def classify_url(url, learned=()):
    """'direct' or 'account' from the address alone, else None."""
    host = _host(url)
    if not host:
        return None
    if _matches(host, NO_ACCOUNT_HOSTS):
        return DIRECT
    if _matches(host, ACCOUNT_HOSTS) or _matches(host, LOGIN_HOSTS) or host in learned:
        return ACCOUNT
    return None


def page_rules(observation):
    """Decide from an observed application page, or None when it is unclear.

    Page text counts only once Apply was reached: a job posting's own menu often has a
    "Login" link (2026-11-09: Hitachi Energy, LGT).
    """
    decided = classify_url(observation.get("apply_url")) or classify_url(observation.get("url"))
    if decided is not None:
        return decided
    if _SIGN_IN_PATH.search(urlsplit(str(observation.get("url") or "")).path):
        return ACCOUNT
    if not observation.get("applied"):
        return None
    if observation.get("password_field"):
        return ACCOUNT
    text = str(observation.get("text") or "")
    account, form = bool(_ACCOUNT_TEXT.search(text)), len(_FORM_TEXT.findall(text)) >= 2
    if form and not account:
        return DIRECT
    if account and not form:
        return ACCOUNT
    return None


_APPLY_START = re.compile(r"^\s*(apply|jetzt bewerben|bewerben|postuler|candidater)\b", re.I)
_NOT_APPLY = re.compile(r"employee|mitarbeit|intern(al)? candidate|job alert", re.I)
_REJECT_COOKIES = re.compile(
    r"^\s*(reject all|reject|decline( all)?|only necessary|necessary only|alle ablehnen|"
    r"ablehnen|nur notwendige|tout refuser|refuser)\s*$",
    re.I,
)


def browse(url, directory):
    """Open the job page headless, follow Apply once, and record what the page shows.

    A cookie banner is refused first (the most private choice). An Apply link's address
    is followed directly; an Apply button is clicked. Nothing is filled or sent.
    """
    from playwright.sync_api import Error, sync_playwright

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_context().new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(2_000)
            try:
                reject = page.get_by_role("button", name=_REJECT_COOKIES).first
                if reject.count() and reject.is_visible():
                    reject.click(timeout=3_000)
                    page.wait_for_timeout(500)
            except Error:
                pass
            apply_url, applied = None, False
            for element in page.locator("a, button, [role=button]").all()[:400]:
                try:
                    label = (element.inner_text(timeout=500) or "").strip()
                    if not _APPLY_START.search(label) or _NOT_APPLY.search(label):
                        continue
                    href = element.get_attribute("href") or ""
                    if href.startswith("http"):
                        apply_url = href
                        page.goto(href, wait_until="domcontentloaded", timeout=30_000)
                    else:
                        element.click(timeout=5_000)
                        page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    page.wait_for_timeout(2_000)
                    applied = True
                    break
                except Error:
                    continue
            # A new tab opened by Apply is the application page.
            page = page.context.pages[-1]
            screenshot = directory / "application.png"
            page.screenshot(path=str(screenshot))
            return {
                "url": page.url,
                "apply_url": apply_url,
                "applied": applied,
                "password_field": page.locator("input[type=password]").count() > 0,
                "text": page.inner_text("body", timeout=5_000)[:6000],
                "screenshot": str(screenshot),
            }
        finally:
            browser.close()


JUDGE_PROMPT = """The attached screenshot shows a job application page reached by opening
the job posting and pressing its Apply button once. Answer whether the applicant must sign
in or create an account before they can fill in the application form. Answer "account" for
a sign-in or registration wall, "direct" when the application form itself is open, and
"unclear" otherwise. Return only the schema object.
"""


def judge(observation, directory, *, runner=None):
    """Ask a small model about one screenshot; any failure is unclear."""
    from .codex_cli import CodexCLIError, run_codex_exec
    from .validation.models import CodexCLIConfig

    directory = Path(directory)
    schema = directory / "judge-schema.json"
    helper.atomic_write_json(
        schema,
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["status"],
            "properties": {"status": {"type": "string", "enum": [DIRECT, ACCOUNT, UNCLEAR]}},
        },
    )
    image = observation["screenshot"]

    def transport(argv, **kwargs):
        return (runner or subprocess.run)([*argv[:2], "--image", image, *argv[2:]], **kwargs)

    try:
        result = run_codex_exec(
            CodexCLIConfig(
                schema_version="codex-cli-config/v1",
                workspace=directory,
                output_schema=schema,
                drift_limitation_reason="Unpinned alias; one screenshot judgement retained.",
            ),
            JUDGE_PROMPT,
            runner=transport,
            timeout_seconds=90,
            allow_non_repository=True,
        )
    except (CodexCLIError, OSError, ValueError):
        return UNCLEAR
    status = (result.structured_result or {}).get("status")
    return status if status in {DIRECT, ACCOUNT, UNCLEAR} else UNCLEAR


def check_account(url, directory, *, learned=(), browser=browse, model=judge):
    """'direct', 'account' or 'unclear' for one job, with what decided it."""
    decided = classify_url(url, learned)
    if decided is not None:
        return {"status": decided, "by": "address", "url": url}
    try:
        observation = browser(url, directory)
    except Exception as error:  # A blocked or slow page leaves the fill to find out.
        return {"status": UNCLEAR, "by": "browser_failed", "error": type(error).__name__}
    decided = page_rules(observation)
    if decided is not None:
        return {"status": decided, "by": "page", "url": observation.get("url")}
    if not observation.get("applied"):
        return {"status": UNCLEAR, "by": "no_apply_found", "url": observation.get("url")}
    return {
        "status": model(observation, directory),
        "by": "screenshot",
        "url": observation.get("url"),
    }


def learned_hosts(path):
    try:
        return set(json.loads(Path(path).read_text(encoding="utf-8")).get("hosts", []))
    except (OSError, ValueError, AttributeError):
        return set()


def learn_host(path, url):
    """Remember a site whose application asked for an account during a fill."""
    host = _host(url)
    if not host or _matches(host, NO_ACCOUNT_HOSTS):
        return
    hosts = learned_hosts(path) | {host}
    helper.atomic_write_json(Path(path), {"hosts": sorted(hosts)})
