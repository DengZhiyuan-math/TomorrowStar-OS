"""Private historical score intervals remain separate from the scoring formula."""

import json

import pytest

from career_evidence_graph.application_benchmark import load_benchmark
from career_evidence_graph.application_worker import digest


def baseline():
    case = {
        "case_id": "synthetic-reference",
        "company": "Synthetic Reference Employer",
        "role_title": "Synthetic Engineer",
        "jd_revision": "c" * 64,
        "role": "reference",
        "outcome": "interview_invitation",
        "evidence_level": "gmail",
        "score": {"lower": 50, "upper": 75, "coverage": 75, "eligibility": "not_specified"},
        "analysis_id": "synthetic-analysis",
        "limitations": ["A later rejection remains recorded in the private event sequence."],
    }
    data = {
        "schemaVersion": 1,
        "source_snapshot_revision": "a" * 64,
        "configuration_revision": "b" * 64,
        "policy_version": "documentary-match/v1",
        "evaluated_at": "2026-10-17T10:00:00Z",
        "historical_materials_available": False,
        "protocol": "Re-evaluate synthetic JDs with current materials; do not remap scores.",
        "cases": [
            case,
            case
            | {
                "case_id": "synthetic-holdout",
                "role": "holdout",
                "outcome": "rejected",
                "score": {"lower": 0, "upper": 100, "coverage": 0, "eligibility": "not_specified"},
            },
        ],
    }
    return data | {"revision": digest(data)}


def write_baseline(root, data):
    directory = root / ".tomorrowstar-match-history"
    directory.mkdir()
    path = directory / "current.json"
    path.write_text(json.dumps(data))
    return path


def test_missing_benchmark_does_not_create_private_files(tmp_path):
    before = list(tmp_path.iterdir())
    loaded = load_benchmark(tmp_path, "a" * 64, "b" * 64)
    assert loaded["status"] == "missing"
    assert loaded["revision"] is None
    assert list(tmp_path.iterdir()) == before


def test_versioned_cohort_loads_only_reference_display_fields_without_writing(tmp_path):
    data = baseline()
    path = write_baseline(tmp_path, data)
    before = path.read_bytes()
    loaded = load_benchmark(tmp_path, "a" * 64, "b" * 64)
    assert loaded["status"] == "ready"
    assert loaded["revision"] == data["revision"]
    assert [case["case_id"] for case in loaded["reference_cases"]] == ["synthetic-reference"]
    assert "outcome" not in loaded["reference_cases"][0]
    assert loaded["reference_cases"][0]["limitations"] == data["cases"][0]["limitations"]
    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize(
    "lower,upper,position",
    [
        (76, 100, "above"),
        (0, 49, "below"),
        (75, 90, "overlaps"),
        (20, 50, "overlaps"),
        (50, 75, "overlaps"),
    ],
)
def test_comparison_uses_interval_separation_and_keeps_formula_numbers(
    tmp_path, lower, upper, position
):
    from career_evidence_graph.application_benchmark import compare_benchmark

    data = baseline()
    write_baseline(tmp_path, data)
    loaded = load_benchmark(tmp_path, "a" * 64, "b" * 64)
    original = {
        "lower": lower,
        "upper": upper,
        "coverage": 100 - upper + lower,
        "eligibility": "not_specified",
    }
    score = dict(original)
    compared = compare_benchmark(score, loaded)
    assert compared["status"] == "ready"
    assert compared["reference_range"] == {"lower": 50, "upper": 75}
    assert compared["revision"] == data["revision"]
    assert compared["comparisons"][0]["position"] == position
    assert compared["comparisons"][0]["score"] == data["cases"][0]["score"]
    assert len(compared["comparisons"]) == 1
    assert score == original


@pytest.mark.parametrize(
    "snapshot_revision,configuration_revision", [("d" * 64, "b" * 64), ("a" * 64, "e" * 64)]
)
def test_changed_materials_or_engine_make_reference_stale(
    tmp_path, snapshot_revision, configuration_revision
):
    data = baseline()
    write_baseline(tmp_path, data)
    loaded = load_benchmark(tmp_path, snapshot_revision, configuration_revision)
    assert loaded["status"] == "stale"
    assert loaded["revision"] == data["revision"]
    assert loaded["reference_cases"] == []


@pytest.mark.parametrize(
    "mutation",
    [
        "negative",
        "over-hundred",
        "backwards",
        "inconsistent-coverage",
        "boolean",
        "numeric-string",
        "duplicate-id",
        "policy",
        "eligibility",
        "materials-flag",
        "schema-boolean",
        "path-field",
        "digest",
        "non-finite",
    ],
)
def test_invalid_cohort_fails_closed_without_exposing_fields_or_paths(tmp_path, mutation):
    data = baseline()
    if mutation == "negative":
        data["cases"][0]["score"]["lower"] = -1
    elif mutation == "over-hundred":
        data["cases"][0]["score"]["upper"] = 101
    elif mutation == "backwards":
        data["cases"][0]["score"].update(lower=80, upper=20)
    elif mutation == "inconsistent-coverage":
        data["cases"][0]["score"]["coverage"] = 100
    elif mutation == "boolean":
        data["cases"][0]["score"]["coverage"] = True
    elif mutation == "numeric-string":
        data["cases"][0]["score"]["lower"] = "50"
    elif mutation == "duplicate-id":
        data["cases"][1]["case_id"] = data["cases"][0]["case_id"]
    elif mutation == "policy":
        data["policy_version"] = "unapproved-policy"
    elif mutation == "eligibility":
        data["cases"][0]["score"]["eligibility"] = "assume_eligible"
    elif mutation == "materials-flag":
        data["historical_materials_available"] = True
    elif mutation == "schema-boolean":
        data["schemaVersion"] = True
    elif mutation == "path-field":
        data["cases_path"] = "../../other-private-file.json"
    elif mutation == "non-finite":
        data["cases"][0]["score"]["upper"] = float("inf")
    if mutation not in {"digest", "non-finite"}:
        data["revision"] = digest({key: value for key, value in data.items() if key != "revision"})
    elif mutation == "digest":
        data["cases"][0]["company"] = "Synthetic secret tamper marker"
    write_baseline(tmp_path, data)
    loaded = load_benchmark(tmp_path, "a" * 64, "b" * 64)
    assert loaded["status"] == "invalid"
    assert loaded["revision"] is None
    assert loaded["reference_cases"] == []
    assert str(tmp_path) not in json.dumps(loaded)
    assert "Synthetic secret tamper marker" not in json.dumps(loaded)


@pytest.mark.parametrize(
    "kind",
    [
        "file-link",
        "directory-link",
        "root-link",
        "corrupt-json",
        "non-utf8",
        "directory-as-current",
    ],
)
def test_storage_boundary_rejects_links_and_corrupt_files_without_following_them(tmp_path, kind):
    root = tmp_path
    data = baseline()
    if kind == "root-link":
        actual = tmp_path / "actual"
        actual.mkdir()
        write_baseline(actual, data)
        root = tmp_path / "selected"
        root.symlink_to(actual, target_is_directory=True)
    elif kind == "directory-link":
        target = tmp_path / "elsewhere"
        target.mkdir()
        (target / "current.json").write_text(json.dumps(data))
        (tmp_path / ".tomorrowstar-match-history").symlink_to(target, target_is_directory=True)
    elif kind == "file-link":
        target = tmp_path / "elsewhere.json"
        target.write_text(json.dumps(data))
        directory = tmp_path / ".tomorrowstar-match-history"
        directory.mkdir()
        (directory / "current.json").symlink_to(target)
    else:
        path = write_baseline(tmp_path, data)
        if kind == "corrupt-json":
            path.write_text("{invalid JSON and synthetic secret diagnostic}")
        elif kind == "non-utf8":
            path.write_bytes(b"\xff\xfe")
        else:
            path.unlink()
            path.mkdir()
    loaded = load_benchmark(root, "a" * 64, "b" * 64)
    assert loaded["status"] == "invalid"
    assert loaded["reference_cases"] == []
    assert "synthetic secret diagnostic" not in json.dumps(loaded)
    assert str(tmp_path) not in json.dumps(loaded)


@pytest.mark.parametrize("status", ["missing", "stale", "invalid"])
def test_missing_stale_or_invalid_reference_never_gives_relative_position(status):
    from career_evidence_graph.application_benchmark import compare_benchmark

    compared = compare_benchmark(
        {"lower": 100, "upper": 100, "coverage": 100, "eligibility": "supported"},
        {
            "status": status,
            "revision": None,
            "reference_cases": [],
            "limitations": ["Synthetic unavailable reference"],
        },
    )
    assert compared["status"] == status
    assert compared["reference_range"] is None
    assert compared["comparisons"] == []


@pytest.mark.parametrize(
    "score",
    [
        None,
        {"lower": None, "upper": None, "coverage": None, "eligibility": "not_specified"},
        {"lower": 0, "upper": float("nan"), "coverage": 0, "eligibility": "not_specified"},
    ],
)
def test_missing_or_invalid_new_score_is_explicitly_unavailable(tmp_path, score):
    from career_evidence_graph.application_benchmark import compare_benchmark

    write_baseline(tmp_path, baseline())
    loaded = load_benchmark(tmp_path, "a" * 64, "b" * 64)
    compared = compare_benchmark(score, loaded)
    assert compared["status"] == "unavailable"
    assert compared["reference_range"] is None
    assert compared["comparisons"] == []


def test_only_holdout_and_context_cases_cannot_establish_a_reference_range(tmp_path):
    from career_evidence_graph.application_benchmark import compare_benchmark

    data = baseline()
    data["cases"][0]["role"] = "context"
    data["revision"] = digest({key: value for key, value in data.items() if key != "revision"})
    write_baseline(tmp_path, data)
    loaded = load_benchmark(tmp_path, "a" * 64, "b" * 64)
    assert loaded["status"] == "ready"
    compared = compare_benchmark(
        {"lower": 60, "upper": 80, "coverage": 80, "eligibility": "needs_input"}, loaded
    )
    assert compared["status"] == "unavailable"
    assert compared["reference_range"] is None


def test_reference_range_uses_only_explicit_roles_and_preserves_later_rejection_limits(tmp_path):
    from career_evidence_graph.application_benchmark import compare_benchmark

    data = baseline()
    data["cases"][1].update(
        role="reference",
        outcome="rejected",
        score={"lower": 60, "upper": 90, "coverage": 70, "eligibility": "not_specified"},
    )
    data["cases"].append(
        data["cases"][0]
        | {
            "case_id": "synthetic-context",
            "role": "context",
            "outcome": "assessment_invitation",
            "score": {"lower": 0, "upper": 100, "coverage": 0, "eligibility": "not_specified"},
        }
    )
    data["revision"] = digest({key: value for key, value in data.items() if key != "revision"})
    write_baseline(tmp_path, data)
    loaded = load_benchmark(tmp_path, "a" * 64, "b" * 64)
    compared = compare_benchmark(
        {"lower": 80, "upper": 95, "coverage": 85, "eligibility": "not_specified"}, loaded
    )
    assert compared["reference_range"] == {"lower": 50, "upper": 90}
    assert [case["position"] for case in compared["comparisons"]] == ["above", "overlaps"]
    assert compared["comparisons"][1]["limitations"] == data["cases"][1]["limitations"]
    assert all("outcome" not in case for case in compared["comparisons"])
