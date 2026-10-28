"""Capture a public job page without cookies, JavaScript, or ambient proxies."""

from __future__ import annotations

import hashlib
import http.client
import json
import queue
import re
import socket
import ssl
import threading
import time
from contextlib import suppress
from datetime import UTC, datetime
from html.parser import HTMLParser
from ipaddress import ip_address
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import uuid4

from .url_safety import is_public_host

MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 2_000_000
MAX_SECONDS = 15


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, *, timeout, context):
        super().__init__(host, port=443, timeout=timeout, context=context)
        self.address = address
        self.deadline = time.monotonic() + timeout
        self._expiry_timer = None
        self._active_socket = None

    def connect(self):
        family, kind, protocol, _, address = self.address
        sock = socket.socket(family, kind, protocol)

        def expire():
            with suppress(OSError):
                (self._active_socket or sock).shutdown(socket.SHUT_RDWR)

        # A wall-clock watchdog also bounds slow headers and slow-drip bodies.
        self._expiry_timer = threading.Timer(max(0, self.deadline - time.monotonic()), expire)
        self._expiry_timer.daemon = True
        self._expiry_timer.start()
        try:
            sock.settimeout(self.timeout)
            sock.connect(address)
            if ip_address(sock.getpeername()[0]) != ip_address(address[0]):
                raise ValueError("peer_mismatch")
            # No second DNS lookup: TLS and the Host header still use the URL hostname.
            self.sock = self._context.wrap_socket(
                sock, server_hostname=self.host, do_handshake_on_connect=False
            )
            self._active_socket = self.sock
            self.sock.settimeout(max(0.001, self.deadline - time.monotonic()))
            self.sock.do_handshake()
        except BaseException:
            sock.close()
            raise

    def finish(self):
        # HTTPConnection closes itself at headers for Connection: close. Its
        # response file still owns the socket; keep the watchdog through body IO.
        if self._expiry_timer is not None:
            self._expiry_timer.cancel()
        self.close()


def _https_get(url, *, addresses, timeout, max_bytes):
    parts = urlsplit(url)
    deadline = time.monotonic() + timeout
    connection = _PinnedHTTPS(
        parts.hostname, addresses[0], timeout=timeout, context=ssl.create_default_context()
    )
    try:
        target = urlunsplit(("", "", parts.path, parts.query, ""))
        connection.request(
            "GET",
            target,
            headers={
                "Accept": "text/html, application/ld+json, application/json, text/plain",
                "Accept-Encoding": "identity",
                "User-Agent": "TomorrowStar-JobSource/1",
                "Connection": "close",
            },
        )
        peer = connection.sock.getpeername()[0]
        sock = connection.sock
        response = connection.getresponse()
        header_pairs = response.getheaders()
        if sum(key.lower() == "location" for key, _ in header_pairs) > 1:
            raise ValueError("invalid_response")
        headers = {key.lower(): value for key, value in header_pairs}
        length = headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > max_bytes):
            raise ValueError("response_too_large")
        chunks, size = [], 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            # HTTPResponse may own a closed-connection socket after headers.
            sock.settimeout(remaining)
            chunk = response.read1(min(65536, max_bytes + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("response_too_large")
        return {
            "status": response.status,
            "headers": headers,
            "body": b"".join(chunks),
            "peer_address": peer,
        }
    finally:
        connection.finish()


def _public_address(value):
    address = ip_address(value)
    return address.is_global and not address.is_multicast


def _addresses(resolver, url, timeout):
    resolved = queue.Queue(maxsize=1)

    def resolve():
        try:
            rows = resolver(
                urlsplit(url).hostname, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )
            resolved.put((rows, None))
        except Exception as exc:
            resolved.put((None, exc))

    # getaddrinfo has no timeout API. A bounded daemon prevents a stuck resolver
    # from blocking acquisition or process shutdown; it never opens a socket.
    threading.Thread(target=resolve, daemon=True).start()
    try:
        rows, error = resolved.get(timeout=timeout)
    except queue.Empty:
        raise TimeoutError from None
    if error is not None:
        raise OSError("resolution_failed") from None
    if not rows or len(rows) > 32:
        raise ValueError("unsafe_address")
    for family, kind, protocol, _, address in rows:
        if (
            family not in {socket.AF_INET, socket.AF_INET6}
            or kind != socket.SOCK_STREAM
            or protocol != socket.IPPROTO_TCP
            or address[1] != 443
            or not _public_address(address[0])
        ):
            raise ValueError("unsafe_address")
    return rows


def _peer_matches(peer, addresses):
    return _public_address(peer) and any(
        ip_address(peer) == ip_address(row[4][0]) for row in addresses
    )


def _url(value):
    if (
        not isinstance(value, str)
        or len(value) > 8192
        or "\\" in value
        or any(ord(char) < 33 or ord(char) == 127 for char in value)
    ):
        raise ValueError("unsafe_url")
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        if (
            parts.scheme != "https"
            or parts.username is not None
            or parts.password is not None
            or parts.port not in {None, 443}
            or "%" in host
            or not is_public_host(host)
        ):
            raise ValueError("unsafe_url")
        return urlunsplit(("https", host, parts.path or "/", parts.query, ""))
    except (ValueError, UnicodeError):
        raise ValueError("unsafe_url") from None


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.scripts = []
        self.inline_scripts = []
        self.identity_urls = []
        self.identity_kinds = []
        self._script = None
        self._script_is_json_ld = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("property", "").lower() == "og:url":
            self.identity_urls.append(attrs.get("content", ""))
            self.identity_kinds.append("og")
        if tag == "link" and "canonical" in attrs.get("rel", "").lower().split():
            self.identity_urls.append(attrs.get("href", ""))
            self.identity_kinds.append("canonical")
        if tag in {"script", "style", "noscript", "svg", "iframe"}:
            self._skip += 1
            if tag == "script":
                self._script = []
                self._script_is_json_ld = attrs.get("type", "").lower() == "application/ld+json"
        elif tag in {"p", "div", "h1", "h2", "h3", "h4", "li", "br", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "iframe"}:
            self._skip = max(0, self._skip - 1)
            if tag == "script" and self._script is not None:
                target = self.scripts if self._script_is_json_ld else self.inline_scripts
                target.append("".join(self._script))
                self._script = None
        elif tag in {"p", "div", "h1", "h2", "h3", "h4", "li", "section"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
        if not self._skip:
            self.parts.append(data)

    @property
    def text(self):
        return "\n".join(
            line for part in "".join(self.parts).splitlines() if (line := " ".join(part.split()))
        )


def _linkedin_job_id(value):
    try:
        parsed = urlsplit(_url(value))
    except ValueError:
        return None
    if (
        re.fullmatch(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*linkedin\.com", parsed.hostname or ""
        )
        is None
    ):
        return None
    match = re.fullmatch(r"/jobs/view/(?:[^/]+-)?([0-9]+)/?", parsed.path)
    return match[1] if match else None


class _LinkedInDOM(HTMLParser):
    """Read only closed, uniquely identified public LinkedIn job-description scopes."""

    _VOID = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack, self.records, self.canonical, self.og_urls = [], {}, [], []

    def _emit(self, value):
        for node in self.stack:
            if node["parts"] is not None:
                node["parts"].append(value)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        classes = set((attrs.get("class") or "").split())
        if any(node["tag"] == "head" for node in self.stack):
            if tag == "link" and "canonical" in (attrs.get("rel") or "").lower().split():
                self.canonical.append(attrs.get("href"))
            if tag == "meta" and (attrs.get("property") or "").lower() == "og:url":
                self.og_urls.append(attrs.get("content"))
        if len(self.stack) >= 512:
            raise ValueError("dom_depth_limit")
        container = next(
            (node for node in reversed(self.stack) if node["kind"] == "container"), None
        )
        item = next((node for node in reversed(self.stack) if node["kind"] == "criterion"), None)
        ancestry = [node["classes"] for node in self.stack]
        kind = None
        if tag == "section" and "description" in classes:
            kind = "container"
        elif tag == "h1" and classes & {"top-card-layout__title", "topcard__title"}:
            kind = "title"
        elif tag == "a" and "topcard__org-name-link" in classes:
            kind = "company"
        elif (
            tag == "span"
            and {"topcard__flavor", "topcard__flavor--bullet"} <= classes
            and "topcard__flavor--metadata" not in classes
            and any("topcard__flavor-row" in value for value in ancestry)
        ):
            kind = "location"
        elif container is not None:
            if (
                tag == "div"
                and "show-more-less-html__markup" in classes
                and any("description__text" in value for value in ancestry)
                and any("show-more-less-html" in value for value in ancestry)
            ):
                kind = "description"
            elif tag == "ul" and "description__job-criteria-list" in classes:
                kind = "criteria"
            elif (
                tag == "li"
                and "description__job-criteria-item" in classes
                and any(node["kind"] == "criteria" for node in self.stack)
            ):
                kind = "criterion"
            elif (
                item is not None
                and tag == "h3"
                and "description__job-criteria-subheader" in classes
            ):
                kind = "criterion_label"
            elif item is not None and tag == "span" and "description__job-criteria-text" in classes:
                kind = "criterion_text"
        node = {
            "tag": tag,
            "classes": classes,
            "kind": kind,
            "container": container,
            "item": item,
            "parts": []
            if kind
            in {"title", "company", "location", "description", "criterion_label", "criterion_text"}
            else None,
            "closed": False,
            "valid": len(attrs) == len(attributes),
            "truncated": False,
        }
        if kind:
            self.records.setdefault(kind, []).append(node)
        truncated = any(
            key in attrs and str(attrs[key]).lower() not in {"false", "0", "no"}
            for key in ("data-truncated", "data-is-truncated")
        ) or bool(
            classes & {"truncated", "description--excerpt", "show-more-less-html__markup--excerpt"}
        )
        if truncated:
            node["truncated"] = True
            for ancestor in self.stack:
                if ancestor["kind"] in {"container", "description"}:
                    ancestor["truncated"] = True
        if tag not in self._VOID:
            self.stack.append(node)
        self._emit(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag in self._VOID:
            return
        index = next(
            (
                index
                for index in range(len(self.stack) - 1, -1, -1)
                if self.stack[index]["tag"] == tag
            ),
            None,
        )
        if index is None:
            for node in self.stack:
                node["valid"] = False
            return
        self._emit(f"</{tag}>")
        if index != len(self.stack) - 1:
            for node in self.stack:
                node["valid"] = False
        self.stack[index]["closed"] = True
        del self.stack[index:]

    def handle_data(self, value):
        self._emit(value)

    def handle_entityref(self, name):
        self._emit(f"&{name};")

    def handle_charref(self, name):
        self._emit(f"&#{name};")

    def _one(self, kind):
        values = self.records.get(kind, [])
        return (
            values[0]
            if len(values) == 1
            and values[0]["closed"]
            and values[0]["valid"]
            and not values[0]["truncated"]
            else None
        )

    def capture(self, final_url):
        identity = _linkedin_job_id(final_url)
        if (
            identity is None
            or len(self.canonical) != 1
            or len(self.og_urls) != 1
            or any(
                _linkedin_job_id(value) != identity for value in (*self.canonical, *self.og_urls)
            )
        ):
            return None
        nodes = {key: self._one(key) for key in ("container", "description", "title", "company")}
        if (
            any(value is None for value in nodes.values())
            or nodes["description"]["container"] is not nodes["container"]
        ):
            return None
        title, company, description = (
            _text("".join(nodes[key]["parts"])) for key in ("title", "company", "description")
        )
        if not all((title, company, description)) or re.search(
            r"(?:\.{3}|…|(?:show|read|see) more)\s*$", description, re.I
        ):
            return None
        fields = {"title": title, "company": company}
        if self.records.get("location"):
            location = self._one("location")
            if location is None:
                return None
            fields["location"] = _text("".join(location["parts"]))
            description += f"\n\nJob location\n{fields['location']}"
        if self.records.get("criteria"):
            criteria = self._one("criteria")
            if criteria is None or criteria["container"] is not nodes["container"]:
                return None
            fields["criteria"] = []
            for item in self.records.get("criterion", []):
                if (
                    not item["closed"]
                    or not item["valid"]
                    or item["container"] is not nodes["container"]
                ):
                    return None
                pair = []
                for kind in ("criterion_label", "criterion_text"):
                    values = [node for node in self.records.get(kind, []) if node["item"] is item]
                    if len(values) != 1 or not values[0]["closed"] or not values[0]["valid"]:
                        return None
                    pair.append(_text("".join(values[0]["parts"])))
                if not all(pair):
                    return None
                fields["criteria"].append({"label": pair[0], "text": pair[1]})
                description += f"\n\n{pair[0]}\n{pair[1]}"
        return {
            "body_text": description,
            "job_fields": fields,
            "source_format": "job_posting",
            "jd_completeness": "full",
            "extraction_method": "linkedin_dom",
        }


def _text(value):
    page = _Page()
    page.feed(value)
    return page.text


def _ashby_identity(value):
    try:
        parts = urlsplit(_url(value))
    except ValueError:
        return None
    if parts.hostname != "jobs.ashbyhq.com":
        return None
    match = re.fullmatch(
        r"/([A-Za-z0-9][A-Za-z0-9._-]{0,127})/"
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
        r"(?:/application)?/?",
        parts.path,
    )
    return match.groups() if match else None


def _ashby_binding(page, target):
    identity = _ashby_identity(target)
    if (
        identity is None
        or not page.identity_urls
        or len(set(page.identity_kinds)) != len(page.identity_kinds)
        or any(_ashby_identity(value) != identity for value in page.identity_urls)
    ):
        return None

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("ambiguous_ashby_data")
            value[key] = item
        return value

    values = []
    for script in page.inline_scripts:
        prefix = re.match(r"\s*window\.__appData\s*=\s*", script)
        if prefix is None:
            continue
        try:
            value, end = json.JSONDecoder(object_pairs_hook=unique_object).raw_decode(
                script[prefix.end() :]
            )
        except (ValueError, RecursionError):
            return None
        suffix = script[prefix.end() + end :]
        if not suffix.lstrip().startswith(";") or "__appData" in suffix:
            return None
        values.append(value)
    if len(values) != 1 or not isinstance(values[0], dict):
        return None
    organization, posting = values[0].get("organization"), values[0].get("posting")
    if (
        not isinstance(organization, dict)
        or not isinstance(posting, dict)
        or organization.get("hostedJobsPageSlug") != identity[0]
        or posting.get("id") != identity[1]
    ):
        return None
    return {"organization": organization, "posting": posting}


def _postings(value):
    pending = [value]
    found = []
    count = 0
    while pending:
        node = pending.pop()
        count += 1
        if count > 10000:
            raise ValueError("structured_data_limit")
        if isinstance(node, list):
            pending.extend(reversed(node))
        elif isinstance(node, dict):
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if isinstance(types, list) and any(
                value
                in {"JobPosting", "https://schema.org/JobPosting", "http://schema.org/JobPosting"}
                for value in types
                if isinstance(value, str)
            ):
                found.append(node)
            pending.extend(reversed(list(node.values())))
    return found


def _matches(posting, targets, *, ashby_binding=None):
    # Explicit job URLs take precedence over a weaker bare identifier.
    explicit = [posting.get(key) for key in ("url", "@id") if posting.get(key)]
    if explicit:
        for value in explicit:
            if not isinstance(value, str):
                return False
            matched = False
            for target in targets:
                try:
                    resolved = _url(urljoin(target, value))
                    matched |= resolved == target or (
                        _linkedin_job_id(target) is not None
                        and _linkedin_job_id(resolved) == _linkedin_job_id(target)
                    )
                except ValueError:
                    continue
            if not matched:
                return False
        return True
    values = [posting.get("identifier")]
    for value in values:
        if isinstance(value, dict):
            value = value.get("value")
        if not isinstance(value, str) or not value:
            continue
        if ashby_binding is not None:
            bound_posting = ashby_binding["posting"]
            organization = posting.get("hiringOrganization")
            if (
                value == bound_posting["id"]
                and posting.get("title") == bound_posting.get("title")
                and posting.get("description") == bound_posting.get("descriptionHtml")
                and isinstance(organization, dict)
                and organization.get("name") == ashby_binding["organization"].get("name")
            ):
                return True
        # A UUID is an opaque identifier, not a relative URL. Ashby accepts it
        # only with the independent same-page board, posting and URL binding.
        if re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value, re.I):
            continue
        for target in targets:
            try:
                if _url(urljoin(target, value)) == target:
                    return True
            except ValueError:
                continue
    return False


def _select_posting(postings, targets, *, ashby_binding=None):
    matched = [
        posting for posting in postings if _matches(posting, targets, ashby_binding=ashby_binding)
    ]
    if len(matched) == 1:
        return matched[0]
    return None


def _field_text(value):
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, list):
        return "\n".join(filter(None, (_field_text(item) for item in value)))
    if isinstance(value, dict):
        return "\n".join(
            f"{key}: {text}"
            for key, item in value.items()
            if not key.startswith("@") and (text := _field_text(item))
        )
    return "" if value is None else str(value)


def _location_text(value):
    if isinstance(value, list):
        return "; ".join(filter(None, (_location_text(item) for item in value)))
    if isinstance(value, dict):
        address = value.get("address", value)
        if isinstance(address, dict):
            return ", ".join(
                _text(item)
                for key in (
                    "streetAddress",
                    "addressLocality",
                    "addressRegion",
                    "postalCode",
                    "addressCountry",
                )
                if isinstance(item := address.get(key), str) and item.strip()
            )
        return _location_text(address)
    return _text(value) if isinstance(value, str) else ""


def _capture_page(capture, body, media_type):
    page = _Page()
    if media_type in {"application/ld+json", "application/json"}:
        page.scripts.append(body)
    else:
        page.feed(body)
    capture.update(body_text=page.text, acquisition_status="available")
    text = page.text.casefold()
    if any(
        phrase in text
        for phrase in (
            "sign in to view this job",
            "log in to view this job",
            "login required",
            "verify you are human",
            "captcha challenge",
            "unusual traffic",
            "enable javascript and cookies to continue",
        )
    ):
        capture["acquisition_status"] = "login_required"
        return
    if any(
        phrase in text
        for phrase in (
            "this job is no longer available",
            "this job has expired",
            "this position has been filled",
            "this job is closed",
        )
    ):
        capture["acquisition_status"] = "expired"
        return
    postings = []
    for script in page.scripts:
        try:
            postings.extend(_postings(json.loads(script)))
        except (ValueError, RecursionError):
            continue
    ashby_binding = (
        _ashby_binding(page, capture["final_url"])
        if _ashby_identity(capture["url"]) == _ashby_identity(capture["final_url"])
        else None
    )
    posting = _select_posting(postings, {capture["final_url"]}, ashby_binding=ashby_binding)
    if posting is None:
        if not page.scripts and _linkedin_job_id(capture["final_url"]):
            dom = _LinkedInDOM()
            dom.feed(body)
            result = dom.capture(capture["final_url"])
            if result:
                capture.update(result)
        return
    title = posting.get("title")
    organization = posting.get("hiringOrganization")
    company = organization.get("name") if isinstance(organization, dict) else None
    description = posting.get("description")
    if not all(isinstance(value, str) and value.strip() for value in (title, company, description)):
        return
    description = _text(description)
    title, company = _text(title), _text(company)
    if not all((description, title, company)) or re.search(
        r"(?:\.{3}|…|(?:show|read|see) more)\s*$", description, re.I
    ):
        return
    expiry = posting.get("validThrough")
    if isinstance(expiry, str):
        try:
            valid_through = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if valid_through.tzinfo is None:
                valid_through = valid_through.replace(tzinfo=UTC)
            if valid_through < datetime.now(UTC):
                capture.update(body_text=description, acquisition_status="expired")
                return
        except ValueError:
            pass
    fields = {"title": title, "company": company}
    location = _location_text(posting.get("jobLocation"))
    if ashby_binding is not None and _matches(posting, set(), ashby_binding=ashby_binding):
        bound_location = ashby_binding["posting"].get("locationName")
        if isinstance(bound_location, str) and bound_location.strip():
            location = _text(bound_location)
            if location and location.casefold() not in description.casefold():
                description += f"\n\nJob location\n{location}"
    if location:
        fields["location"] = location
    for key, label in (
        ("qualifications", "Qualifications"),
        ("responsibilities", "Responsibilities"),
        ("skills", "Skills"),
        ("educationRequirements", "Education requirements"),
        ("experienceRequirements", "Experience requirements"),
        ("eligibilityToWorkRequirement", "Eligibility to work"),
        ("employmentType", "Employment type"),
        ("jobLocation", "Job location"),
        ("jobLocationType", "Job location type"),
        ("applicantLocationRequirements", "Applicant location requirements"),
        ("workHours", "Work hours"),
        ("baseSalary", "Base salary"),
        ("datePosted", "Date posted"),
        ("validThrough", "Valid through"),
    ):
        if key in posting:
            fields[key] = posting[key]
            text = _field_text(posting[key])
            if text and text.casefold() not in description.casefold():
                description += f"\n\n{label}\n{text}"
    capture.update(
        body_text=description,
        jd_completeness="full",
        source_format="job_posting",
        job_fields=fields,
    )


def _finish(capture):
    capture["captured_at"] = datetime.now(UTC).isoformat()
    capture["revision"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in capture.items() if key != "capture_id"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return capture


def fetch_job_source(url, *, resolver=socket.getaddrinfo, transport=None):
    """Return an acquisition receipt; routine page failures do not raise."""
    capture = {
        "capture_id": uuid4().hex,
        "url": url,
        "final_url": url,
        "body_text": "",
        "acquisition_status": "unavailable",
        "jd_completeness": "unknown",
        "source_format": "page",
        "redirects": [],
        "job_fields": {},
    }
    try:
        url = _url(url)
    except ValueError:
        capture["error_code"] = "unsafe_url"
        return _finish(capture)
    capture["final_url"] = url
    transport = _https_get if transport is None else transport
    try:
        deadline = time.monotonic() + MAX_SECONDS
        visited = set()
        for hop in range(MAX_REDIRECTS + 1):
            url = _url(url)
            capture["final_url"] = url
            if url in visited:
                raise ValueError("redirect_loop")
            visited.add(url)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            addresses = _addresses(resolver, url, remaining)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            result = transport(
                url, addresses=addresses, timeout=remaining, max_bytes=MAX_RESPONSE_BYTES
            )
            if not _peer_matches(result.get("peer_address", ""), addresses):
                raise ValueError("peer_mismatch")
            headers = {key.lower(): value for key, value in result["headers"].items()}
            if not isinstance(result["body"], bytes):
                raise ValueError("invalid_response")
            length = headers.get("content-length")
            if len(result["body"]) > MAX_RESPONSE_BYTES or (
                length is not None and (not length.isdigit() or int(length) > MAX_RESPONSE_BYTES)
            ):
                raise ValueError("response_too_large")
            if length is not None and len(result["body"]) != int(length):
                raise ValueError("incomplete_response")
            if headers.get("content-encoding", "identity").casefold() != "identity":
                raise ValueError("unsupported_encoding")
            if result["status"] not in {301, 302, 303, 307, 308}:
                break
            if hop == MAX_REDIRECTS:
                raise ValueError("redirect_limit")
            target = _url(urljoin(url, headers.get("location", "")))
            capture["redirects"].append(
                {"url": url, "status": result["status"], "location": target}
            )
            url = target
        capture["final_url"] = url
    except (ValueError, OSError, http.client.HTTPException) as exc:
        capture["error_code"] = (
            "timeout"
            if isinstance(exc, TimeoutError)
            else (
                str(exc)
                if str(exc)
                in {
                    "unsafe_url",
                    "unsafe_address",
                    "peer_mismatch",
                    "redirect_loop",
                    "redirect_limit",
                    "invalid_response",
                    "response_too_large",
                    "unsupported_encoding",
                    "incomplete_response",
                }
                else "network_error"
            )
        )
        return _finish(capture)
    status = result["status"]
    capture["http_status"] = status
    capture["content_sha256"] = hashlib.sha256(result["body"]).hexdigest()
    if status in {401, 403}:
        capture["acquisition_status"] = "login_required"
    elif status in {404, 410}:
        capture["acquisition_status"] = "expired"
    elif status != 200:
        capture["error_code"] = "http_error"
    else:
        media_type = headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        if media_type not in {
            "text/html",
            "application/xhtml+xml",
            "text/plain",
            "application/ld+json",
            "application/json",
        }:
            capture["error_code"] = "unsupported_content_type"
        else:
            match = re.search(
                r"charset\s*=\s*[\"']?([^\s;\"']+)", headers.get("content-type", ""), re.I
            )
            charset = match.group(1) if match else "utf-8"
            try:
                body = result["body"].decode(charset, errors="replace")
            except LookupError:
                body = result["body"].decode("utf-8", errors="replace")
            try:
                _capture_page(capture, body, media_type)
            except (ValueError, RecursionError):
                capture.update(
                    body_text="",
                    acquisition_status="unavailable",
                    jd_completeness="unknown",
                    job_fields={},
                    error_code="invalid_structured_data",
                )
    return _finish(capture)
