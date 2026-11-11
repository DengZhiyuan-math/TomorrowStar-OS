"""Gmail intake requires actual read-only connector evidence, not model assertions."""

import json
import subprocess

import pytest

from career_evidence_graph.career_portal_data import PortalDataError


def _process(events, output=None, calls=None):
    def process(argv, **kwargs):
        if calls is not None:
            calls.append((argv, kwargs))
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "codex-cli synthetic\n", "")
        result = output or {"status": "readable"}
        stream = [*events, {"type": "structured_result", "result": result}]
        return subprocess.CompletedProcess(argv, 0, "\n".join(map(json.dumps, stream)) + "\n", "")

    return process


def _tool(identifier, name, arguments, data):
    return {
        "type": "item.completed",
        "item": {
            "id": identifier,
            "type": "mcp_tool_call",
            "server": "codex_apps",
            "tool": name,
            "status": "completed",
            "arguments": arguments,
            "result": {"structured_content": data, "content": []},
            "error": None,
        },
    }


def _mail_events():
    from career_evidence_graph.application_gmail import RECOMMENDATION_QUERY

    return [
        _tool(
            "search-1",
            "gmail.search_emails",
            {"query": RECOMMENDATION_QUERY, "max_results": 1},
            {"emails": [{"id": "synthetic-message-1"}], "next_page_token": ""},
        ),
        _tool(
            "read-1",
            "gmail.read_email",
            {"message_id": "synthetic-message-1", "format": "full"},
            {
                "id": "synthetic-message-1",
                "thread_id": "synthetic-thread-1",
                "internal_date": "1792195200000",
                "payload": {
                    "mime_type": "text/plain",
                    "headers": [
                        {"name": "From", "value": "Jobs <jobalerts-noreply@linkedin.com>"},
                        {"name": "Subject", "value": "Synthetic Python opportunities"},
                        {"name": "Date", "value": "Sat, 17 Oct 2026 00:00:00 +0000"},
                    ],
                    "body": {
                        "content": "Synthetic Python role\nhttps://www.linkedin.com/jobs/view/12345/"
                    },
                    "parts": None,
                },
            },
        ),
    ]


def test_model_claim_without_gmail_tool_evidence_is_unavailable(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    def process(argv, **kwargs):
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "codex-cli synthetic\n", "")
        output = {"status": "no_matches"}
        event = {"type": "structured_result", "result": output}
        return subprocess.CompletedProcess(argv, 0, json.dumps(event) + "\n", "")

    directory = tmp_path / "private-capture"
    result = read_recommendation_emails(directory, runner=process)
    assert result["status"] == "unavailable"
    assert result["reason"] == "tool_evidence_missing"
    assert result["emails"] == []
    assert (directory / "raw-events.jsonl").is_file()
    assert json.loads((directory / "result.json").read_text())["status"] == "unavailable"


def test_reader_builds_mail_from_real_search_and_read_results(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    result = read_recommendation_emails(tmp_path / "capture", runner=_process(_mail_events()))
    assert result["status"] == "readable"
    assert result["reason"] is None
    assert len(result["emails"]) == 1
    mail = result["emails"][0]
    assert mail["message_id"] == "synthetic-message-1"
    assert mail["from"] == "Jobs <jobalerts-noreply@linkedin.com>"
    assert mail["subject"] == "Synthetic Python opportunities"
    assert mail["body_text"] == "Synthetic Python role\nhttps://www.linkedin.com/jobs/view/12345/"
    assert mail["body_completeness"] == "full"
    assert mail["links"] == ["https://www.linkedin.com/jobs/view/12345/"]
    assert result["provenance"]["tool_call_ids"] == ["search-1", "read-1"]


def test_reader_retains_connector_cursor_and_capture_completeness(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    events[0]["item"]["result"]["structured_content"]["next_page_token"] = "opaque-next-page"
    events[1]["item"]["result"]["structured_content"]["payload"]["body"]["content"] = "x" * 150000
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "readable"
    provenance = result["provenance"]
    assert provenance["next_page_token"] == "opaque-next-page"
    assert provenance["has_more"] is True
    assert provenance["page_token"] is None
    assert provenance["returned_message_ids"] == ["synthetic-message-1"]
    assert provenance["truncated_message_ids"] == ["synthetic-message-1"]
    assert provenance["unread_message_ids"] == []


def test_reader_continues_exact_frozen_query_with_bound_context_and_real_token(tmp_path):
    from career_evidence_graph.application_gmail import (
        RECOMMENDATION_QUERY,
        read_recommendation_emails,
    )

    query = RECOMMENDATION_QUERY.replace("newer_than:7d", "after:2026/10/10 before:2026/10/18")
    events = _mail_events()
    events[0]["item"]["arguments"] = {
        "query": query,
        "max_results": 1,
        "next_page_token": "opaque-next-page",
    }
    directory = tmp_path / "capture"
    result = read_recommendation_emails(
        directory,
        runner=_process(events),
        query=query,
        page_token="opaque-next-page",
        account_context="account-revision-1",
        window_context="2026-10-10..2026-10-18",
    )
    assert result["status"] == "readable"
    assert result["provenance"]["query"] == query
    assert result["provenance"]["page_token"] == "opaque-next-page"
    assert result["provenance"]["account_context"] == "account-revision-1"
    assert result["provenance"]["window_context"] == "2026-10-10..2026-10-18"
    assert result["provenance"]["account_identity_status"] == "unverified"
    request = json.loads((directory / "request.json").read_text())
    assert request["page_token"] == "opaque-next-page"
    assert request["query"] == query
    assert "next_page_token" in (directory / "prompt.txt").read_text()


def test_reader_accepts_exact_epoch_window_from_search_trace(tmp_path):
    from career_evidence_graph.application_gmail import (
        RECOMMENDATION_QUERY,
        read_recommendation_emails,
    )

    query = RECOMMENDATION_QUERY.replace("newer_than:7d", "after:1792108800 before:1792281600")
    events = _mail_events()
    events[0]["item"]["arguments"]["query"] = query
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events), query=query)
    assert result["status"] == "readable"
    assert result["provenance"]["query"] == query
    assert result["provenance"]["returned_message_ids"] == ["synthetic-message-1"]


def test_epoch_query_accepts_positive_minimum_and_supported_maximum():
    from career_evidence_graph.application_gmail import (
        RECOMMENDATION_QUERY,
        validate_recommendation_query,
    )

    query = RECOMMENDATION_QUERY.replace("newer_than:7d", "after:1 before:253402300799")
    assert validate_recommendation_query(query) == query


@pytest.mark.parametrize(
    "window",
    [
        "after:0 before:2",
        "after:-1 before:2",
        "after:01 before:2",
        "after:1.0 before:2",
        "after:2 before:2",
        "after:3 before:2",
        "after:1 before:253402300800",
        "after:1 before:99999999999999999999",
    ],
)
def test_epoch_query_rejects_invalid_or_unbounded_seconds_before_capture(tmp_path, window):
    from career_evidence_graph.application_gmail import (
        RECOMMENDATION_QUERY,
        read_recommendation_emails,
    )

    directory = tmp_path / "capture"
    query = RECOMMENDATION_QUERY.replace("newer_than:7d", window)
    with pytest.raises(PortalDataError) as error:
        read_recommendation_emails(directory, runner=_process([]), query=query)
    assert error.value.code == "gmail_query_invalid"
    assert not directory.exists()


@pytest.mark.parametrize("address_field", ["email_address", "emailAddress", "email"])
def test_verified_mailbox_profile_binds_two_pages_without_enabling_profile_during_search(
    tmp_path, address_field
):
    from career_evidence_graph.application_gmail import (
        GMAIL_APP_ID,
        RECOMMENDATION_QUERY,
        read_recommendation_emails,
    )

    calls = []

    def process(argv, **kwargs):
        if argv[-1] == "--version":
            return _process([])(argv, **kwargs)
        phase = "profile" if kwargs["cwd"].name == "profile" else "search"
        calls.append((phase, argv))
        if phase == "profile":
            address = (
                "User@Example.invalid"
                if kwargs["cwd"].parent.name == "page-1"
                else "user@example.invalid"
            )
            events = [_tool("profile-1", "gmail.get_profile", {}, {address_field: address})]
        else:
            events = _mail_events()
            events[0]["item"]["result"]["structured_content"]["next_page_token"] = "next-page"
            if kwargs["cwd"].name == "page-2":
                events[0]["item"]["arguments"]["next_page_token"] = "next-page"
        return _process(events)(argv, **kwargs)

    first = read_recommendation_emails(tmp_path / "page-1", runner=process, verify_account=True)
    second = read_recommendation_emails(
        tmp_path / "page-2",
        runner=process,
        verify_account=True,
        expected_mailbox_identity=first["provenance"]["mailbox_identity"],
        query=RECOMMENDATION_QUERY,
        page_token="next-page",
        account_context="local-account-revision",
        window_context="frozen-window",
    )
    assert first["status"] == second["status"] == "readable"
    assert first["provenance"]["account_identity_status"] == "verified"
    assert second["provenance"]["account_identity_status"] == "verified"
    assert first["provenance"]["mailbox_identity"] == second["provenance"]["mailbox_identity"]
    assert len(first["provenance"]["mailbox_identity"]) == 64
    assert "User@Example.invalid" not in json.dumps(first)
    assert [phase for phase, _ in calls] == ["profile", "search", "profile", "search"]
    for phase, argv in calls:
        flags = {argv[index + 1] for index, value in enumerate(argv) if value == "--config"}
        enabled_tools = {flag for flag in flags if ".tools." in flag}
        assert enabled_tools == (
            {f"apps.{GMAIL_APP_ID}.tools.get_profile.enabled=true"}
            if phase == "profile"
            else {
                f"apps.{GMAIL_APP_ID}.tools.search_emails.enabled=true",
                f"apps.{GMAIL_APP_ID}.tools.read_email.enabled=true",
            }
        )


def test_changed_connector_mailbox_refuses_cursor_before_any_second_search(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    profile_address = "first@example.invalid"
    phases = []

    def process(argv, **kwargs):
        if argv[-1] == "--version":
            return _process([])(argv, **kwargs)
        phase = "profile" if kwargs["cwd"].name == "profile" else "search"
        phases.append(phase)
        events = (
            [_tool("profile-1", "gmail.get_profile", {}, {"emailAddress": profile_address})]
            if phase == "profile"
            else _mail_events()
        )
        return _process(events)(argv, **kwargs)

    first = read_recommendation_emails(tmp_path / "first", runner=process, verify_account=True)
    profile_address = "second@example.invalid"
    second = read_recommendation_emails(
        tmp_path / "second",
        runner=process,
        verify_account=True,
        expected_mailbox_identity=first["provenance"]["mailbox_identity"],
        page_token="old-mailbox-cursor",
        account_context="unchanged-local-context",
        window_context="same-window",
    )
    assert second["status"] == "unavailable"
    assert second["reason"] == "mailbox_identity_changed"
    assert second["emails"] == []
    assert second["provenance"]["account_identity_status"] == "unverified"
    assert phases == ["profile", "search", "profile"]
    assert (tmp_path / "second" / "profile" / "raw-events.jsonl").is_file()


@pytest.mark.parametrize(
    "events",
    [
        [],
        [_tool("profile-1", "gmail.get_profile", {}, {})],
        [_tool("profile-1", "gmail.get_profile", {}, {"email_address": "not-an-address"})],
        [_tool("profile-1", "gmail.get_profile", {"email_address": "fake@example.invalid"}, {})],
        [_tool("search-1", "gmail.search_emails", {}, {})],
    ],
)
def test_unknown_profile_never_admits_mail_search_even_when_model_claims_readable(tmp_path, events):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    phases = []

    def process(argv, **kwargs):
        if argv[-1] != "--version":
            phases.append(kwargs["cwd"].name)
        return _process(events)(argv, **kwargs)

    result = read_recommendation_emails(tmp_path / "capture", runner=process, verify_account=True)
    assert result["status"] == "unavailable"
    assert result["reason"] == "mailbox_identity_unavailable"
    assert result["emails"] == []
    # One read-only profile retry (2026-11-08); no search either way.
    assert phases == ["profile", "profile-retry"]


@pytest.mark.parametrize(
    "addresses",
    [
        {"email_address": "one@example.invalid", "emailAddress": "two@example.invalid"},
        {"email_address": "one@example.invalid", "email": "two@example.invalid"},
        {"emailAddress": "one@example.invalid", "email": "two@example.invalid"},
    ],
)
def test_conflicting_connector_profile_address_fields_do_not_choose_one_account(
    tmp_path, addresses
):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    phases = []

    def process(argv, **kwargs):
        if argv[-1] == "--version":
            return _process([])(argv, **kwargs)
        phases.append(kwargs["cwd"].name)
        events = (
            [
                _tool(
                    "profile-1",
                    "gmail.get_profile",
                    {},
                    addresses,
                )
            ]
            if kwargs["cwd"].name.startswith("profile")
            else _mail_events()
        )
        return _process(events)(argv, **kwargs)

    result = read_recommendation_emails(tmp_path / "capture", runner=process, verify_account=True)
    assert result["status"] == "unavailable"
    assert result["reason"] == "mailbox_identity_unavailable"
    assert phases == ["profile", "profile-retry"]


def test_a_profile_call_without_the_gmail_tool_is_retried_once(tmp_path):
    """2026-11-08: about a third of calls started before the Gmail connector loaded."""
    from career_evidence_graph.application_gmail import read_recommendation_emails

    phases = []

    def process(argv, **kwargs):
        if argv[-1] == "--version":
            return _process([])(argv, **kwargs)
        phases.append(kwargs["cwd"].name)
        name = kwargs["cwd"].name
        events = (
            []
            if name == "profile"
            else [
                _tool("profile-1", "gmail.get_profile", {}, {"email_address": "a@example.invalid"})
            ]
            if name == "profile-retry"
            else _mail_events()
        )
        return _process(events)(argv, **kwargs)

    result = read_recommendation_emails(tmp_path / "capture", runner=process, verify_account=True)
    assert phases[:2] == ["profile", "profile-retry"]
    assert result["provenance"]["account_identity_status"] == "verified"
    assert result["status"] == "readable"


@pytest.mark.parametrize(
    "arguments",
    [
        {"verify_account": "false"},
        {"expected_mailbox_identity": "a" * 64},
        {"verify_account": True, "expected_mailbox_identity": "not-an-identity"},
        {"verify_account": True, "expected_mailbox_identity": ["identity"]},
    ],
)
def test_mailbox_expectation_cannot_be_silently_ignored_or_malformed(tmp_path, arguments):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    directory = tmp_path / "capture"
    with pytest.raises(PortalDataError) as error:
        read_recommendation_emails(directory, runner=_process([]), **arguments)
    assert error.value.code == "gmail_context_invalid"
    assert not directory.exists()


def test_cancelled_reader_does_not_start_search_after_successful_profile(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    phases = []

    def process(argv, **kwargs):
        if argv[-1] != "--version":
            phases.append(kwargs["cwd"].name)
        return _process(
            [_tool("profile-1", "gmail.get_profile", {}, {"email_address": "user@example.invalid"})]
        )(argv, **kwargs)

    result = read_recommendation_emails(
        tmp_path / "capture", runner=process, verify_account=True, admit_search=lambda: False
    )
    assert result["status"] == "unavailable"
    assert result["reason"] == "reader_interrupted"
    assert result["emails"] == []
    assert phases == ["profile"]


@pytest.mark.parametrize(
    "query",
    [
        "from:anywhere",
        "newer_than:0d {senders}",
        "newer_than:366d {senders}",
        "newer_than:7d {senders} OR from:anywhere",
        "after:2026/02/30 before:2026/10/18 {senders}",
        "after:2026/10/18 before:2026/10/10 {senders}",
    ],
)
def test_reader_rejects_query_outside_fixed_sender_and_finite_window_before_capture(
    tmp_path, query
):
    from career_evidence_graph.application_gmail import (
        RECOMMENDATION_QUERY,
        read_recommendation_emails,
    )

    query = query.format(senders=RECOMMENDATION_QUERY.partition(" ")[2])
    directory = tmp_path / "capture"
    with pytest.raises(PortalDataError) as error:
        read_recommendation_emails(directory, runner=_process([]), query=query)
    assert error.value.code == "gmail_query_invalid"
    assert not directory.exists()


@pytest.mark.parametrize(
    "token", [["private-token"], {"private": "token"}, True, "x" * 4097, "x\ny"]
)
def test_invalid_connector_cursor_is_unavailable_instead_of_a_successful_page(tmp_path, token):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    events[0]["item"]["result"]["structured_content"]["next_page_token"] = token
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "unavailable"
    assert result["reason"] == "search_evidence_invalid"
    assert result["emails"] == []
    assert "private-token" not in json.dumps(result)


@pytest.mark.parametrize(
    "arguments,reason",
    [
        ({"page_token": ""}, "gmail_cursor_invalid"),
        ({"page_token": ["token"]}, "gmail_cursor_invalid"),
        ({"page_token": "x\ny"}, "gmail_cursor_invalid"),
        ({"page_token": "token"}, "gmail_context_invalid"),
        ({"account_context": {}}, "gmail_context_invalid"),
        ({"window_context": ""}, "gmail_context_invalid"),
    ],
)
def test_cursor_requests_require_bounded_tokens_and_explicit_local_context_before_capture(
    tmp_path, arguments, reason
):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    directory = tmp_path / "capture"
    with pytest.raises(PortalDataError) as error:
        read_recommendation_emails(directory, runner=_process([]), **arguments)
    assert error.value.code == reason
    assert not directory.exists()


@pytest.mark.parametrize("limit", [0, 11, True, "1"])
def test_reader_rejects_unbounded_limits_before_creating_records(tmp_path, limit):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    directory = tmp_path / "capture"
    with pytest.raises(PortalDataError) as error:
        read_recommendation_emails(directory, runner=_process([]), max_results=limit)
    assert error.value.code == "gmail_limit_invalid"
    assert not directory.exists()


def test_multipart_mail_keeps_inert_html_links_and_uses_actual_plain_body(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    payload = events[1]["item"]["result"]["structured_content"]["payload"]
    payload.update(
        {
            "mime_type": "multipart/alternative",
            "body": {"content": None},
            "parts": [
                {"mime_type": "text/plain", "body": {"content": "Actual synthetic text"}},
                {
                    "mime_type": "text/html",
                    "body": {
                        "content": '<script>do not execute</script><a href="https://www.linkedin.com/jobs/view/54321/">Role</a>'
                    },
                },
            ],
        }
    )
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "readable"
    assert result["emails"][0]["body_text"] == "Actual synthetic text"
    assert result["emails"][0]["links"] == ["https://www.linkedin.com/jobs/view/54321/"]
    assert result["emails"][0]["body_completeness"] == "full"


def test_unread_text_mime_part_keeps_visible_body_as_pending_instead_of_full(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    payload = events[1]["item"]["result"]["structured_content"]["payload"]
    payload["parts"] = [
        {
            "mime_type": "text/plain",
            "body": {"content": None, "attachment_id": "unread-body-part"},
        }
    ]
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "readable"
    assert result["emails"][0]["body_completeness"] == "excerpt"
    assert result["provenance"]["truncated_message_ids"] == ["synthetic-message-1"]


def test_oversized_body_is_bounded_and_disclosed_while_original_trace_is_retained(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    events[1]["item"]["result"]["structured_content"]["payload"]["body"]["content"] = "x" * 150000
    directory = tmp_path / "capture"
    result = read_recommendation_emails(directory, runner=_process(events))
    assert result["status"] == "readable"
    assert len(result["emails"][0]["body_text"]) == 131072
    assert result["emails"][0]["body_completeness"] == "excerpt"
    assert "x" * 150000 in (directory / "raw-events.jsonl").read_text()


@pytest.mark.parametrize(
    "failure,reason",
    [("missing", "cli_missing"), ("timeout", "model_timeout"), ("auth", "login_required")],
)
def test_transport_failures_return_content_free_unavailable_and_keep_private_evidence(
    tmp_path, failure, reason
):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    def process(argv, **kwargs):
        if failure == "missing":
            raise FileNotFoundError("private CLI path sentinel")
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "codex-cli synthetic\n", "")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(
                argv, 180, output="private partial trace sentinel", stderr="private stderr sentinel"
            )
        return subprocess.CompletedProcess(
            argv, 1, "", "not authenticated; private account sentinel"
        )

    directory = tmp_path / "capture"
    result = read_recommendation_emails(directory, runner=process)
    assert result["status"] == "unavailable"
    assert result["reason"] == reason
    assert result["emails"] == []
    assert "sentinel" not in json.dumps(result)
    assert (directory / "model-result.json").exists()
    assert (directory / "raw-events.jsonl").exists()


def test_extra_tool_attempt_is_rejected_even_when_it_has_no_completion(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    events.insert(
        0,
        {
            "type": "item.started",
            "item": {
                "type": "command_execution",
                "command": "private sentinel",
                "status": "in_progress",
            },
        },
    )
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "unavailable"
    assert result["reason"] == "unauthorized_tool"
    assert result["emails"] == []


def test_missing_body_is_unavailable_and_is_never_marked_full(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    events[1]["item"]["result"]["structured_content"]["payload"]["body"] = {
        "content": None,
        "attachment_id": "unread-body",
    }
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "unavailable"
    assert result["reason"] == "mail_content_unavailable"
    assert result["emails"] == []


@pytest.mark.parametrize(
    "mutation", ["status-array", "result-null", "headers-invalid", "id-array", "parts-invalid"]
)
def test_malformed_tool_or_model_data_fails_closed_without_leaking_input(tmp_path, mutation):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    output = {"status": "readable"}
    if mutation == "status-array":
        output["status"] = ["private sentinel"]
    elif mutation == "result-null":
        events[1]["item"]["result"] = None
    elif mutation == "headers-invalid":
        events[1]["item"]["result"]["structured_content"]["payload"]["headers"] = [
            "private sentinel"
        ]
    elif mutation == "id-array":
        events[0]["item"]["result"]["structured_content"]["emails"][0]["id"] = ["private sentinel"]
    else:
        events[1]["item"]["result"]["structured_content"]["payload"]["parts"] = "private sentinel"
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events, output))
    assert result["status"] == "unavailable"
    assert result["reason"] in {
        "model_output_invalid",
        "tool_evidence_invalid",
        "search_evidence_invalid",
    }
    assert result["emails"] == []
    assert "sentinel" not in json.dumps(result)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("bool-limit", "search_evidence_invalid"),
        ("read-first", "read_evidence_invalid"),
        ("failed-result", "gmail_tool_failed"),
        ("unfinished-read", "tool_evidence_incomplete"),
        ("duplicate-call-id", "tool_evidence_invalid"),
    ],
)
def test_search_read_sequence_requires_exact_successful_bounded_tool_calls(
    tmp_path, mutation, reason
):
    from copy import deepcopy

    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    if mutation == "bool-limit":
        events[0]["item"]["arguments"]["max_results"] = True
    elif mutation == "read-first":
        events.reverse()
    elif mutation == "failed-result":
        events[1]["item"]["result"]["is_error"] = True
    elif mutation == "unfinished-read":
        started = deepcopy(events[1])
        started["type"] = "item.started"
        started["item"]["id"] = "unfinished"
        started["item"]["status"] = "in_progress"
        events.append(started)
    else:
        events[1]["item"]["id"] = events[0]["item"]["id"]
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "unavailable"
    assert result["reason"] == reason
    assert result["emails"] == []


@pytest.mark.parametrize("mutation", ["different-query", "duplicate-start"])
def test_started_tool_identity_cannot_change_or_repeat_before_completion(tmp_path, mutation):
    from copy import deepcopy

    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    started = deepcopy(events[0])
    started["type"] = "item.started"
    started["item"]["status"] = "in_progress"
    if mutation == "different-query":
        started["item"]["arguments"]["query"] = "from:anywhere"
        events.insert(0, started)
    else:
        events[:0] = [started, deepcopy(started)]
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "unavailable"
    assert result["reason"] == "tool_evidence_invalid"
    assert result["emails"] == []


def test_symlink_ancestor_cannot_redirect_private_mail_capture(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    target = tmp_path / "actual"
    (target / "nested").mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(PortalDataError) as error:
        read_recommendation_emails(alias / "nested" / "capture", runner=_process([]))
    assert error.value.code == "gmail_directory_invalid"
    assert not (target / "nested" / "capture").exists()


def test_ignored_configuration_is_unavailable_even_if_some_tools_succeeded(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    events.insert(
        0,
        {
            "type": "item.completed",
            "item": {
                "type": "error",
                "message": "Codex is ignoring 1 unrecognized configuration setting. sentinel",
            },
        },
    )
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "unavailable"
    assert result["reason"] == "configuration_rejected"
    assert "sentinel" not in json.dumps(result)


def test_attachment_text_is_not_promoted_to_the_email_body(tmp_path):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    payload = events[1]["item"]["result"]["structured_content"]["payload"]
    payload["filename"] = "untrusted-attachment.txt"
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "unavailable"
    assert result["reason"] == "mail_content_unavailable"


def test_empty_actual_search_is_no_matches_and_retains_pagination_boundary(tmp_path):
    from career_evidence_graph.application_gmail import (
        RECOMMENDATION_QUERY,
        read_recommendation_emails,
    )

    search = _tool(
        "search-1",
        "gmail.search_emails",
        {"query": RECOMMENDATION_QUERY, "max_results": 1},
        {"emails": [], "next_page_token": ""},
    )
    result = read_recommendation_emails(
        tmp_path / "capture", runner=_process([search], {"status": "no_matches"})
    )
    assert result["status"] == "no_matches"
    assert result["reason"] is None
    assert result["emails"] == []
    assert result["provenance"]["has_more"] is False


def test_transport_enables_only_two_gmail_read_tools_with_bare_keys_and_no_shell(tmp_path):
    from career_evidence_graph.application_gmail import GMAIL_APP_ID, read_recommendation_emails

    calls = []
    read_recommendation_emails(tmp_path / "capture", runner=_process(_mail_events(), calls=calls))
    argv, options = calls[-1]
    flags = [argv[index + 1] for index, value in enumerate(argv) if value == "--config"]
    assert f"apps.{GMAIL_APP_ID}.enabled=true" in flags
    assert f"apps.{GMAIL_APP_ID}.default_tools_enabled=false" in flags
    assert "apps._default.enabled=false" in flags
    assert f"apps.{GMAIL_APP_ID}.destructive_enabled=false" in flags
    assert {flag for flag in flags if ".tools." in flag} == {
        f"apps.{GMAIL_APP_ID}.tools.search_emails.enabled=true",
        f"apps.{GMAIL_APP_ID}.tools.read_email.enabled=true",
    }
    assert 'web_search="disabled"' in flags
    assert "features.shell_tool=false" in flags
    assert "features.multi_agent=false" in flags
    assert options["shell"] is False
    assert argv[argv.index("--sandbox") + 1] == "read-only"


def test_gmail_calls_keep_their_one_app_enabled_and_the_rest_disabled(tmp_path):
    # The generic exec disables account apps; a Gmail call enables only its connector,
    # so "--disable apps" would override that and leave no Gmail tool (installed MC-11).
    from career_evidence_graph.application_gmail import (
        _read_mailbox_identity,
        read_recommendation_emails,
    )

    calls = []
    read_recommendation_emails(tmp_path / "capture", runner=_process(_mail_events(), calls=calls))
    with pytest.raises(Exception, match="mailbox_identity_unavailable"):
        _read_mailbox_identity(tmp_path / "profile", _process([], calls=calls))
    execs = [argv for argv, _ in calls if len(argv) > 1 and argv[1] == "exec"]
    assert len(execs) == 2  # the mail search, then a profile verification
    for argv in execs:
        flags = [argv[index + 1] for index, value in enumerate(argv) if value == "--config"]
        disabled = {argv[index + 1] for index, value in enumerate(argv) if value == "--disable"}
        assert "features.apps=true" in flags
        assert "apps" not in disabled
        assert {"memories", "plugins", "hooks"} <= disabled


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("wrong-id", "read_evidence_invalid"),
        ("missing-read", "read_evidence_missing"),
        ("wrong-query", "search_evidence_invalid"),
        ("write-tool", "unauthorized_tool"),
        ("wrong-sender", "sender_not_allowed"),
        ("model-emails", "model_output_invalid"),
    ],
)
def test_unverified_sources_and_model_created_mail_never_cross_the_reader_boundary(
    tmp_path, mutation, reason
):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    output = {"status": "readable"}
    if mutation == "wrong-id":
        events[1]["item"]["result"]["structured_content"]["id"] = "invented"
    elif mutation == "missing-read":
        events.pop()
    elif mutation == "wrong-query":
        events[0]["item"]["arguments"]["query"] = "from:anywhere"
    elif mutation == "write-tool":
        events.append(_tool("write", "gmail.send_email", {}, {}))
    elif mutation == "wrong-sender":
        events[1]["item"]["result"]["structured_content"]["payload"]["headers"][0]["value"] = (
            "untrusted@example.invalid"
        )
    else:
        output["emails"] = [{"message_id": "invented", "body_text": "private sentinel"}]
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events, output))
    assert result["status"] == "unavailable"
    assert result["reason"] == reason
    assert result["emails"] == []


@pytest.mark.parametrize(
    "mutation,reason", [("header", "mail_metadata_invalid"), ("mime", "mail_content_invalid")]
)
def test_metadata_and_mime_structure_have_finite_capture_limits(tmp_path, mutation, reason):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    payload = events[1]["item"]["result"]["structured_content"]["payload"]
    if mutation == "header":
        payload["headers"][1]["value"] = "x" * 5000
    else:
        payload["parts"] = [{"mime_type": "text/plain", "body": {"content": "x"}}] * 257
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "unavailable"
    assert result["reason"] == reason
    assert result["emails"] == []


@pytest.mark.parametrize("domain", ["jobalert.indeed.com", "match.indeed.com"])
def test_indeed_query_domains_are_verified_as_domains_instead_of_mailbox_addresses(
    tmp_path, domain
):
    from career_evidence_graph.application_gmail import read_recommendation_emails

    events = _mail_events()
    events[1]["item"]["result"]["structured_content"]["payload"]["headers"][0]["value"] = (
        f"Synthetic <alerts@{domain}>"
    )
    result = read_recommendation_emails(tmp_path / "capture", runner=_process(events))
    assert result["status"] == "readable"
    assert result["emails"][0]["from"] == f"Synthetic <alerts@{domain}>"


def test_processing_inspection_uses_actual_label_and_message_state(tmp_path):
    from career_evidence_graph.application_gmail import process_recommendation_email

    result = process_recommendation_email(
        tmp_path / "inspect",
        message_id="captured-mail",
        label_name="Configured Jobs",
        operation="inspect",
        runner=_process(
            [
                _tool(
                    "labels",
                    "gmail.list_labels",
                    {"label_names": ["Configured Jobs"]},
                    {"labels": [{"id": "Label_1", "name": "Configured Jobs"}]},
                ),
                _tool(
                    "mail",
                    "gmail.read_email",
                    {"message_id": "captured-mail", "format": "full"},
                    {"id": "captured-mail", "label_ids": ["Label_1", "UNREAD"]},
                ),
            ],
            {"status": "complete"},
        ),
    )
    assert result == {"status": "complete", "labeled": True, "archived": True}


@pytest.mark.parametrize(
    "operation,tool,arguments",
    [
        (
            "label",
            "gmail.apply_labels_to_emails",
            {
                "message_ids": ["captured-mail"],
                "add_label_names": ["Configured Jobs"],
                "create_missing_labels": True,
            },
        ),
        (
            "archive",
            "gmail.batch_modify_email",
            {"message_ids": ["captured-mail"], "remove_labels": ["INBOX"]},
        ),
    ],
)
def test_processing_only_modifies_the_captured_message(tmp_path, operation, tool, arguments):
    from career_evidence_graph.application_gmail import process_recommendation_email

    result = process_recommendation_email(
        tmp_path / operation,
        message_id="captured-mail",
        label_name="Configured Jobs",
        operation=operation,
        runner=_process([_tool("change", tool, arguments, {})], {"status": "complete"}),
    )
    assert result == {"status": "complete"}


def test_processing_model_claim_and_thread_archive_cannot_confirm_success(tmp_path):
    from career_evidence_graph.application_gmail import process_recommendation_email

    for name, events in (
        ("claim", []),
        (
            "thread",
            [_tool("change", "gmail.archive_emails", {"thread_ids": ["captured-thread"]}, {})],
        ),
        (
            "other-message",
            [
                _tool(
                    "change",
                    "gmail.batch_modify_email",
                    {"message_ids": ["uncaptured-mail"], "remove_labels": ["INBOX"]},
                    {},
                )
            ],
        ),
    ):
        result = process_recommendation_email(
            tmp_path / name,
            message_id="captured-mail",
            label_name="Configured Jobs",
            operation="archive",
            runner=_process(events, {"status": "complete"}),
        )
        assert result["status"] == "needs_recheck"
