"""Codex Computer Use fills in the user's everyday Chrome (2026-11-08)."""

import json
import subprocess

import pytest

from career_evidence_graph.application_computer_use import REPORT_SCHEMA, fill_context, run_fill

REPORT = {
    "status": "ready_for_review",
    "summary": "All fields filled; CV attached.",
    "filled": ["Name", "Resume"],
    "unanswered": [],
}


class Process:
    def __init__(self, argv, *, report, code=0, **options):
        self.argv, self.options, self.code = argv, options, code
        if report is not None:
            path = argv[argv.index("--output-last-message") + 1]
            with open(path, "w", encoding="utf-8") as file:
                file.write(report if isinstance(report, str) else json.dumps(report))

    def wait(self, timeout=None):
        return self.code

    def poll(self):
        return self.code


def test_a_fill_runs_codex_with_the_users_own_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", "/isolated/codex-home")
    seen = []

    def popen(argv, **options):
        process = Process(argv, report=REPORT, **options)
        seen.append(process)
        return process

    context = {"job_url": "https://jobs.example.invalid/1", "resume_path": "/r.pdf"}
    report = run_fill("/bin/codex", context, tmp_path, popen=popen)
    assert {key: report[key] for key in REPORT} == REPORT
    (process,) = seen
    # The user's own Codex home carries their Computer Use plugin; the isolated
    # model-call home has none, and no config or plugin is disabled.
    assert "CODEX_HOME" not in process.options["env"]
    assert "--ignore-user-config" not in process.argv
    assert process.argv[:2] == ["/bin/codex", "exec"]
    saved = json.loads((tmp_path / report["run"].split("/")[-1] / "context.json").read_text())
    assert saved == context
    prompt = process.argv[-1]
    assert "Never click Submit" in prompt and "everyday Google Chrome" in prompt
    # Computer Use is the only route: no shell to script Chrome through osascript.
    assert json.dumps(context) in prompt and "osascript" in prompt
    disabled = {process.argv[i + 1] for i, arg in enumerate(process.argv) if arg == "--disable"}
    assert disabled == {"shell_tool", "unified_exec"}
    assert json.loads((tmp_path / report["run"].split("/")[-1] / "report-schema.json").read_text())
    assert REPORT_SCHEMA["required"] == ["status", "summary", "filled", "unanswered"]


@pytest.mark.parametrize(
    ("report", "code"),
    [(None, 0), ("not json", 0), ({"status": "sent"}, 0), (REPORT, 1)],
)
def test_a_missing_or_invalid_report_is_a_failed_fill(tmp_path, report, code):
    result = run_fill(
        "/bin/codex",
        {"job_url": "u"},
        tmp_path,
        popen=lambda argv, **options: Process(argv, report=report, code=code, **options),
    )
    assert result["status"] == "failed"


def test_a_fill_that_outlasts_its_budget_is_stopped(tmp_path):
    stopped = []

    class Slow(Process):
        def wait(self, timeout=None):
            if not stopped:
                raise subprocess.TimeoutExpired("codex", timeout)
            return -15

        def terminate(self):
            stopped.append(True)

    result = run_fill(
        "/bin/codex",
        {"job_url": "u"},
        tmp_path,
        timeout=1,
        popen=lambda argv, **options: Slow(argv, report=None, **options),
    )
    assert result["status"] == "failed" and stopped == [True]


def test_the_context_names_the_job_files_and_records():
    job = {
        "company": "Example",
        "role_title": "Engineer",
        "job_url": "https://jobs.example.invalid/1",
        "file_path": "/attachments/resume.pdf",
        "materials": [{"kind": "cover_letter", "file_path": "/materials/letter.pdf"}],
    }
    reference = {"confirmed_answers": [{"question": "Email", "value": "a@b.invalid"}]}
    context = fill_context(job, reference, "Dear team")
    assert context["resume_path"] == "/attachments/resume.pdf"
    assert context["cover_letter_path"] == "/materials/letter.pdf"
    assert context["confirmed_answers"] == reference["confirmed_answers"]
    assert context["career_facts"] == [] and context["cover_letter_text"] == "Dear team"


@pytest.mark.parametrize(
    ("email", "found"),
    [
        (
            {
                "from": "Keyrock <no-reply@ashbyhq.com>",
                "subject": "Thank you for applying to Keyrock",
                "body_text": "We have received your application.",
            },
            True,
        ),
        ({"from": "x", "subject": "Keyrock", "body_text": "We've received your application"}, True),
        # Another company's confirmation, or Keyrock news without a confirmation.
        ({"from": "x", "subject": "Thank you for applying to Mistral", "body_text": ""}, False),
        ({"from": "x", "subject": "Keyrock newsletter", "body_text": "Market update"}, False),
    ],
)
def test_a_confirmation_mail_names_the_company_and_confirms(email, found):
    from career_evidence_graph.application_computer_use import confirmation_email

    assert (confirmation_email([email], "Keyrock") is email) is found


def test_confirmations_search_one_company_since_the_fill(tmp_path):
    from career_evidence_graph.application_computer_use import read_confirmations
    from career_evidence_graph.application_gmail import validate_recommendation_query

    seen = []

    def reader(directory, *, query, max_results):
        seen.append((query, max_results))
        return {"status": "readable", "emails": [{"subject": "ok"}]}

    assert read_confirmations("Keyrock", 1794146430.5, tmp_path, reader=reader) == [
        {"subject": "ok"}
    ]
    assert seen == [('after:1794146430 "Keyrock" (application OR applying)', 5)]
    assert validate_recommendation_query(seen[0][0]) == seen[0][0]
    assert (
        read_confirmations(
            "Keyrock", 1, tmp_path, reader=lambda *_a, **_k: {"status": "unavailable"}
        )
        == []
    )
    from career_evidence_graph.career_portal_data import PortalDataError

    with pytest.raises(PortalDataError):
        validate_recommendation_query('after:1 "Keyrock" (application OR applying) OR from:x')
