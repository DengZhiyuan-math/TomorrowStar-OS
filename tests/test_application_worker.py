"""Worker contracts with explicitly selected, synthetic temporary stores."""

from __future__ import annotations

import base64
import json
import multiprocessing
from pathlib import Path
from types import SimpleNamespace

import pytest

from career_evidence_graph.application_worker import (
    WorkerService,
    WorkerStore,
    digest,
    fact_for,
)
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


def _append_answer(apps: str, root: str, index: int) -> None:
    store = WorkerStore(ApplicationStore(Path(apps)), Path(root))
    with store.applications.write_lock():
        store.answers.put_answer(
            {
                "question": f"Synthetic question {index}",
                "value": str(index),
                "scope": {},
                "state": "confirmed",
                "source": "synthetic",
            }
        )


@pytest.fixture
def service(tmp_path: Path, monkeypatch) -> WorkerService:
    apps = tmp_path / "applications"
    apps.mkdir()
    service = WorkerService(
        ApplicationStore(apps), tmp_path / "worker", fixture_origin="http://127.0.0.1:9999"
    )
    monkeypatch.setattr(service, "spawn", lambda: None)
    return service


def job(service: WorkerService, index: int = 1, country: str = "CHE") -> dict:
    app = service.store.applications.create_application(
        {
            "company": f"Synthetic {index}",
            "role_title": "Engineer",
            "status": "drafting",
            "url": f"https://jobs.lever.co/synthetic-{index}/00000000-0000-0000-0000-{index:012d}",
        }
    )
    return {
        "application_id": app["id"],
        "revision": app["revision"],
        "country": country,
        "filename": f"resume-{index}.pdf",
        "file_base64": base64.b64encode(f"%PDF-1.4 synthetic {index}".encode()).decode(),
    }


def test_prepare_binds_each_file_and_preserves_original_status(service: WorkerService) -> None:
    items = [job(service, 1), job(service, 2)]
    state = service.request("prepare", {"jobs": items})
    assert state["control"] == "paused"
    assert len({j["file_sha256"] for j in state["jobs"]}) == 2
    assert all("file_path" not in j for j in state["jobs"])
    assert all(a["status"] == "drafting" for a in service.store.applications.list_applications())
    persisted = service.store.load()
    assert all(Path(j["file_path"]).is_file() for j in persisted["jobs"])


@pytest.mark.parametrize(
    "change,code",
    [
        ({"filename": "../private.pdf"}, "resume_required"),
        ({"file_base64": "broken"}, "invalid_resume"),
        ({"country": ""}, "country_required"),
        ({"revision": "stale"}, "conflict"),
    ],
)
def test_invalid_inputs_stop_before_batch_creation(service, change, code) -> None:
    item = {**job(service), **change}
    with pytest.raises(PortalDataError) as exc:
        service.request("prepare", {"jobs": [item]})
    assert exc.value.code == code
    assert service.store.load()["jobs"] == []


def test_duplicate_targets_are_rejected(service: WorkerService) -> None:
    item = job(service)
    with pytest.raises(PortalDataError, match="同一岗位"):
        service.request("prepare", {"jobs": [item, item]})


def test_new_history_before_resume_pauses_only_affected_job(service):
    first, second = job(service, 1), job(service, 2)
    service.request("prepare", {"jobs": [first, second]})
    app = service.store.applications.get_application(first["application_id"])
    prior = service.store.applications.create_application(
        {"company": app["company"], "role_title": app["role_title"], "status": "applied"}
    )
    result = service.request("resume", {"controller": "synthetic-controller"})
    assert result["jobs"][0]["status"] == "needs_recheck"
    assert result["jobs"][0]["reason"] == "duplicate_application"
    assert result["jobs"][1]["status"] == "queued"
    assert service.store.applications.get_application(prior["id"])["status"] == "applied"


def test_actual_scope_is_checked_even_if_helper_key_is_misleading(service) -> None:
    item = job(service)
    service.request("prepare", {"jobs": [item]})
    current = service.store.load()["jobs"][0]
    question = {
        "question": "Do you require visa sponsorship now or in the future?",
        "options": ["Yes", "No"],
    }
    service.store.answers.put_answer(
        {
            "key": "arbitrary",
            "question": question["question"],
            "scope": {"country": "USA"},
            "value": "Yes",
            "state": "confirmed",
        }
    )
    assert service.store.resolve(question, current) is None
    service.store.answers.put_answer(
        {
            "question": "Will you now or in the future require visa sponsorship?",
            "scope": {"country": "CHE"},
            "value": "No",
            "state": "confirmed",
        }
    )
    assert service.store.resolve(question, current)[0] == "No"


def test_standing_data_consent_ticks_a_lone_box_or_the_affirmative_choice(service) -> None:
    service.request("prepare", {"jobs": [job(service)]})
    current = service.store.load()["jobs"][0]
    service.store.answers.put_answer(
        {"question": "Data processing consent", "value": "Yes", "state": "confirmed"}
    )
    label = "I hereby agree that my data will be stored for future vacancies"
    box = {"question": label, "type": "checkbox", "options": [label]}
    choice = {"question": label, "type": "radio", "options": ["Nein", "Ja"]}
    assert service.store.resolve(box, current)[0] == label
    assert service.store.resolve(choice, current)[0] == "Ja"
    check = {"question": "I consent to a background check", "type": "checkbox", "options": ["x"]}
    assert service.store.resolve(check, current) is None


def test_fact_aliases_keep_time_and_authorization_distinct() -> None:
    assert fact_for("Will you now or in the future require visa sponsorship?") == fact_for(
        "Do you require visa sponsorship now or in the future?"
    )
    assert fact_for("Do you require visa sponsorship now?") != fact_for(
        "Will you now or in the future require visa sponsorship?"
    )
    assert fact_for("Are you currently authorized to work in this country?") != fact_for(
        "Will you now or in the future require visa sponsorship?"
    )


def test_confirmed_profile_links_reuse_explicit_equivalent_labels(service):
    service.request("prepare", {"jobs": [job(service)]})
    current = service.store.load()["jobs"][0]
    for question, label, value in (
        ("GitHub URL", "Link to your Github profile", "https://github.com/synthetic"),
        ("LinkedIn URL", "Link to your LinkedIn profile", "https://www.linkedin.com/in/synthetic"),
    ):
        service.store.answers.put_answer(
            {"question": question, "value": value, "scope": {}, "state": "confirmed"}
        )
        result = service.store.resolve({"question": label, "options": []}, current)
        assert result is not None
        assert result[0] == value
    assert service.store.resolve({"question": "Portfolio or personal website"}, current) is None


def test_language_library_requires_confirmed_global_unambiguous_cefr(service):
    for question, value, scope, state in (
        ("French proficiency (CEFR)", "B1", {}, "confirmed"),
        ("French level", "C1", {"country": "FRA"}, "confirmed"),
        ("German proficiency (CEFR)", "B2", {}, "inferred"),
    ):
        service.store.answers.put_answer(
            {"question": question, "value": value, "scope": scope, "state": state}
        )
    assert service.store.language_levels() == {"French": "B1"}
    current = {"country": "CHE", "company": "Synthetic", "application_id": "synthetic"}
    assert (
        service.store.resolve({"question": "French proficiency", "options": ["B1", "B2"]}, current)[
            0
        ]
        == "B1"
    )
    assert (
        service.store.resolve(
            {"question": "Do you speak French fluently?", "options": ["Yes", "No"]}, current
        )
        is None
    )
    service.store.answers.put_answer(
        {"question": "French language level", "value": "B2", "scope": {}, "state": "confirmed"}
    )
    assert service.store.language_levels() == {}
    assert service.store.resolve({"question": "French proficiency", "options": []}, current) is None


def test_live_language_mismatch_blocks_batch_before_attachment_write(tmp_path, monkeypatch):
    apps = tmp_path / "applications"
    apps.mkdir()
    live = WorkerService(ApplicationStore(apps), tmp_path / "worker", live=True)
    monkeypatch.setattr(live, "spawn", lambda: pytest.fail("must not spawn"))
    item = job(live)
    app = live.store.applications.update_application(
        item["application_id"],
        {"job_description": "Minimum German level B2 required."},
        item["revision"],
    )
    item["revision"] = app["revision"]
    live.store.answers.put_answer(
        {"question": "German proficiency (CEFR)", "value": "A1", "scope": {}, "state": "confirmed"}
    )
    with pytest.raises(PortalDataError) as error:
        live.request("prepare", {"jobs": [item]})
    assert error.value.code == "job_requirement_mismatch"
    assert live.store.load()["jobs"] == []
    assert not list(live.store.root.rglob("*.pdf"))
    assert live.store.applications.get_application(app["id"])["status"] == "drafting"


def test_conflicting_answers_and_opposite_options_do_not_reuse(service) -> None:
    service.request("prepare", {"jobs": [job(service)]})
    current = service.store.load()["jobs"][0]
    for question, value in (("Full name", "Person A"), ("Your full name", "Person B")):
        service.store.answers.put_answer(
            {"question": question, "scope": {}, "value": value, "state": "confirmed"}
        )
    assert service.store.resolve({"question": "Name", "options": []}, current) is None
    service.store.answers.put_answer(
        {
            "question": "Will you now or in the future require visa sponsorship?",
            "scope": {"country": "CHE"},
            "value": "No",
            "state": "confirmed",
        }
    )
    assert (
        service.store.resolve(
            {
                "question": "Will you now or in the future require visa sponsorship?",
                "options": ["I need sponsorship", "I do not need sponsorship"],
            },
            current,
        )
        is None
    )


def test_confirmed_sensitive_value_reuses_only_in_its_scope(service) -> None:
    service.request("prepare", {"jobs": [job(service)]})
    current = service.store.load()["jobs"][0]
    question = {"question": "Expected salary", "options": []}
    service.store.answers.put_answer(
        {
            "question": question["question"],
            "scope": {"application_id": current["application_id"]},
            "value": "100000",
            "state": "confirmed",
            "sensitivity": "high",
        },
        remember_sensitive=True,
    )
    assert service.store.resolve(question, current)[0] == "100000"
    other = {**current, "application_id": "different"}
    assert service.store.resolve(question, other) is None


def test_pause_and_controller_takeover_do_not_resume_implicitly(service) -> None:
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "controller-a"})
    service.request("pause", {"controller": "controller-a"})
    assert service.snapshot()["control"] == "paused"
    service.request("resume", {"controller": "controller-b"})
    with pytest.raises(PortalDataError, match="另一窗口"):
        service.request("heartbeat", {"controller": "controller-a"})


def test_single_application_answer_is_saved_with_its_scope(service) -> None:
    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    current = state["jobs"][0]
    current["status"] = "needs_input"
    current["questions"] = [{"id": "q", "question": "Start date", "options": []}]
    service.store.save(state)
    service.request(
        "answer",
        {
            "application_id": current["application_id"],
            "question_id": "q",
            "value": "2026-11-01",
            "only_this": True,
        },
    )
    assert service.store.library()[0]["scope"] == {"application_id": current["application_id"]}
    assert service.store.library()[0]["value"] == "2026-11-01"
    assert service.store.load()["commands"][-1]["action"] == "answers-changed"
    assert service.store.load()["control"] == "paused"


@pytest.mark.parametrize(
    "question,sensitivity,expected",
    [
        ("Full name", "none", {}),
        ("Full name", "high", "application"),
        ("Synthetic policy acknowledgement", "none", "application"),
        ("Expected salary", "high", "application"),
        ("Will you now or in the future require visa sponsorship?", "none", {"country": "CHE"}),
    ],
)
def test_answer_auto_saves_without_broadening_semantic_scope(
    service, question, sensitivity, expected
):
    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    current = state["jobs"][0]
    current.update(
        status="needs_input",
        questions=[{"id": "q", "question": question, "options": [], "sensitivity": sensitivity}],
    )
    service.store.save(state)
    expected_scope = (
        {"application_id": current["application_id"]} if expected == "application" else expected
    )
    assert service.snapshot()["input_items"][0]["scope"] == expected_scope
    service.request(
        "answer",
        {
            "application_id": current["application_id"],
            "question_id": "q",
            "value": "Synthetic value",
        },
    )
    record = service.store.library()[0]
    assert record["scope"] == expected_scope
    assert record["source"] == "user" and record["state"] == "confirmed"
    assert service.store.load()["control"] == "paused"
    assert not service.store.load()["jobs"][0]["observations"]


def test_answer_saved_while_paused_marks_matching_jobs_ready_without_actions(service) -> None:
    service.request("prepare", {"jobs": [job(service, 1), job(service, 2), job(service, 3, "USA")]})
    state = service.store.load()
    for current in state["jobs"]:
        current["status"] = "needs_input"
        current["questions"] = [
            {
                "id": "sponsor",
                "question": "Will you now or in the future require visa sponsorship?",
                "options": ["Yes", "No"],
            }
        ]
    service.store.save(state)
    service.request(
        "answer",
        {
            "application_id": state["jobs"][0]["application_id"],
            "question_id": "sponsor",
            "value": "Yes",
            "scope": {"country": "CHE"},
        },
    )
    updated = service.store.load()
    assert [j["status"] for j in updated["jobs"]] == ["queued", "queued", "needs_input"]
    assert updated["control"] == "paused"
    assert all(j["observations"] == [] for j in updated["jobs"])


def test_action_resolution_draft_survives_other_job_progress(service):
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the offline resolution form regression")
    service.request("prepare", {"jobs": [job(service, 1), job(service, 2)]})
    state = service.store.load()
    for index, current in enumerate(state["jobs"]):
        current.update(
            status="needs_recheck",
            intent={"action": "upload", "attempt_id": f"synthetic-attempt-{index}"},
        )
    service.store.save(state)
    script = r"""
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
let state = JSON.parse(fs.readFileSync(0, "utf8"));
class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.dataset = {}; this.attrs = {};
    this.listeners = {}; this.value = "";
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  setAttribute(key, value) { this.attrs[key] = value; }
  contains() { return false; }
}
const roots = new Map(), events = new Map(); const submissions = []; let fail = true;
const context = {
  document: {getElementById(id) {
    if (!roots.has(id)) roots.set(id, new Element("div")); return roots.get(id);
  },
    createElement: tag => new Element(tag), addEventListener() {}, activeElement: null},
  window: {addEventListener(type, callback) { events.set(type, callback); }},
  location: {hash: "#applications"},
  crypto: {randomUUID: () => "synthetic-controller"}, setInterval() {},
  stateReady: true, data: {applications: []}, renderApplications() {}, loadState() {}, toast() {},
  api: async (path, options) => {
    if (path.endsWith("/resolve-action")) {
      submissions.push(JSON.parse(options.body));
      if (fail) throw new Error("synthetic save failure");
      state.jobs[0].action_resolutions = [{intent_ref: state.jobs[0].intent_ref,
        conclusion: "current_matches", source: "Synthetic source A"}];
    }
    return structuredClone(state);
  },
};
vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), context);
function descendants(element) { return [element, ...element.children.flatMap(descendants)]; }
function formFor(index) {
  const card = descendants(roots.get("worker-root"))
    .find(e => e.dataset.jobId === state.jobs[index].application_id);
  const form = descendants(card).find(e => e.tag === "form");
  return {form, conclusion: descendants(form).find(e => e.tag === "select"),
    source: descendants(form).find(e => e.tag === "input")};
}
function enter(index, conclusion, source) {
  const fields = formFor(index); fields.conclusion.value = conclusion; fields.source.value = source;
  fields.form.listeners.change?.(); fields.form.listeners.input?.();
}
const tick = () => new Promise(setImmediate);
(async () => {
  await tick();
  enter(0, "current_matches", "Synthetic source A"); enter(1, "not_applied", "Synthetic source B");
  state.jobs[1].reason = "page_closed";
  await events.get("focus")(); await tick();
  assert.equal(formFor(0).conclusion.value, "current_matches", "preserve the conclusion");
  assert.equal(formFor(0).source.value, "Synthetic source A", "preserve the source");
  assert.equal(formFor(1).conclusion.value, "not_applied");
  assert.equal(formFor(1).source.value, "Synthetic source B");
  await formFor(0).form.listeners.submit({preventDefault() {}});
  state.jobs[1].reason = "page_lost";
  await events.get("focus")(); await tick();
  assert.equal(formFor(0).source.value, "Synthetic source A", "failed saves must retain the draft");
  fail = false;
  await formFor(0).form.listeners.submit({preventDefault() {}});
  assert.equal(submissions.at(-1).application_id, state.jobs[0].application_id);
  assert.equal(submissions.at(-1).intent_ref, state.jobs[0].intent_ref);
  assert.equal(submissions.at(-1).conclusion, "current_matches");
  assert.equal(submissions.at(-1).source, "Synthetic source A");
  assert.equal(formFor(0).conclusion.value, "", "successful saves clear only the saved draft");
  assert.equal(formFor(0).source.value, "");
  assert.equal(formFor(1).source.value, "Synthetic source B");
  const original = state.jobs[1].intent_ref;
  state.jobs[1].intent_ref = "synthetic-next-attempt";
  state.jobs[1].intent.attempt_id = "synthetic-next-attempt";
  await events.get("focus")(); await tick();
  assert.equal(formFor(1).conclusion.value, "", "a new attempt cannot reuse an old conclusion");
  assert.equal(formFor(1).source.value, "");
  state.jobs[1].intent_ref = original; state.jobs[1].intent.attempt_id = original;
  await events.get("focus")(); await tick();
  assert.equal(formFor(1).source.value, "", "discarded attempts must not restore stale drafts");
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [
            node,
            "-e",
            script,
            str(Path(__file__).parents[1] / "src/career_evidence_graph/portal_static/worker.js"),
        ],
        input=json.dumps(service.snapshot()),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("selection", ["default", "job", "company"])
@pytest.mark.parametrize("country", [None, "CHE", "OTHER"])
def test_answer_form_scope_selection_is_applied_to_all_waiting_jobs(service, selection, country):
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the offline answer form regression")
    country_scoped = country is not None
    items = [
        job(service, i, "USA" if country_scoped and i == 3 else country or "CHE") for i in (1, 2, 3)
    ]
    for index, item in enumerate(items):
        app = service.store.applications.get_application(item["application_id"])
        updated = service.store.applications.update_application(
            app["id"],
            {"company": "Shared Synthetic" if index < 2 or country_scoped else "Other Synthetic"},
            app["revision"],
        )
        item["revision"] = updated["revision"]
    service.request("prepare", {"jobs": items})
    state = service.store.load()
    for current in state["jobs"]:
        current.update(
            status="needs_input",
            questions=[
                {
                    "id": "q",
                    "question": "Will you now or in the future require visa sponsorship?"
                    if country_scoped
                    else "Which reporting tool do you use?",
                    "options": ["Yes", "No"] if country_scoped else [],
                }
            ],
        )
    service.store.save(state)
    ui = {**service.snapshot(), "jobs": [], "library": []}
    script = r"""
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const fixture = JSON.parse(fs.readFileSync(0, "utf8"));
class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.dataset = {}; this.attrs = {}; this.listeners = {};
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  setAttribute(key, value) { this.attrs[key] = value; }
  contains() { return false; }
}
const roots = new Map(); let submitted;
const context = {
  document: {getElementById(id) {
    if (!roots.has(id)) roots.set(id, new Element("div")); return roots.get(id);
  },
    createElement: tag => new Element(tag), addEventListener() {}, activeElement: null},
  window: {addEventListener() {}}, location: {hash: "#applications"},
  crypto: {randomUUID: () => "synthetic-controller"},
  setInterval() {}, stateReady: true, data: {applications: []},
  renderApplications() {}, loadState() {}, toast() {},
  api: async (path, options) => {
    if (path.endsWith("/answer")) submitted = JSON.parse(options.body); return fixture.state;
  },
};
vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), context);
function descendants(element) { return [element, ...element.children.flatMap(descendants)]; }
(async () => {
  await new Promise(setImmediate);
  const form = descendants(roots.get("worker-root"))
    .find(e => e.tag === "form" && e.dataset.inputId);
  assert.ok(form, "the actual worker input form must render");
  const fields = descendants(form);
  fields.find(e => e.attrs["aria-label"] === "已确认答案").value = "Yes";
  const selects = fields.filter(e => e.tag === "select");
  const scope = selects.find(e => e.children.some(c => c.value === "company"));
  scope.value = fixture.selection;
  const target = selects.find(e => e !== scope && e.attrs["aria-label"] !== "已确认答案");
  target.value = fixture.state.input_items[0].jobs[0].id;
  await form.listeners.submit({preventDefault() {}});
  assert.ok(submitted, "the submit handler must send the answer");
  process.stdout.write(JSON.stringify(submitted));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [
            node,
            "-e",
            script,
            str(Path(__file__).parents[1] / "src/career_evidence_graph/portal_static/worker.js"),
        ],
        input=json.dumps({"state": ui, "selection": selection}),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    service.request("answer", payload)
    saved = service.store.load()
    assert [current["status"] for current in saved["jobs"]] == [
        "queued",
        "queued"
        if country_scoped
        and country != "OTHER"
        and (selection == "company" or selection == "default" and country_scoped)
        else "needs_input",
        "needs_input",
    ]
    assert saved["control"] == "paused"
    assert all(current["observations"] == [] for current in saved["jobs"])
    if selection == "company":
        expected_scope = {"company": "Shared Synthetic"}
        if country_scoped:
            expected_scope["country"] = country
        if country == "OTHER":
            expected_scope["application_id"] = items[0]["application_id"]
        assert payload["scope"] == expected_scope


def test_answer_edit_and_withdraw_bind_fresh_revisions(service) -> None:
    record = service.store.answers.put_answer(
        {"question": "Full name", "scope": {}, "value": "Old", "state": "confirmed"}
    )
    old_revision = digest(record)
    service.request("library", {"key": record["key"], "revision": old_revision, "value": "New"})
    changed = service.store.answers.get_answer(record["key"])
    assert digest(changed) != old_revision
    with pytest.raises(PortalDataError, match="答案已变更"):
        service.request(
            "library", {"key": record["key"], "revision": old_revision, "value": "Stale"}
        )
    service.request(
        "library", {"key": record["key"], "revision": digest(changed), "withdraw": True}
    )
    assert service.store.answers.get_answer(record["key"])["value"] is None


def test_process_writers_preserve_every_answer(service) -> None:
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(
            target=_append_answer,
            args=(str(service.store.applications.root), str(service.store.root), i),
        )
        for i in range(12)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(15)
        assert process.exitcode == 0
    assert len(service.store.library()) == 12
    assert json.loads(service.store.answers.profile_path.read_text())["profile"] == {}


def test_human_submission_and_receipt_are_separate_sources(service) -> None:
    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    current = state["jobs"][0]
    current.update(status="ready_for_review", handed_off=True)
    service.store.save(state)
    identifier = current["application_id"]
    service.request("submitted", {"application_id": identifier, "acknowledge": True})
    assert service.store.applications.get_application(identifier)["status"] == "applied"
    assert service.store.load()["jobs"][0]["receipt"] is None
    with pytest.raises(PortalDataError, match="已确认人工提交"):
        service.request("recheck", {"application_id": identifier, "acknowledge": True})
    service.request(
        "receipt", {"application_id": identifier, "locator": "Synthetic confirmation page"}
    )
    assert (
        service.store.applications.get_application(identifier)["status"] == "confirmation_received"
    )
    service.request("submitted", {"application_id": identifier, "acknowledge": True})
    assert (
        service.store.applications.get_application(identifier)["status"] == "confirmation_received"
    )


def test_pending_sync_requires_review_of_new_revision_and_preserves_notes(service) -> None:
    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    current = state["jobs"][0]
    changed = service.store.applications.update_application(
        current["application_id"], {"notes": "Keep this external edit"}, current["revision"]
    )
    service.store.sync(current, "Synthetic review action")
    service.store.save(state)
    assert current["sync_error"] == "revision-conflict"
    with pytest.raises(PortalDataError, match="请先核验"):
        service.request(
            "retry-sync",
            {"application_id": current["application_id"], "revision": changed["revision"]},
        )
    service.request(
        "retry-sync",
        {
            "application_id": current["application_id"],
            "revision": changed["revision"],
            "acknowledge": True,
        },
    )
    app = service.store.applications.get_application(current["application_id"])
    assert app["notes"] == "Keep this external edit"
    assert app["next_action"] == "Synthetic review action"


@pytest.mark.parametrize("platform", ["lever", "greenhouse"])
def test_final_request_guard_allows_only_the_selected_fixture_upload(service, platform) -> None:
    from career_evidence_graph.lever_worker import LeverRunner

    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    current = service.store.load()["jobs"][0]
    identifier = current["application_id"]
    runner = LeverRunner(service.store, None, "http://127.0.0.1:9999")

    assert runner.authorize(
        current,
        service.store.load()["batch_id"],
        {"action": "upload", "sha256": current["file_sha256"]},
    )

    class Route:
        def __init__(self, method, url):
            self.request = type("Request", (), {"method": method, "url": url})()
            self.outcome = ""

        def fetch(self, **kwargs):
            assert kwargs == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
            return SimpleNamespace(status=200, dispose=lambda: None)

        def fulfill(self, *, response):
            assert response.status == 200
            self.outcome = "allowed"

        def abort(self, reason):
            self.outcome = "blocked"

    from career_evidence_graph.ats_forms import FORMS

    own_upload = FORMS[platform].upload_path(identifier)
    other_upload = FORMS[platform].upload_path("other-job")
    final_path = FORMS[platform].submit_path(identifier)
    wrong_platform = FORMS["lever" if platform == "greenhouse" else "greenhouse"].upload_path(
        identifier
    )
    for method, path, expected in (
        ("POST", "http://127.0.0.1:9999/submit/job", "blocked"),
        ("POST", "http://127.0.0.1:9999" + final_path, "blocked"),
        ("POST", "http://127.0.0.1:9999" + other_upload, "blocked"),
        ("POST", "http://127.0.0.1:9999" + wrong_platform, "blocked"),
        ("GET", "http://127.0.0.1:8765/api/state", "blocked"),
        ("POST", "http://127.0.0.1:9999" + own_upload, "allowed"),
    ):
        route = Route(method, path)
        runner._guard(identifier, platform)(route)
        assert route.outcome == expected


def test_saved_qualification_in_other_country_stays_bound_to_one_job(service) -> None:
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    service.request("prepare", {"jobs": [job(service, country="OTHER")]})
    state = service.store.load()
    current = state["jobs"][0]
    question = {
        "id": "sponsorship",
        "question": "Will you now or in the future require visa sponsorship?",
        "options": ["Yes", "No"],
        "required": True,
    }
    current.update(status="needs_input", questions=[question])
    service.store.save(state)
    service.request(
        "answer",
        {
            "application_id": current["application_id"],
            "question_id": "sponsorship",
            "value": "No",
            "only_this": True,
        },
    )
    runner = ApplicationRunner(service.store, None, "http://127.0.0.1:9999")
    runner.commands(service.store.load())
    assert service.store.resolve(question, current, runner.temporary)[0] == "No"
    assert (
        service.store.resolve(question, {**current, "application_id": "another"}, runner.temporary)
        is None
    )
    assert service.store.library()[0]["scope"] == {
        "country": "OTHER",
        "application_id": current["application_id"],
    }


def test_upload_result_save_failure_stops_without_resending(service, monkeypatch) -> None:
    from copy import deepcopy

    from career_evidence_graph.lever_worker import LeverRunner

    service.request("prepare", {"jobs": [job(service)]})
    for question, value, scope in (
        ("Full name", "Synthetic", {}),
        ("Email address", "synthetic@example.invalid", {}),
        ("Will you now or in the future require visa sponsorship?", "No", {"country": "CHE"}),
    ):
        service.store.answers.put_answer(
            {"question": question, "scope": scope, "value": value, "state": "confirmed"}
        )
    state = service.store.load()
    current = state["jobs"][0]
    service.request("resume", {"controller": "synthetic-controller"})
    fields = []
    for identifier, kind, question, value in (
        ("name", "text", "Full name", "Synthetic"),
        ("email", "email", "Email address", "synthetic@example.invalid"),
        ("sponsorship", "select", "Will you now or in the future require visa sponsorship?", "No"),
        ("resume", "file", "Resume", ""),
    ):
        fields.append(
            {
                "id": identifier,
                "type": kind,
                "question": question,
                "value": value,
                "options": ["Yes", "No"] if kind == "select" else [],
                "required": True,
                "valid": True,
            }
        )

    class Page:
        url = "http://127.0.0.1:9999/lever/" + current["application_id"]
        upload = {"state": "empty"}
        sends = 0

        def is_closed(self):
            return False

        def evaluate(self, expression):
            return {
                "identity": {
                    "company": current["company"],
                    "role": current["role_title"],
                    "jobUrl": current["job_url"],
                },
                "fields": deepcopy(fields),
                "upload": self.upload.copy(),
            }

        def locator(self, selector):
            return self

        def set_input_files(self, selected, timeout):
            assert selected["buffer"] == Path(current["file_path"]).read_bytes()
            self.sends += 1
            self.upload = {
                "state": "complete",
                "name": current["filename"],
                "sha256": current["file_sha256"],
            }

        def wait_for(self, timeout):
            pass

    page = Page()
    runner = LeverRunner(service.store, None, "http://127.0.0.1:9999")
    runner.pages[current["application_id"]] = page
    save = service.store.save
    failed = False

    def fail_after_upload(snapshot):
        nonlocal failed
        intent = service.store.load()["jobs"][0]["intent"]
        if (
            not failed
            and intent
            and intent["action"] == "upload"
            and snapshot["jobs"][0]["intent"] is None
        ):
            failed = True
            raise OSError("Synthetic failure after remote upload, before local result save")
        save(snapshot)

    monkeypatch.setattr(service.store, "save", fail_after_upload)
    runner.tick()
    stopped = service.store.load()["jobs"][0]
    assert stopped["status"] == "needs_recheck"
    assert stopped["intent"]["action"] == "upload"
    runner.tick()
    assert page.sends == 1


def test_codex_claim_blocks_automated_prepare(service):
    from career_evidence_graph.application_execution import reserve_execution

    item = job(service)
    reserve_execution(service.store.applications, item["application_id"], "codex-task", "codex")
    with pytest.raises(PortalDataError) as raised:
        service.request("prepare", {"jobs": [item]})
    assert raised.value.code == "execution_conflict"
    assert service.snapshot()["jobs"] == []


def test_worker_rejects_handoff_root_before_creating_answers(tmp_path):
    apps = tmp_path / "apps"
    apps.mkdir()
    root = tmp_path / "handoff"
    root.mkdir()
    (root / "handoff.json").write_text("{}")
    with pytest.raises(ValueError, match="separate"):
        WorkerStore(ApplicationStore(apps), root)
    assert not (root / "answer-library").exists()


def test_cancel_keeps_ownership_until_page_and_intent_settled(service):
    from career_evidence_graph.application_execution import (
        automated_owner,
        require_execution,
    )

    item = job(service)
    state = service.request("prepare", {"jobs": [item]})
    with service.store.applications.write_lock():
        raw = service.store.load()
        raw["jobs"][0].update(page_open=True, intent={"action": "upload"})
        service.store.save(raw)
    service.request("cancel-job", {"application_id": item["application_id"]})
    require_execution(
        service.store.applications,
        item["application_id"],
        automated_owner(service.store.root, state["batch_id"], item["application_id"]),
        "automated",
    )


def test_prepare_save_failure_can_retry_without_orphaned_ownership(service, monkeypatch):
    item = job(service)
    original_save = service.store.save
    monkeypatch.setattr(
        service.store, "save", lambda state: (_ for _ in ()).throw(OSError("disk full"))
    )
    with pytest.raises(OSError, match="disk full"):
        service.request("prepare", {"jobs": [item]})
    assert service.store.load()["jobs"] == []
    monkeypatch.setattr(service.store, "save", original_save)
    state = service.request("prepare", {"jobs": [item]})
    assert state["jobs"][0]["application_id"] == item["application_id"]
    assert not (service.store.root / "prepare-pending.json").exists()


def test_prepare_process_interruption_is_recoverable_on_explicit_prepare(service, monkeypatch):
    import career_evidence_graph.application_worker as worker

    item = job(service)
    original_reserve = worker.reserve_execution

    def interrupted(*args):
        original_reserve(*args)
        raise SystemExit("simulated process interruption after reservation")

    monkeypatch.setattr(worker, "reserve_execution", interrupted)
    with pytest.raises(SystemExit):
        service.request("prepare", {"jobs": [item]})
    assert service.store.load()["jobs"] == []
    monkeypatch.setattr(worker, "reserve_execution", original_reserve)
    state = service.request("prepare", {"jobs": [item]})
    assert len(state["jobs"]) == 1
    assert list((service.store.root / "prepare-history").glob("*.json"))


def test_prepare_interruption_after_publication_keeps_owner(service, monkeypatch):
    from career_evidence_graph.application_execution import automated_owner, require_execution

    item = job(service)
    original_settle = service._settle_pending_prepare

    def interrupted(state):
        if (service.store.root / "prepare-pending.json").exists():
            raise SystemExit("simulated interruption after publication")
        original_settle(state)

    monkeypatch.setattr(service, "_settle_pending_prepare", interrupted)
    with pytest.raises(SystemExit):
        service.request("prepare", {"jobs": [item]})
    published = service.store.load()
    assert len(published["jobs"]) == 1
    monkeypatch.setattr(service, "_settle_pending_prepare", original_settle)
    with pytest.raises(PortalDataError) as raised:
        service.request("prepare", {"jobs": [item]})
    assert raised.value.code == "batch_exists"
    require_execution(
        service.store.applications,
        item["application_id"],
        automated_owner(service.store.root, published["batch_id"], item["application_id"]),
        "automated",
    )
    assert not (service.store.root / "prepare-pending.json").exists()


def test_saved_job_exception_reuses_one_answer_without_overwriting_global_fact(service):
    item = job(service)
    service.request("prepare", {"jobs": [item]})
    current = service.store.load()["jobs"][0]
    for scope, value in [
        ({}, "global@example.test"),
        ({"application_id": current["application_id"]}, "job@example.test"),
    ]:
        service.store.answers.put_answer(
            {"question": "Email address", "scope": scope, "value": value, "state": "confirmed"}
        )
    question = {"question": "Your email address", "options": []}
    assert service.store.resolve(question, current)[0] == "job@example.test"
    assert (
        service.store.resolve(question, current | {"application_id": "different-job"})[0]
        == "global@example.test"
    )
    reopened = WorkerStore(service.store.applications, service.store.root)
    assert reopened.resolve(question, current)[0] == "job@example.test"


def test_a_restart_rechecks_only_jobs_whose_page_an_earlier_run_opened(service) -> None:
    # 2026-11-04: with a skipped job beside it, a restart demoted the next queued job
    # (worker_restarted) before its first page ever opened.
    from career_evidence_graph.application_worker import start_run

    service.request("prepare", {"jobs": [job(service, 1), job(service, 2)]})
    start_run(service.store)
    state = service.store.load()
    opened, fresh = state["jobs"]
    opened.update(
        status="needs_recheck",
        reason="page_lost",
        page_observation={"run_id": state["runtime"]["id"], "page_id": "p", "at": 1.0},
    )
    assert fresh["status"] == "queued" and not fresh.get("reason")
    # Queue jobs are single-flow jobs; the fresh one has no page or action history.
    for row in state["jobs"]:
        row["workflow"] = "single"
    # The earlier Worker exited without clearing its pid: this start is a recovery.
    state["worker_pid"] = 999_999
    service.store.save(state)
    start_run(service.store)
    opened, fresh = service.store.load()["jobs"]
    assert (opened["status"], opened["reason"]) == ("needs_recheck", "worker_restarted")
    assert fresh["status"] == "queued" and not fresh.get("reason")
