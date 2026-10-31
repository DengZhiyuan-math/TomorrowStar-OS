"""Let the user sign in to a job board for the App's browser (decided 2026-10-31).

A visible system Chrome opens the site's sign-in page with no job bound to it and
no request blocking. Its logins are saved where the worker loads them, so later
job pages open signed in. The user's own Chrome is never read.
"""

from __future__ import annotations

import threading
from pathlib import Path

from .career_portal_data import PortalDataError
from .cua_driver import load_login_state, save_login_state

SIGN_IN_PAGES = {"linkedin": "https://www.linkedin.com/login"}
_open: set[str] = set()
_lock = threading.Lock()


def open_sign_in(worker_root: Path, site: str) -> dict:
    """Open one sign-in window per site; it saves logins until the user closes it."""
    url = SIGN_IN_PAGES.get(site)
    if url is None:
        raise PortalDataError("sign_in_site_unknown", "暂不支持这个网站的登录。", 400)
    with _lock:
        if site in _open:
            return {"status": "open", "site": site}
        _open.add(site)
    threading.Thread(target=_run, args=(Path(worker_root), site, url), daemon=True).start()
    return {"status": "opened", "site": site}


def _run(root: Path, site: str, url: str) -> None:
    from playwright.sync_api import Error, sync_playwright

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=False)
            try:
                saved = load_login_state(root)
                context = browser.new_context(**({"storage_state": saved} if saved else {}))
                page = context.new_page()
                page.goto(url)
                while not page.is_closed() and browser.is_connected():
                    save_login_state(root, context)
                    page.wait_for_timeout(2000)
                save_login_state(root, context)
            finally:
                browser.close()
    except (Error, OSError, ValueError):
        # Logins saved before the window closed remain; nothing else is changed.
        pass
    finally:
        with _lock:
            _open.discard(site)
