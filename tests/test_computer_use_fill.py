"""Codex Computer Use fills in the user's everyday Chrome (2026-11-08)."""

import json
import shutil
import subprocess
from pathlib import Path

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
    # 2026-11-08 (SAEKI): a refused first node_repl call made the fill give up.
    assert "runs through the node_repl tool" in prompt and "instead of stopping" in prompt
    # 2026-11-08: a pre-opened page and short paths; no deliberate human pace.
    assert "page_opened" in prompt
    # 2026-11-09: text typed into the macOS open panel arrived as "aaaa"; files go
    # through upload(), which sets the Go to field's value instead.
    assert 'typed text arrives there as "aaaa"' in prompt
    assert "async function upload(control, path)" in prompt and "PathTextField" in prompt
    assert "human pace" not in prompt
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


def test_files_are_staged_under_short_clear_names(tmp_path):
    from career_evidence_graph.application_computer_use import stage_files

    resume, letter = tmp_path / "resume.pdf", tmp_path / "letter.pdf"
    resume.write_bytes(b"cv")
    letter.write_bytes(b"letter")
    folder = tmp_path / "Apply"
    folder.mkdir()
    (folder / "Old_Name_CV.pdf").write_bytes(b"previous job")
    (folder / "notes.txt").write_text("the user's own file")
    context = {
        "resume_path": str(resume),
        "cover_letter_path": str(letter),
        "confirmed_answers": [{"question": "Full name", "value": "Zhiyuan Deng"}],
    }
    staged = stage_files(context, folder)
    assert sorted(path.name for path in folder.iterdir()) == [
        "Zhiyuan_Deng_CV.pdf",
        "Zhiyuan_Deng_Cover_Letter.pdf",
        "notes.txt",
    ]
    assert staged["resume_path"] == str(folder / "Zhiyuan_Deng_CV.pdf")
    assert (folder / "Zhiyuan_Deng_Cover_Letter.pdf").read_bytes() == b"letter"
    assert context["resume_path"] == str(resume)


def test_a_staged_file_under_home_is_given_as_a_tilde_path(tmp_path, monkeypatch):
    from career_evidence_graph.application_computer_use import stage_files

    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "r.pdf").write_bytes(b"cv")
    staged = stage_files(
        {"resume_path": str(tmp_path / "r.pdf"), "confirmed_answers": []}, tmp_path / "Apply"
    )
    assert staged["resume_path"] == "~/Apply/CV.pdf"


def test_the_job_page_opens_in_chrome():
    from types import SimpleNamespace

    from career_evidence_graph.application_computer_use import open_job_page

    calls = []
    assert open_job_page(
        "https://jobs.example.invalid/1",
        run=lambda argv, **_: calls.append(argv) or SimpleNamespace(returncode=0),
    )
    assert calls == [["open", "-a", "Google Chrome", "https://jobs.example.invalid/1"]]


def test_a_fill_runs_at_the_requested_reasoning_effort(tmp_path):
    seen = []

    def popen(argv, **options):
        process = Process(argv, report=REPORT, **options)
        seen.append(process)
        return process

    context = {"job_url": "https://jobs.example.invalid/1", "resume_path": "/r.pdf"}
    report = run_fill("/bin/codex", context, tmp_path, popen=popen, reasoning_effort="medium")
    (process,) = seen
    assert 'model_reasoning_effort="medium"' in process.argv
    settings = json.loads((Path(report["run"]) / "settings.json").read_text())
    assert settings == {"reasoning_effort": "medium"}


def test_the_effort_trial_alternates_and_then_ends(tmp_path):
    """2026-11-09: the user asked to alternate medium and high over ten fills."""
    from career_evidence_graph.application_computer_use import next_trial_effort

    assert next_trial_effort(tmp_path) is None
    (tmp_path / "effort-trial.json").write_text(json.dumps({"remaining": 3, "next": "medium"}))
    assert [next_trial_effort(tmp_path) for _ in range(4)] == ["medium", "high", "medium", None]


# A fake sky replays accessibility-tree diffs as the real one returned them on
# 2026-11-09 (file chooser IDs open-panel, PathTextField, OKButton).
FAKE_SKY = r"""
const calls = [];
const pages = {
  start: 'Window "Apply"\n0 standard window Apply\n10 pop up button Language\n'
    + '11 button Upload CV\n50 text We work in English and German.',
  menu: 'The following is a diff from the previous accessibility tree for Window: "Apply"\n'
    + '+\t80 menu item German\n+\t81 menu item English',
  chosen: 'The following is a diff from the previous accessibility tree for Window: "Apply"\n'
    + 'Removed element IDs: 80-81\n~\t10 pop up button Language, Value: English',
  panel: 'The following is a diff from the previous accessibility tree for Window: "Open"\n'
    + '+170 sheet Description: open, ID: open-panel\n+\t238 button Open, ID: OKButton',
  goto: 'The following is a diff from the previous accessibility tree for Window: ""\n'
    + '+\t172 text field (settable) Value: , ID: PathTextField',
  closed: 'The following is a diff from the previous accessibility tree for Window: "Apply"\n'
    + 'Removed element IDs: 170-238\n~\t11 button Upload CV, Value: CV.pdf',
};
let page = 'start';
const sky = {
  get_app_state: async () => ({ text: pages[page] }),
  click: async ({ element_index }) => {
    calls.push('click ' + element_index);
    page = { 10: 'menu', 81: 'chosen', 11: 'panel', 238: 'closed' }[element_index] || page;
  },
  press_key: async ({ key }) => {
    calls.push('key ' + key);
    if (key === 'super+shift+g') page = 'goto';
  },
  set_value: async ({ element_index, value }) => {
    calls.push('set ' + element_index + ' ' + value);
  },
};
"""


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_the_helpers_pick_new_options_and_attach_through_the_chooser(tmp_path):
    from career_evidence_graph.application_computer_use import HELPERS

    body = HELPERS.replace("var { sky } = await import('@oai/sky');", FAKE_SKY)
    body = body.replace(
        "var pause = (ms) => new Promise((done) => setTimeout(done, ms));",
        "var pause = async () => {};",
    )
    script = tmp_path / "helpers.mjs"
    script.write_text(
        "const out = []; const nodeRepl = { homeDir: '/Users/u', write: (v) => out.push(v) };\n"
        + body
        + "\nout.push(await pick(10, 'English'));"
        + "\nout.push('TREE ' + tree.get(10) + ' | ' + tree.has(80));"
        + "\nout.push(await upload(11, '~/Apply/CV.pdf'));"
        + "\nconsole.log(JSON.stringify({ out, calls }));\n"
    )
    result = json.loads(
        subprocess.run(["node", script], capture_output=True, text=True, check=True).stdout
    )
    out, calls = result["out"], result["calls"]
    assert "10 pop up button Language" in out[0]
    # The option that appeared after the click, not the page text naming English.
    assert out[1].startswith("Clicked 81 menu item English")
    assert out[2] == "TREE pop up button Language, Value: English | false"
    assert out[3].startswith("Attached CV.pdf")
    assert calls == [
        "click 10",
        "click 81",
        "click 11",
        "key super+shift+g",
        "set 172 /Users/u/Apply/CV.pdf",
        "key Return",
        "click 238",
    ]
