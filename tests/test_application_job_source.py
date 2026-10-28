"""Public job-page acquisition uses synthetic DNS and HTTP responses only."""

import io
import json
import socket
import threading
import time

import pytest

from career_evidence_graph.application_job_source import fetch_job_source


def public_resolver(host, port, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", port))]


def response(body, *, status=200, headers=None):
    return {
        "status": status,
        "headers": {"content-type": "text/html; charset=utf-8", **(headers or {})},
        "body": body.encode() if isinstance(body, str) else body,
        "peer_address": "8.8.8.8",
    }


def posting(**changes):
    return {
        "@type": "JobPosting",
        "url": "https://jobs.example.com/role",
        "title": "Systems Engineer",
        "hiringOrganization": {"@type": "Organization", "name": "Example Labs"},
        "description": (
            "<h2>Responsibilities</h2><p>Build Python services.</p>"
            "<h2>Requirements</h2><p>Use Linux.</p>"
        ),
        **changes,
    }


def html_job(value):
    return '<html><script type="application/ld+json">' + json.dumps(value) + "</script></html>"


def test_ashby_application_page_accepts_its_bound_uuid_json_ld_without_a_second_request():
    identity = "11111111-2222-4333-8444-555555555555"
    url = f"https://jobs.ashbyhq.com/example-labs/{identity}"
    job = posting(url=None, identifier={"value": identity})
    bootstrap = {
        "organization": {"hostedJobsPageSlug": "example-labs", "name": "Example Labs"},
        "posting": {
            "id": identity,
            "title": "Systems Engineer",
            "descriptionHtml": job["description"],
            "locationName": "Zurich",
        },
    }
    body = (
        f'<meta property="og:url" content="{url}">'
        + html_job(job)
        + "<script>window.__appData = "
        + json.dumps(bootstrap)
        + "; throw Error('must not run');</script>"
    )
    calls = []

    def transport(target, **options):
        calls.append(target)
        return response(body)

    capture = fetch_job_source(url + "/application", resolver=public_resolver, transport=transport)
    assert capture["jd_completeness"] == "full"
    assert capture["job_fields"]["company"] == "Example Labs"
    assert capture["job_fields"]["title"] == "Systems Engineer"
    assert capture["job_fields"]["location"] == "Zurich"
    assert "Build Python services." in capture["body_text"]
    assert calls == [url + "/application"]


@pytest.mark.parametrize(
    "conflict",
    [
        "other-board",
        "other-id",
        "other-organization",
        "other-title",
        "other-description",
        "other-og-board",
        "other-og-id",
        "conflicting-canonical",
        "duplicate-og",
        "duplicate-canonical",
        "missing-og",
        "missing-bootstrap",
        "invalid-bootstrap",
        "duplicate-bootstrap",
        "duplicate-json-key",
        "bootstrap-overwrite",
        "duplicate-posting",
        "explicit-other-job",
        "mixed-explicit-and-bare",
        "generic-host",
        "redirect-other-board",
    ],
)
def test_ashby_bare_uuid_requires_one_unambiguous_same_board_posting(conflict):
    identity = "11111111-2222-4333-8444-555555555555"
    target = f"https://jobs.ashbyhq.com/example-labs/{identity}"
    metadata = f'<meta property="og:url" content="{target}">'
    job = posting(url=None, identifier={"value": identity})
    bootstrap = {
        "organization": {"hostedJobsPageSlug": "example-labs", "name": "Example Labs"},
        "posting": {
            "id": identity,
            "title": "Systems Engineer",
            "descriptionHtml": job["description"],
        },
    }
    if conflict == "other-board":
        bootstrap["organization"]["hostedJobsPageSlug"] = "another-board"
    elif conflict == "other-id":
        bootstrap["posting"]["id"] = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    elif conflict == "other-organization":
        bootstrap["organization"]["name"] = "Other Company"
    elif conflict == "other-title":
        bootstrap["posting"]["title"] = "Other Role"
    elif conflict == "other-description":
        bootstrap["posting"]["descriptionHtml"] = "Other duties."
    elif conflict == "other-og-board":
        metadata = metadata.replace("example-labs", "another-board")
    elif conflict == "other-og-id":
        metadata = metadata.replace(identity, "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
    elif conflict == "conflicting-canonical":
        metadata += f'<link rel="canonical" href="{target.replace("example-labs", "other")}">'
    elif conflict == "duplicate-og":
        metadata += metadata
    elif conflict == "duplicate-canonical":
        metadata += 2 * f'<link rel="canonical" href="{target}">'
    elif conflict == "missing-og":
        metadata = ""
    elif conflict == "explicit-other-job":
        job["url"] = target.replace("example-labs", "other")
    elif conflict == "generic-host":
        target = target.replace("jobs.ashbyhq.com", "jobs.example.com")
    document = job
    if conflict == "duplicate-posting":
        document = [job, job]
    elif conflict == "mixed-explicit-and-bare":
        document = [job, posting(url=target)]
    script = "<script>window.__appData = " + json.dumps(bootstrap) + ";</script>"
    if conflict == "missing-bootstrap":
        script = ""
    elif conflict == "invalid-bootstrap":
        script = "<script>window.__appData = {broken};</script>"
    elif conflict == "duplicate-bootstrap":
        script += script
    elif conflict == "duplicate-json-key":
        script = script.replace('"id":', '"id": "conflicting-id", "id":')
    elif conflict == "bootstrap-overwrite":
        script = script.replace(";</script>", "; window.__appData = {};</script>")
    body = metadata + html_job(document) + script

    def transport(url, **options):
        if conflict == "redirect-other-board" and "original-board" in url:
            return response("", status=302, headers={"location": target})
        return response(body)

    original = (
        target.replace("example-labs", "original-board")
        if conflict == "redirect-other-board"
        else target
    )
    capture = fetch_job_source(original, resolver=public_resolver, transport=transport)
    assert capture["jd_completeness"] == "unknown"
    assert capture["job_fields"] == {}


def test_unidentified_single_posting_cannot_claim_to_be_the_requested_job():
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(html_job(posting(url=None))),
    )
    assert capture["jd_completeness"] == "unknown"
    assert capture["job_fields"] == {}


@pytest.mark.parametrize("url", ["https://jobs.example.com/role", "http://unsafe.example.com/role"])
def test_every_source_receipt_records_its_acquisition_time(url):
    from datetime import UTC, datetime

    before = datetime.now(UTC)
    capture = fetch_job_source(
        url,
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(html_job(posting())),
    )
    captured_at = datetime.fromisoformat(capture["captured_at"])
    assert captured_at.tzinfo is not None
    assert before <= captured_at <= datetime.now(UTC)


def test_matching_linkedin_job_id_accepts_provider_canonical_url_variants():
    capture = fetch_job_source(
        "https://www.linkedin.com/jobs/view/12345",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(
            html_job(
                posting(
                    url="https://ch.linkedin.com/jobs/view/systems-engineer-at-example-labs-12345",
                )
            )
        ),
    )
    assert capture["jd_completeness"] == "full"
    assert capture["job_fields"]["company"] == "Example Labs"


@pytest.mark.parametrize(
    "description", ["Build services…", "Use Python...", "Work with us. Read more"]
)
def test_explicitly_truncated_structured_description_cannot_claim_full_jd(description):
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(html_job(posting(description=description))),
    )
    assert capture["jd_completeness"] == "unknown"
    assert capture["job_fields"] == {}


def test_public_job_posting_retains_full_plain_description_and_identity():
    calls = []

    def transport(url, **options):
        calls.append((url, options))
        return response(html_job(posting(url=url)))

    capture = fetch_job_source(
        "https://jobs.example.com/engineer", resolver=public_resolver, transport=transport
    )
    assert capture["acquisition_status"] == "available"
    assert capture["jd_completeness"] == "full"
    assert capture["source_format"] == "job_posting"
    assert (
        capture["body_text"] == "Responsibilities\nBuild Python services.\nRequirements\nUse Linux."
    )
    assert capture["job_fields"]["title"] == "Systems Engineer"
    assert capture["job_fields"]["company"] == "Example Labs"
    assert capture["url"] == capture["final_url"] == "https://jobs.example.com/engineer"
    assert len(capture["capture_id"]) >= 16
    assert len(capture["revision"]) == 64
    assert calls[0][1]["addresses"][0][4] == ("8.8.8.8", 443)


@pytest.mark.parametrize(
    "url",
    [
        "http://jobs.example.com/role",
        "https://user:password@jobs.example.com/role",
        "https://jobs.example.com:8443/role",
        "https://localhost/role",
        "https://127.0.0.1/role",
        "https://2130706433/role",
        "https://jobs.example.com\\@localhost/role",
        "https://jobs.example.com/role\nInjected: header",
        "https://jobs.example.com%2flocalhost/role",
    ],
)
def test_unsafe_urls_are_rejected_before_dns_or_http(url):
    def forbidden(*args, **kwargs):
        pytest.fail("Unsafe input must not reach DNS or HTTP")

    capture = fetch_job_source(url, resolver=forbidden, transport=forbidden)
    assert capture["acquisition_status"] == "unavailable"
    assert capture["jd_completeness"] == "unknown"
    assert capture["error_code"] == "unsafe_url"


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.4", "169.254.169.254", "::1", "224.0.0.1"]
)
def test_every_dns_answer_must_be_public_even_when_the_first_is_public(address):
    def resolver(host, port, **kwargs):
        return public_resolver(host, port) + [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (address, port),
            )
        ]

    def forbidden(*args, **kwargs):
        pytest.fail("Mixed or private DNS answers must not reach HTTP")

    capture = fetch_job_source(
        "https://jobs.example.com/role", resolver=resolver, transport=forbidden
    )
    assert capture["error_code"] == "unsafe_address"
    assert capture["body_text"] == ""


def test_redirect_target_is_validated_and_resolved_before_each_request():
    calls = []

    def resolver(host, port, **kwargs):
        calls.append(("dns", host))
        return public_resolver(host, port)

    def transport(url, **kwargs):
        calls.append(("http", url))
        return response("", status=302, headers={"location": "https://127.0.0.1/admin"})

    capture = fetch_job_source(
        "https://jobs.example.com/role", resolver=resolver, transport=transport
    )
    assert capture["error_code"] == "unsafe_url"
    assert calls == [("dns", "jobs.example.com"), ("http", "https://jobs.example.com/role")]


def test_transport_peer_must_match_a_verified_dns_address():
    def transport(url, **kwargs):
        return {**response(html_job(posting())), "peer_address": "127.0.0.1"}

    capture = fetch_job_source(
        "https://jobs.example.com/role", resolver=public_resolver, transport=transport
    )
    assert capture["error_code"] == "peer_mismatch"
    assert capture["body_text"] == ""


def test_default_https_transport_pins_dns_result_and_retains_original_tls_name(monkeypatch):
    body = html_job(posting()).encode()
    calls = []

    class Connection:
        def settimeout(self, timeout):
            assert 0 < timeout <= 15

        def connect(self, address):
            calls.append(("connect", address))

        def getpeername(self):
            return ("8.8.8.8", 443)

        def sendall(self, value):
            calls.append(("request", value))

        def makefile(self, mode):
            return io.BytesIO(
                (
                    "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n"
                ).encode()
                + body
            )

        def close(self):
            pass

        def do_handshake(self):
            calls.append(("handshake", True))

    class Context:
        def wrap_socket(self, sock, *, server_hostname, do_handshake_on_connect):
            assert do_handshake_on_connect is False
            calls.append(("tls", server_hostname))
            return sock

    def resolver(host, port, **kwargs):
        calls.append(("dns", host))
        assert sum(kind == "dns" for kind, _ in calls) == 1
        return public_resolver(host, port)

    monkeypatch.setattr("ssl.create_default_context", lambda: Context())
    monkeypatch.setattr("socket.socket", lambda *args: Connection())
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    capture = fetch_job_source("https://jobs.example.com/role", resolver=resolver)
    assert capture["jd_completeness"] == "full"
    assert ("connect", ("8.8.8.8", 443)) in calls
    assert ("tls", "jobs.example.com") in calls
    request = next(value for kind, value in calls if kind == "request")
    assert request.startswith(b"GET /role HTTP/1.1\r\n")
    assert b"Host: jobs.example.com\r\n" in request
    assert b"Cookie:" not in request and b"Authorization:" not in request


@pytest.mark.parametrize(
    "document",
    [
        [posting()],
        {"@context": "https://schema.org", "@graph": [{"@type": "WebSite"}, posting()]},
        {"mainEntity": posting(**{"@type": ["Thing", "JobPosting"]})},
    ],
)
def test_job_posting_can_be_nested_in_json_ld_lists_or_graph(document):
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(html_job(document)),
    )
    assert capture["jd_completeness"] == "full"
    assert "Build Python services." in capture["body_text"]


def test_multiple_postings_require_a_unique_identity_match_to_the_target_url():
    document = {
        "@graph": [
            posting(url="https://jobs.example.com/another", title="Other Role"),
            posting(url="https://jobs.example.com/role", title="Target Role"),
        ]
    }
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(html_job(document)),
    )
    assert capture["jd_completeness"] == "full"
    assert capture["job_fields"]["title"] == "Target Role"


def test_matching_bare_identifier_cannot_override_a_conflicting_explicit_job_url():
    document = posting(
        url="https://jobs.example.com/jobs/other",
        title="Other explicit job",
        identifier={"@type": "PropertyValue", "value": "role-123"},
    )
    capture = fetch_job_source(
        "https://jobs.example.com/jobs/role-123",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(html_job(document)),
    )
    assert capture["jd_completeness"] == "unknown"
    assert capture["job_fields"] == {}


def test_redirected_page_cannot_publish_the_previous_job_as_the_final_job():
    original = "https://jobs.example.com/jobs/old"
    final = "https://jobs.example.com/jobs/new"

    def transport(url, **kwargs):
        if url == original:
            return response("", status=302, headers={"location": final})
        return response(html_job(posting(url=original, title="Old posting")))

    capture = fetch_job_source(original, resolver=public_resolver, transport=transport)
    assert capture["final_url"] == final
    assert capture["jd_completeness"] == "unknown"


@pytest.mark.parametrize(
    "document",
    [
        [posting(title="One"), posting(title="Two")],
        [
            posting(url="https://jobs.example.com/role", title="One"),
            posting(url="https://jobs.example.com/role", title="Two"),
        ],
        posting(title=""),
        posting(hiringOrganization={}),
        posting(description="<script>writeFakeJD()</script>"),
    ],
)
def test_ambiguous_or_incomplete_postings_do_not_claim_full_jd(document):
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(html_job(document)),
    )
    assert capture["jd_completeness"] == "unknown"
    assert capture["job_fields"] == {}


def test_page_fallback_retains_visible_text_without_executing_or_retaining_scripts():
    body = (
        "<h1>Systems Engineer</h1><p>Apply at Example Labs.</p>"
        '<script>throw Error("execute"); trackingToken="secret";</script>'
        "<style>.ad{display:block}</style>"
    )
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(body),
    )
    assert capture["acquisition_status"] == "available"
    assert capture["jd_completeness"] == "unknown"
    assert capture["source_format"] == "page"
    assert capture["body_text"] == "Systems Engineer\nApply at Example Labs."


@pytest.mark.parametrize(
    ("status", "body", "expected_status"),
    [
        (401, "Authentication required", "login_required"),
        (403, "Access denied", "login_required"),
        (404, "Not found", "expired"),
        (410, "Gone", "expired"),
        (200, "<h1>Sign in to view this job</h1>", "login_required"),
        (200, "<h1>Verify you are human</h1>", "login_required"),
        (200, "<h1>This job is no longer available</h1>", "expired"),
        (500, "Service failure", "unavailable"),
    ],
)
def test_login_expiry_and_http_failures_cannot_be_used_as_a_full_jd(status, body, expected_status):
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(body, status=status),
    )
    assert capture["acquisition_status"] == expected_status
    assert capture["jd_completeness"] == "unknown"


@pytest.mark.parametrize(
    ("body", "headers", "error"),
    [
        (b"%PDF-binary", {"content-type": "application/pdf"}, "unsupported_content_type"),
        (b"compressed", {"content-encoding": "gzip"}, "unsupported_encoding"),
        (b"x" * 2_000_001, {}, "response_too_large"),
        (b"short", {"content-length": "2000001"}, "response_too_large"),
    ],
    ids=["pdf", "compressed", "body-size", "declared-size"],
)
def test_response_content_and_size_limits_apply_to_injected_transports_too(body, headers, error):
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(body, headers=headers),
    )
    assert capture["acquisition_status"] == "unavailable"
    assert capture["body_text"] == ""
    assert capture["error_code"] == error


def test_dns_resolution_has_a_finite_total_deadline(monkeypatch):
    monkeypatch.setattr("career_evidence_graph.application_job_source.MAX_SECONDS", 0.02)

    def resolver(*args, **kwargs):
        threading.Event().wait(0.15)
        return public_resolver("jobs.example.com", 443)

    def forbidden(*args, **kwargs):
        pytest.fail("Expired resolution must not lead to HTTP")

    started = time.monotonic()
    capture = fetch_job_source(
        "https://jobs.example.com/role", resolver=resolver, transport=forbidden
    )
    assert time.monotonic() - started < 0.12
    assert capture["error_code"] == "timeout"


def test_redirects_are_finite_and_each_public_target_is_resolved_again():
    hosts = []

    def resolver(host, port, **kwargs):
        hosts.append(host)
        return public_resolver(host, port)

    def transport(url, **kwargs):
        return response("", status=302, headers={"location": f"/role/{len(hosts)}"})

    capture = fetch_job_source(
        "https://jobs.example.com/role", resolver=resolver, transport=transport
    )
    assert capture["error_code"] == "redirect_limit"
    assert len(hosts) == 4


def test_direct_json_ld_and_explicit_expiration_are_preserved():
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(
            json.dumps(posting(validThrough="2001-01-01T00:00:00Z")),
            headers={"content-type": "application/ld+json"},
        ),
    )
    assert capture["acquisition_status"] == "expired"
    assert capture["jd_completeness"] == "unknown"


def test_job_identifier_can_select_one_posting_and_other_posting_is_not_used():
    document = [
        posting(url=None, identifier={"@type": "PropertyValue", "value": "other"}, title="Other"),
        posting(
            url=None, identifier={"@type": "PropertyValue", "value": "role-123"}, title="Target"
        ),
    ]
    capture = fetch_job_source(
        "https://jobs.example.com/jobs/role-123",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(html_job(document)),
    )
    assert capture["jd_completeness"] == "full"
    assert capture["job_fields"]["title"] == "Target"


def test_single_posting_with_a_different_explicit_url_is_not_the_target_job():
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(html_job(posting(url="/different-role"))),
    )
    assert capture["jd_completeness"] == "unknown"


def test_relative_public_redirect_captures_final_job_and_records_provenance():
    def transport(url, **kwargs):
        if url.endswith("/alert"):
            return response("", status=302, headers={"location": "/role"})
        return response(html_job(posting(url="https://jobs.example.com/role")))

    capture = fetch_job_source(
        "https://jobs.example.com/alert", resolver=public_resolver, transport=transport
    )
    assert capture["url"] == "https://jobs.example.com/alert"
    assert capture["final_url"] == "https://jobs.example.com/role"
    assert capture["jd_completeness"] == "full"
    assert capture["redirects"] == [
        {
            "url": "https://jobs.example.com/alert",
            "status": 302,
            "location": "https://jobs.example.com/role",
        }
    ]


def test_malformed_json_ld_is_ignored_without_inventing_a_description():
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(
            '<h1>Role teaser</h1><script type="application/ld+json">'
            '{"@type": "JobPosting",</script>'
        ),
    )
    assert capture["body_text"] == "Role teaser"
    assert capture["jd_completeness"] == "unknown"


def test_default_total_deadline_also_bounds_a_close_connection_response_body(monkeypatch):
    monkeypatch.setattr("career_evidence_graph.application_job_source.MAX_SECONDS", 0.02)
    expired = threading.Event()

    class SlowBody(io.BytesIO):
        def read1(self, size):
            expired.wait(0.2)
            if expired.is_set():
                raise TimeoutError
            return super().read1(size)

    class Connection:
        def settimeout(self, timeout):
            pass

        def connect(self, address):
            pass

        def getpeername(self):
            return ("8.8.8.8", 443)

        def sendall(self, data):
            pass

        def do_handshake(self):
            pass

        def makefile(self, mode):
            return SlowBody(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                b"Connection: close\r\nContent-Length: 1\r\n\r\nx"
            )

        def close(self):
            pass

        def shutdown(self, how):
            expired.set()

    class Context:
        def wrap_socket(self, sock, **kwargs):
            return sock

    monkeypatch.setattr("ssl.create_default_context", lambda: Context())
    monkeypatch.setattr("socket.socket", lambda *args: Connection())
    started = time.monotonic()
    capture = fetch_job_source("https://jobs.example.com/role", resolver=public_resolver)
    assert time.monotonic() - started < 0.12
    assert capture["error_code"] == "timeout"


def test_declared_incomplete_body_cannot_claim_a_complete_job_posting():
    body = html_job(posting())
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(
            body, headers={"content-length": str(len(body.encode()) + 50)}
        ),
    )
    assert capture["acquisition_status"] == "unavailable"
    assert capture["jd_completeness"] == "unknown"
    assert capture["error_code"] == "incomplete_response"


def test_same_host_redirect_cannot_rebind_to_private_dns_address():
    queries = []
    requests = []

    def resolver(host, port, **kwargs):
        queries.append(host)
        if len(queries) == 1:
            return public_resolver(host, port)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.1", 443))]

    def transport(url, **kwargs):
        requests.append(url)
        return response("", status=302, headers={"location": "/second"})

    capture = fetch_job_source(
        "https://jobs.example.com/first", resolver=resolver, transport=transport
    )
    assert capture["error_code"] == "unsafe_address"
    assert len(queries) == 2
    assert requests == ["https://jobs.example.com/first"]


def test_capture_revision_binds_original_payload_and_selected_content():
    first = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(html_job(posting())),
    )
    second = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(html_job(posting()) + "<!-- changed -->"),
    )
    assert first["body_text"] == second["body_text"]
    assert first["content_sha256"] != second["content_sha256"]
    assert first["revision"] != second["revision"]


def test_full_capture_includes_hard_requirements_stored_outside_description():
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(
            html_job(
                posting(
                    description="<p>Join our systems team.</p>",
                    qualifications="<p>German C1 and a doctoral degree are required.</p>",
                    responsibilities=["Build Python services.", "Operate the Linux deployment."],
                    jobLocation={"@type": "Place", "address": {"addressLocality": "Zurich"}},
                )
            )
        ),
    )
    assert capture["jd_completeness"] == "full"
    assert "German C1 and a doctoral degree are required." in capture["body_text"]
    assert "Operate the Linux deployment." in capture["body_text"]
    assert "Zurich" in capture["body_text"]
    assert (
        capture["job_fields"]["qualifications"]
        == "<p>German C1 and a doctoral degree are required.</p>"
    )


def linkedin_dom_page():
    return """<html><head>
<link rel="canonical" href="https://ch.linkedin.com/jobs/view/systems-engineer-at-example-labs-12345">
<meta property="og:url" content="https://ch.linkedin.com/jobs/view/systems-engineer-at-example-labs-12345">
</head><body>
<h1 class="top-card-layout__title topcard__title">Systems Engineer</h1>
<div class="topcard__flavor-row"><a class="topcard__org-name-link">Example Labs</a>
<span class="topcard__flavor topcard__flavor--bullet">Sample City</span></div>
<section class="core-section-container description"><div>
<div class="description__text"><section class="show-more-less-html" data-max-lines="5">
<div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5">
<h2>Requirements</h2><ul><li>Use Python and Linux.</li></ul>
<p>Work authorisation is required. German C1 is mandatory.</p>
</div><button>Show more</button><button>Show less</button></section></div>
<ul class="description__job-criteria-list"><li class="description__job-criteria-item">
<h3 class="description__job-criteria-subheader">Employment type</h3>
<span class="description__job-criteria-text">Full-time</span></li></ul>
</div></section>
<section><h2 class="base-search-card__title">Similar role</h2>
<p>Rust for another employer.</p></section>
</body></html>"""


def test_linkedin_closed_dom_description_retains_criteria_and_tail_without_similar_jobs():
    capture = fetch_job_source(
        "https://www.linkedin.com/jobs/view/12345",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(linkedin_dom_page()),
    )
    assert capture["acquisition_status"] == "available"
    assert capture["jd_completeness"] == "full"
    assert capture["source_format"] == "job_posting"
    assert capture["extraction_method"] == "linkedin_dom"
    assert capture["job_fields"]["title"] == "Systems Engineer"
    assert capture["job_fields"]["company"] == "Example Labs"
    assert capture["job_fields"]["location"] == "Sample City"
    assert "German C1 is mandatory." in capture["body_text"]
    assert "Employment type\nFull-time" in capture["body_text"]
    assert "Show more" not in capture["body_text"]
    assert "Similar role" not in capture["body_text"]
    assert "Rust" not in capture["body_text"]


@pytest.mark.parametrize(
    "change",
    [
        lambda html: html.replace("labs-12345", "labs-99999", 1),
        lambda html: html.replace('property="og:url"', 'property="unrelated"'),
        lambda html: html.replace(
            "</head>",
            '<link rel="canonical" href="https://www.linkedin.com/jobs/view/12345"></head>',
        ),
        lambda html: html.replace("</h1>", '</h1><h1 class="topcard__title">Other role</h1>'),
        lambda html: html.replace(
            "</a>", '</a><a class="topcard__org-name-link">Other employer</a>'
        ),
        lambda html: html.replace("</div><button>Show more", "<button>Show more"),
        lambda html: html.replace("German C1 is mandatory.", "German C1…"),
        lambda html: html.replace(
            'class="show-more-less-html__markup ',
            'data-truncated="true" class="show-more-less-html__markup ',
        ),
        lambda html: html.replace('class="description__job-criteria-text"', 'class="unrelated"'),
        lambda html: html.replace('class="description__text"', 'class="unrelated"'),
    ],
    ids=[
        "canonical-conflict",
        "missing-og",
        "duplicate-canonical",
        "duplicate-title",
        "duplicate-company",
        "unclosed-description",
        "excerpt",
        "explicit-truncation",
        "incomplete-criterion",
        "wrong-description-context",
    ],
)
def test_linkedin_dom_fallback_rejects_identity_ambiguity_or_incomplete_scopes(change):
    capture = fetch_job_source(
        "https://www.linkedin.com/jobs/view/12345",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(change(linkedin_dom_page())),
    )
    assert capture["jd_completeness"] == "unknown"
    assert capture["job_fields"] == {}


@pytest.mark.parametrize(
    "text,status",
    [
        ("Sign in to view this job", "login_required"),
        ("This job is no longer available", "expired"),
    ],
)
def test_linkedin_dom_does_not_bypass_login_or_expired_page_guards(text, status):
    capture = fetch_job_source(
        "https://www.linkedin.com/jobs/view/12345",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(
            linkedin_dom_page().replace("<body>", f"<body><p>{text}</p>")
        ),
    )
    assert capture["acquisition_status"] == status
    assert capture["jd_completeness"] == "unknown"


def test_linkedin_dom_does_not_override_a_conflicting_json_ld_job_identity():
    body = linkedin_dom_page().replace(
        "</body>", html_job(posting(url="https://www.linkedin.com/jobs/view/99999")) + "</body>"
    )
    capture = fetch_job_source(
        "https://www.linkedin.com/jobs/view/12345",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(body),
    )
    assert capture["jd_completeness"] == "unknown"
    assert capture["job_fields"] == {}


def test_linkedin_dom_selectors_do_not_grant_full_status_on_other_hosts():
    capture = fetch_job_source(
        "https://jobs.example.com/jobs/view/12345",
        resolver=public_resolver,
        transport=lambda *args, **kwargs: response(linkedin_dom_page()),
    )
    assert capture["jd_completeness"] == "unknown"


def test_json_ld_location_is_available_under_application_location_key():
    capture = fetch_job_source(
        "https://jobs.example.com/role",
        resolver=public_resolver,
        transport=lambda *_args, **_kwargs: response(
            html_job(
                posting(
                    jobLocation={
                        "@type": "Place",
                        "address": {
                            "@type": "PostalAddress",
                            "addressLocality": "Zurich",
                            "addressCountry": "CH",
                        },
                    },
                    datePosted="2026-10-20",
                )
            )
        ),
    )
    assert capture["job_fields"]["location"] == "Zurich, CH"
    assert capture["job_fields"]["datePosted"] == "2026-10-20"
