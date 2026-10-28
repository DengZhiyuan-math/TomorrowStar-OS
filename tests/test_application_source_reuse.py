"""Exact retained material can supply documentary sources, without new acceptance."""

import hashlib
import json

import pytest

from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import CareerCatalog, PortalDataError


def _write_retained_fixture(root, source_text=None, profile=None, groups=None):
    from career_evidence_graph.application_source_reuse import retained_material_sources

    (root / "sources").mkdir(parents=True, exist_ok=True)
    captures = root / ".retained"
    captures.mkdir(exist_ok=True)
    source = source_text or (
        "\\documentclass{article}\n\\begin{document}\n"
        "\\section{Education}\n"
        "\\entry{Example University}{2024--2028}{PhD in progress}{Expected July 2028}\n"
        "\\section{Experience}\n"
        "Built a Python service with the engineering team.\n\\end{document}\n"
    )
    pdf = b"%PDF-1.4 synthetic retained bytes\n"

    def sha(value):
        return hashlib.sha256(value).hexdigest()

    approval = {
        "schema": "material15-human-material-acceptance/v1",
        "actor": "human-user",
        "at": "2026-10-19T12:00:00Z",
        "user_reply": "I accept this exact PDF content and layout.",
        "decision": "accept_exact_revised_pdf_content_and_layout",
        "scope": ["complete_pdf_content", "pdf_layout"],
        "tex_sha256": sha(source.encode()),
        "pdf_sha256": sha(pdf),
    }
    approval_raw = json.dumps(approval).encode()
    task = {
        "id": "a" * 32,
        "application_id": "b" * 32,
        "application_revision": "c" * 64,
        "job_binding": {"revision": "d" * 64},
        "inputs": {"original": "retained"},
        "input_epoch": 0,
        "draft_id": "e" * 32,
        "draft_sha256": "f" * 64,
        "prism": {
            "source_revision": "1" * 64,
            "main": "resume.tex",
            "files": {"resume.tex": sha(source.encode())},
        },
        "resume_id": "2" * 32,
        "resume_sha256": sha(pdf),
        "origin": "existing_latex",
        "factual_review": "pending",
        "status": "materials_ready",
        "materials_confirmed": True,
    }
    receipt = {
        "schemaVersion": 1,
        "kind": "retained_human_material_acceptance",
        "human_actor": "user",
        **{
            key: task[key]
            for key in (
                "task_id",
                "application_id",
                "application_revision",
                "job_binding",
                "input_epoch",
                "draft_id",
                "draft_sha256",
                "resume_id",
            )
            if key in task
        },
        "task_id": task["id"],
        "inputs_revision": digest(task["inputs"]),
        "source_revision": task["prism"]["source_revision"],
        "source_sha256": sha(source.encode()),
        "pdf_sha256": sha(pdf),
        "task_revision_before_record": "3" * 64,
        "export_manifest_sha256": "4" * 64,
        "approval_record": {
            "sha256": sha(approval_raw),
            "accepted_at": approval["at"],
            "statement": approval["user_reply"],
        },
        "operator_record": {
            "actor": "codex",
            "operation": "record_existing_human_decision",
            "recorded_at": "2026-10-19T12:01:00Z",
        },
    }
    receipt["revision"] = digest(receipt)
    task["material_acceptance"] = receipt
    raw = {
        "source": source.encode(),
        "pdf": pdf,
        "approval": approval_raw,
        "task": json.dumps(task).encode(),
    }
    profile = profile or {
        "education": [
            {
                "degree": "PhD in progress",
                "institution": "Example University",
                "period": "2024--2028",
                "detail": "Expected July 2028",
            }
        ]
    }
    manifest = {
        "schema": "retained-resume-sources/v1",
        "captures": {},
        "groups": [
            {
                "title": "Education",
                "start_line": 3,
                "end_line": 4,
                "source_kind": "education",
                "context_source_ids": [],
                "education_profile_locator": "profile.education[0]",
                "education_profile_sha256": digest(profile["education"][0]),
            },
            {
                "title": "Service",
                "start_line": 5,
                "end_line": 6,
                "source_kind": "accepted_resume",
                "context_source_ids": ["scope:service"],
                "education_profile_locator": None,
                "education_profile_sha256": None,
            },
        ],
    }
    if groups is not None:
        manifest["groups"] = groups
    for name, content in raw.items():
        path = captures / name
        path.write_bytes(content)
        manifest["captures"][name] = {"path": f".retained/{name}", "sha256": sha(content)}
    path = root / "sources/retained-resume-sources.json"
    path.write_text(json.dumps(manifest))
    catalog = CareerCatalog(root)
    document = catalog._record(path, "source", detail=True)
    profile_source = {
        "id": "profile-doc",
        "revision": "5" * 64,
        "source_name": "sources/profile.json",
    }
    return {
        "catalog": catalog,
        "document": document,
        "profile": profile,
        "profile_source": profile_source,
        "manifest": manifest,
        "task": task,
        "approval": approval,
        "raw": raw,
        "source": source,
        "reader": retained_material_sources,
    }


def write_retained_material(career_root, source_text, profile=None, groups=None):
    """Write synthetic captured material using the retained acceptance schema."""
    return _write_retained_fixture(career_root, source_text, profile, groups)["manifest"]


@pytest.fixture
def retained_capture(tmp_path):
    return _write_retained_fixture(tmp_path / "career")


def test_retained_sources_preserve_exact_words_and_documentary_education(retained_capture):
    case = retained_capture
    items = case["reader"](
        case["catalog"], case["document"], case["profile"], case["profile_source"]
    )
    assert len(items) == 2
    assert json.loads(items[0]["text"])["accepted_latex"].startswith("\\section{Education}\n")
    assert items[0]["source_kind"] == "education" and items[0]["rewrite_allowed"] is False
    assert (
        items[1]["text"]
        == "\\section{Experience}\nBuilt a Python service with the engineering team.\n"
    )
    assert items[1]["context_source_ids"] == ["scope:service"]
    assert items[1]["retained_receipt_revision"] == case["task"]["material_acceptance"]["revision"]


def _refresh(case):
    path = case["catalog"].root / "sources/retained-resume-sources.json"
    path.write_text(json.dumps(case["manifest"]))
    case["document"] = case["catalog"]._record(path, "source", detail=True)


def _replace_capture(case, name, value):
    raw = json.dumps(value).encode()
    path = case["catalog"].root / case["manifest"]["captures"][name]["path"]
    path.write_bytes(raw)
    case["manifest"]["captures"][name]["sha256"] = hashlib.sha256(raw).hexdigest()
    _refresh(case)


def _reject(case):
    with pytest.raises(PortalDataError) as error:
        case["reader"](case["catalog"], case["document"], case["profile"], case["profile_source"])
    assert error.value.code == "resume_reuse_invalid"
    assert str(case["catalog"].root) not in str(error.value)


def test_non_object_task_capture_fails_with_content_free_error(retained_capture):
    _replace_capture(retained_capture, "task", [])
    _reject(retained_capture)


@pytest.mark.parametrize("name", ["task", "source", "pdf", "approval"])
def test_stale_capture_hash_is_not_accepted(retained_capture, name):
    case = retained_capture
    path = case["catalog"].root / case["manifest"]["captures"][name]["path"]
    path.write_bytes(path.read_bytes() + b" ")
    _reject(case)


@pytest.mark.parametrize("state", ["missing", "unconfirmed", "not_ready", "tampered_receipt"])
def test_material_acceptance_must_be_present_confirmed_and_valid(retained_capture, state):
    case = retained_capture
    task = case["task"]
    if state == "missing":
        task.pop("material_acceptance")
    elif state == "unconfirmed":
        task["materials_confirmed"] = False
    elif state == "not_ready":
        task["status"] = "review_required"
    else:
        task["material_acceptance"]["source_sha256"] = "0" * 64
    _replace_capture(case, "task", task)
    _reject(case)


def test_flow_publishes_the_retained_material_acceptance_rule(retained_capture):
    from career_evidence_graph.application_flow import ApplicationFlowService

    task = retained_capture["task"]
    assert ApplicationFlowService.valid_material_acceptance(task) is True
    tampered = json.loads(json.dumps(task))
    tampered["material_acceptance"]["source_sha256"] = "0" * 64
    assert ApplicationFlowService.valid_material_acceptance(tampered) is False
    tampered["material_acceptance"] = "not a receipt"
    assert ApplicationFlowService.valid_material_acceptance(tampered) is False
    absent = {key: value for key, value in task.items() if key != "material_acceptance"}
    assert ApplicationFlowService.valid_material_acceptance(absent) is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", ["complete_pdf_content"]),
        ("actor", "codex"),
        ("decision", "draft_only"),
        ("tex_sha256", "0" * 64),
        ("pdf_sha256", "0" * 64),
        ("at", "2026-10-19T12:00:01Z"),
        ("user_reply", "Different approval"),
    ],
)
def test_original_human_approval_is_bound_beyond_its_hash(retained_capture, field, value):
    case = retained_capture
    approval = case["approval"] | {field: value}
    _replace_capture(case, "approval", approval)
    receipt = case["task"]["material_acceptance"]
    receipt["approval_record"]["sha256"] = case["manifest"]["captures"]["approval"]["sha256"]
    receipt["revision"] = digest(
        {key: value for key, value in receipt.items() if key != "revision"}
    )
    _replace_capture(case, "task", case["task"])
    _reject(case)


@pytest.mark.parametrize("field", ["degree", "institution", "period", "detail"])
def test_changed_education_record_invalidates_previous_binding(retained_capture, field):
    case = retained_capture
    case["profile"]["education"][0][field] = "Changed documentary fact"
    _reject(case)


@pytest.mark.parametrize(
    "change",
    [
        "empty",
        "unknown_flag",
        "overlap",
        "out_of_range",
        "education_as_work",
        "work_as_education",
        "mixed",
        "education_bad_locator",
        "work_education_binding",
    ],
)
def test_manifest_cannot_grant_arbitrary_source_or_span_authority(retained_capture, change):
    case = retained_capture
    groups = case["manifest"]["groups"]
    if change == "empty":
        case["manifest"]["groups"] = []
    elif change == "unknown_flag":
        groups[1]["resume_eligible"] = True
    elif change == "overlap":
        groups.append(dict(groups[1]))
    elif change == "out_of_range":
        groups[1]["end_line"] = 500
    elif change == "education_as_work":
        groups[0].update(
            source_kind="accepted_resume",
            education_profile_locator=None,
            education_profile_sha256=None,
        )
    elif change == "work_as_education":
        groups[0].update(start_line=5, end_line=6)
    elif change == "mixed":
        groups[0]["end_line"] = 6
    elif change == "education_bad_locator":
        groups[0]["education_profile_locator"] = "profile.education[3]"
    else:
        groups[1]["education_profile_locator"] = "profile.education[0]"
    _refresh(case)
    _reject(case)


@pytest.mark.parametrize(
    "relative", ["../escape", "/private/tmp/escape", "sources/public.json", ".retained/../source"]
)
def test_captures_must_use_hidden_root_relative_paths(retained_capture, relative):
    case = retained_capture
    case["manifest"]["captures"]["source"]["path"] = relative
    _refresh(case)
    _reject(case)


def test_symlinked_capture_is_not_followed(retained_capture):
    case = retained_capture
    path = case["catalog"].root / ".retained/source"
    target = path.with_name("original")
    path.rename(target)
    path.symlink_to(target)
    _reject(case)


def test_stale_manifest_document_is_not_reused(retained_capture):
    case = retained_capture
    path = case["catalog"].root / "sources/retained-resume-sources.json"
    path.write_text(json.dumps(case["manifest"]) + " ")
    _reject(case)


def test_one_education_record_cannot_bind_two_disjoint_credentials(retained_capture):
    case = retained_capture
    groups = case["manifest"]["groups"]
    groups[0]["end_line"] = 3
    groups.insert(1, groups[0] | {"start_line": 4, "end_line": 4})
    _refresh(case)
    _reject(case)


@pytest.mark.parametrize(
    "field,value",
    [
        ("degree", "Bachelor of Science"),
        ("degree", "PhD awarded"),
        ("period", "2023--2026"),
        ("institution", "Unrelated University"),
    ],
)
def test_rehashed_profile_cannot_misbind_initial_education(retained_capture, field, value):
    case = retained_capture
    entry = case["profile"]["education"][0]
    entry[field] = value
    case["manifest"]["groups"][0]["education_profile_sha256"] = digest(entry)
    _refresh(case)
    _reject(case)


def test_equivalent_documentary_core_reuses_record_without_shortening_it(retained_capture):
    case = retained_capture
    entry = case["profile"]["education"][0]
    entry.update(
        degree="Doctor of Philosophy candidate",
        institution="Universität Example",
        period="2024 to 2028",
        detail="Expected July 2028; additional recorded documentary detail",
    )
    case["manifest"]["groups"][0]["education_profile_sha256"] = digest(entry)
    _refresh(case)
    items = case["reader"](
        case["catalog"], case["document"], case["profile"], case["profile_source"]
    )
    assert json.loads(items[0]["text"])["profile_record"] == entry
    assert "PhD in progress" in json.loads(items[0]["text"])["accepted_latex"]


def test_same_hash_bound_source_cannot_be_relabelled_as_a_different_school(retained_capture):
    case = retained_capture
    text = case["source"].replace("Example University", "Different University")
    raw = text.encode()
    path = case["catalog"].root / ".retained/source"
    path.write_bytes(raw)
    case["manifest"]["captures"]["source"]["sha256"] = hashlib.sha256(raw).hexdigest()
    _refresh(case)
    _reject(case)


def test_ongoing_status_in_recorded_detail_cannot_disappear(retained_capture):
    case = retained_capture
    profile = {
        "education": [
            {
                "degree": "PhD",
                "institution": "Example University",
                "period": "2024--2028",
                "detail": "Not awarded; expected July 2028",
            }
        ]
    }
    source = (
        case["source"].replace("PhD in progress", "PhD").replace("Expected July 2028", "Research")
    )
    case = _write_retained_fixture(case["catalog"].root, source_text=source, profile=profile)
    _reject(case)


def test_explicit_expected_completion_month_cannot_change(retained_capture):
    case = retained_capture
    source = case["source"].replace("Expected July 2028", "Expected August 2028")
    case = _write_retained_fixture(case["catalog"].root, source_text=source)
    _reject(case)


def test_not_yet_awarded_in_detail_cannot_disappear(retained_capture):
    case = retained_capture
    profile = {
        "education": [
            {
                "degree": "PhD",
                "institution": "Example University",
                "period": "2024--2028",
                "detail": "Not yet awarded",
            }
        ]
    }
    source = (
        case["source"].replace("PhD in progress", "PhD").replace("Expected July 2028", "Research")
    )
    case = _write_retained_fixture(case["catalog"].root, source_text=source, profile=profile)
    _reject(case)


def test_matching_not_yet_awarded_can_reuse_original_words(retained_capture):
    case = retained_capture
    profile = {
        "education": [
            {
                "degree": "PhD",
                "institution": "Example University",
                "period": "2024--2028",
                "detail": "Not yet awarded",
            }
        ]
    }
    source = (
        case["source"]
        .replace("PhD in progress", "PhD")
        .replace("Expected July 2028", "Not yet awarded")
    )
    case = _write_retained_fixture(case["catalog"].root, source_text=source, profile=profile)
    items = case["reader"](
        case["catalog"], case["document"], case["profile"], case["profile_source"]
    )
    assert "Not yet awarded" in json.loads(items[0]["text"])["accepted_latex"]


@pytest.mark.parametrize(
    "negative", ["Not formally awarded", "Never awarded", "Hasn't been awarded"]
)
def test_unknown_negated_award_is_not_treated_as_completion(retained_capture, negative):
    case = retained_capture
    profile = {
        "education": [
            {
                "degree": "PhD",
                "institution": "Example University",
                "period": "2024--2028",
                "detail": negative,
            }
        ]
    }
    source = (
        case["source"].replace("PhD in progress", "PhD").replace("Expected July 2028", negative)
    )
    case = _write_retained_fixture(case["catalog"].root, source_text=source, profile=profile)
    _reject(case)


@pytest.mark.parametrize(
    "detail",
    [
        "Expected completion date: August 2028",
        "Expected July 2028; expected graduation August 2028",
        "Expected completion date to be confirmed",
    ],
)
def test_uncertain_or_conflicting_expected_completion_is_not_reused(retained_capture, detail):
    case = retained_capture
    entry = case["profile"]["education"][0]
    entry["detail"] = detail
    case["manifest"]["groups"][0]["education_profile_sha256"] = digest(entry)
    _refresh(case)
    _reject(case)


def test_only_expected_completion_dates_bind_not_unrelated_funding_dates(retained_capture):
    case = retained_capture
    profile = {
        "education": [
            {
                "degree": "Doctor of Philosophy candidate",
                "institution": "Example University",
                "period": "2024--2028",
                "detail": "Expected completion date: July 2028; scholarship began September 2026",
            }
        ]
    }
    source = case["source"].replace(
        "Expected July 2028", "Expected graduation in Jul 2028; project funding began August 2026"
    )
    case = _write_retained_fixture(case["catalog"].root, source_text=source, profile=profile)
    items = case["reader"](
        case["catalog"], case["document"], case["profile"], case["profile_source"]
    )
    assert (
        json.loads(items[0]["text"])["profile_record"]["detail"]
        == profile["education"][0]["detail"]
    )
