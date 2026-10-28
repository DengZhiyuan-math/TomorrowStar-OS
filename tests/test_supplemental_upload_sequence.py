"""Required supplemental attachments precede final form completeness checks."""

from copy import deepcopy
from time import time

import pytest
from test_p07_runner import field, retained_runner

from career_evidence_graph import application_form_runner as forms
from career_evidence_graph.application_materials import SupplementalMaterials


def attachment():
    return field(
        "C:\\fakepath\\cover-letter.pdf",
        id="cover",
        type="file",
        question="Cover letter",
        options=[],
        multiple=False,
        resume=False,
        filename="cover-letter.pdf",
        file_sha256="a" * 64,
        draft_path="cover",
    )


def test_required_cover_upload_is_reachable_before_final_validation(tmp_path, monkeypatch):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    runner.store.answers.put_answer(
        {
            "question": "Email",
            "value": "synthetic@example.invalid",
            "scope": {},
            "state": "confirmed",
        }
    )
    cover = attachment()
    cover.update(value="", filename="", file_sha256="", valid=False)
    observed = {
        "fields": [
            field("synthetic@example.invalid", options=[], multiple=False, resume=False),
            cover,
        ],
        "document_token": "document",
        "parser": {"status": "complete"},
    }
    now = time()
    for moment in (now, now + 0.25, now + 0.5):
        monkeypatch.setattr(forms.time, "time", lambda moment=moment: moment)
        forms.capture(runner, page, job, batch, observed)
    state = runner.store.load()
    state["control"] = "running"
    runner.store.save(state)
    job = state["jobs"][0]
    monkeypatch.setattr(runner, "observe", lambda *_: deepcopy(observed))
    monkeypatch.setattr(runner, "check_inputs", lambda *_args, **_options: None)
    monkeypatch.setattr(SupplementalMaterials, "prepare", lambda *_args, **_options: True)
    stages = []

    def uploaded(*_args):
        stages.append("upload")
        return True

    monkeypatch.setattr(runner, "upload_supplement", uploaded)
    check_ready = forms.check_ready

    def checked(*args):
        stages.append("complete")
        return check_ready(*args)

    monkeypatch.setattr(forms, "check_ready", checked)

    runner.process(job, batch)

    assert stages == ["upload"]
    assert runner.store.load()["jobs"][0]["status"] != "ready_for_review"


@pytest.mark.parametrize(
    "change,intervention",
    [
        ("none", False),
        ("same_name_other_bytes", True),
        ("later_same_name_other_bytes", True),
        ("other_filename", True),
        ("late_attachment_input", True),
        ("late_other_field", True),
    ],
)
def test_verified_attachment_readback_keeps_exact_identity_and_late_inputs(
    tmp_path, monkeypatch, change, intervention
):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    empty = attachment()
    empty.update(value="", filename="", file_sha256="", valid=False)
    before = {"fields": [field(""), empty], "document_token": "document"}
    forms.capture(runner, page, job, batch, before)
    state = runner.store.load()
    current = state["jobs"][0]
    current["form_state"]["parser"]["status"] = "stable"
    verified = attachment()
    after = {
        "fields": [field(""), verified],
        "document_token": "document",
        "user_activity": {"cover": 1},
    }
    forms.note_write(
        current,
        verified,
        verified["value"],
        {"key": "cover-material", "revision": "a" * 64, "source": "system_material"},
        observed=after,
    )
    runner.store.save(state)
    if change == "later_same_name_other_bytes":
        first = forms.capture(runner, page, job, batch, after)
        assert not first.get("intervention_pending")
        assert first["written_fields"]["cover"]["readback_pending"] is False
        state = runner.store.load()
        state["jobs"][0]["form_state"]["parser"]["status"] = "stable"
        runner.store.save(state)
    actual = deepcopy(after)
    if change in {"same_name_other_bytes", "later_same_name_other_bytes"}:
        actual["fields"][1]["file_sha256"] = "b" * 64
    elif change == "other_filename":
        actual["fields"][1]["filename"] = "human-letter.pdf"
    elif change == "late_attachment_input":
        actual["user_activity"]["cover"] = 2
    elif change == "late_other_field":
        actual["fields"][0]["value"] = "human@example.invalid"
        actual["user_activity"]["email"] = 1

    result = forms.capture(runner, page, job, batch, actual)

    assert bool(result.get("intervention_pending")) is intervention
    assert result["parser"]["status"] == "waiting"
    assert result["baseline"]["cover"]["filename"] == ""
    assert result["ack_activity"]["cover"] == 1
    if change == "late_other_field":
        fills, kept = forms.plan(
            job,
            actual,
            [(actual["fields"][0], "saved@example.invalid", {"key": "email", "revision": "one"})],
        )
        assert fills == kept == [] and job["form_state"]["differences"]
    if change in {"same_name_other_bytes", "later_same_name_other_bytes", "other_filename"}:
        assert result["written_fields"]["cover"]["source"]["revision"] == "a" * 64
