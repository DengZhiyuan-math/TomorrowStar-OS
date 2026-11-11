"""The complete thin directory resolves new identities through registered captures."""

import hashlib
import json
from copy import deepcopy

import pytest

from career_evidence_graph.application_career_library import CareerLibrary


@pytest.fixture
def canonical(tmp_path):
    root = tmp_path / "career"
    root.mkdir()
    (root / ".career-evidence/raw").mkdir(parents=True)

    def write(path, data):
        raw = json.dumps(data).encode()
        (root / path).write_bytes(raw)
        return {"path": path, "sha256": hashlib.sha256(raw).hexdigest()}

    raw = json.dumps(
        {
            "confirmed_facts": {"theme": "Physics and biology", "status": "planned"},
            "not_selected": "private irrelevant text",
        }
    ).encode()
    capture_hash = hashlib.sha256(raw).hexdigest()
    capture_path = root / ".career-evidence/raw" / capture_hash
    capture_path.write_bytes(raw)
    link = {
        "source_id": "new-unseen-source",
        "content_identity": "sha256:" + capture_hash,
        "locator": "$.confirmed_facts",
        "role": "identity",
    }
    row = {
        "candidate_id": "unseen-identity",
        "title": "New interdisciplinary internship",
        "record_class": "current-confirmed-identity",
        "accepted_reading_summary": "A new physics and biology placement",
        "confirmed_identity_facts": {"status": "planned"},
        "source_links": [link],
    }
    catalog = write("catalog.json", {"records": [row]})
    registry = write(
        "registry.json",
        {
            "registry": {
                "sources": [
                    {
                        "source_id": link["source_id"],
                        "availability": "available",
                        "capture": {"content_hash": link["content_identity"]},
                    }
                ]
            }
        },
    )
    manifest = tmp_path / "manifest.json"
    descriptor = {
        "schema_version": 1,
        "root": str(root),
        "catalog": catalog,
        "source_registry": registry,
    }
    manifest.write_text(json.dumps(descriptor))
    base = {"documents": [], "items": [], "revision": "base"}
    return CareerLibrary(manifest), root, capture_path, base, write, manifest, descriptor


def test_complete_index_does_not_read_capture_but_selects_unlisted_identity(canonical):
    library, _, capture, base, *_ = canonical
    before = deepcopy(base)
    index = library.index()
    assert index["status"] == "available"
    assert "physics and biology" in index["records"][0]["summary"]
    assert index["records"][0]["read_status"] == "indexed_not_read"
    assert library.snapshot_for_analysis(base)["items"] == []
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert base == before
    assert len(loaded["items"]) == 2
    assert loaded["career_library"]["source_reads"][0]["status"] == "read"
    assert "Physics and biology" in loaded["items"][-1]["text"]
    assert "private irrelevant" not in json.dumps(loaded)
    assert "planned" in loaded["items"][-1]["text"]
    assert all(item["documentary_only"] and not item["rewrite_allowed"] for item in loaded["items"])
    capture.unlink()
    assert library.index()["status"] == "available"  # Discovery does not read raw captures.
    assert (
        library.snapshot_for_analysis(base, ["unseen-identity"])["career_library"]["source_reads"][
            0
        ]["status"]
        == "unavailable"
    )


def test_stale_capture_fails_closed(canonical):
    library, _, capture, base, *_ = canonical
    capture.write_text('{"confirmed_facts":"changed"}')
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert len(loaded["items"]) == 1
    assert loaded["career_library"]["source_reads"][0]["status"] == "hash_mismatch"
    assert "changed" not in json.dumps(loaded)


def test_bound_registry_drift_is_not_available(canonical):
    library, root, _, _, *_ = canonical
    (root / "registry.json").write_text('{"sources":[]}')
    assert library.index()["status"] == "unavailable"


def test_large_capture_is_not_read_as_evidence(canonical):
    library, _, capture, base, *_ = canonical
    capture.write_bytes(b"x" * 8_000_001)
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert len(loaded["items"]) == 1
    assert loaded["career_library"]["source_reads"][0]["status"] == "unavailable"


def test_unsupported_locator_is_explicit(canonical):
    library, root, _, base, write, manifest, descriptor = canonical
    catalog = json.loads((root / "catalog.json").read_text())
    catalog["records"][0]["source_links"][0]["locator"] = "repository.*"
    descriptor["catalog"] = write("catalog.json", catalog)
    manifest.write_text(json.dumps(descriptor))
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert loaded["career_library"]["source_reads"][0]["status"] == "unsupported_locator"
    assert len(loaded["items"]) == 1


@pytest.mark.parametrize(
    "category", ["candidate_facts", "website_candidates", "documentary_classifications", "projects"]
)
def test_registered_capture_supports_literal_hyphenated_keys(canonical, category):
    library, root, _, base, write, manifest, descriptor = canonical
    identifier = "exp-arbitrary-new-9"
    facts = {"research_theme": "Mathematics and neuroscience", "status": "planned"}
    raw = json.dumps({category: {identifier: facts}}).encode()
    capture_hash = hashlib.sha256(raw).hexdigest()
    (root / ".career-evidence/raw" / capture_hash).write_bytes(raw)
    catalog = json.loads((root / "catalog.json").read_text())
    link = catalog["records"][0]["source_links"][0]
    link.update(content_identity="sha256:" + capture_hash, locator=f"$.{category}.{identifier}")
    descriptor["catalog"] = write("catalog.json", catalog)
    descriptor["source_registry"] = write(
        "registry.json",
        {
            "sources": [
                {
                    "source_id": link["source_id"],
                    "availability": "available",
                    "capture": {"content_hash": link["content_identity"]},
                }
            ]
        },
    )
    manifest.write_text(json.dumps(descriptor))
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert loaded["career_library"]["source_reads"][0]["status"] == "read"
    assert json.loads(loaded["items"][-1]["text"]) == facts


@pytest.mark.parametrize(
    "locator",
    [
        "$..candidate",
        "$.candidate[*]",
        "$.candidate[0]",
        "$.candidate[?(@.key)]",
        "$.candidate.*",
        "$.candidate[0:2]",
    ],
)
def test_locator_does_not_gain_jsonpath_operators(locator):
    from career_evidence_graph.application_career_library import _capture_text

    with pytest.raises(ValueError, match="Unsupported source locator"):
        _capture_text(b'{"candidate": {"key": "fact"}}', locator)


def test_rfc6901_supports_arbitrary_literal_object_key():
    from career_evidence_graph.application_career_library import _capture_text

    raw = json.dumps({"arbitrary./~ key": {"exp-new-9": "verified fact"}}).encode()
    assert json.loads(_capture_text(raw, "/arbitrary.~1~0 key/exp-new-9")) == "verified fact"


def inventory_binding(canonical, project, raw, *, head=None, retained=False, fragment="L1"):
    library, root, _, base, write, manifest, descriptor = canonical
    file_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
    relative = "unfamiliar.tex" if fragment == "L1" else "source.js"
    capture = {
        "project": {"configured_path": str(project)},
        "git": {"head": head},
        "files": [{"path": relative, "sha256": file_hash, "type": "file", "size": len(raw)}],
    }
    if retained:
        capture = {
            "retained_source_files": [
                {"file_hash": file_hash, "origin": "/archived/" + relative, "utf8": raw.decode()}
            ]
        }
    payload = json.dumps(capture).encode()
    capture_hash = hashlib.sha256(payload).hexdigest()
    (root / ".career-evidence/raw" / capture_hash).write_bytes(payload)
    catalog = json.loads((root / "catalog.json").read_text())
    link = catalog["records"][0]["source_links"][0]
    link.update(content_identity=file_hash, locator=relative + "#" + fragment)
    descriptor["catalog"] = write("catalog.json", catalog)
    descriptor["source_registry"] = write(
        "registry.json",
        {
            "sources": [
                {
                    "source_id": link["source_id"],
                    "availability": "available",
                    "capture": {"content_hash": "sha256:" + capture_hash},
                }
            ]
        },
    )
    manifest.write_text(json.dumps(descriptor))
    return library, root, base, relative


def test_registered_inventory_resolves_exact_declared_file(canonical, tmp_path):
    project = tmp_path / "external-declared-project"
    project.mkdir()
    raw = b"Confirmed original claim.\nSecond line.\n"
    library, _, base, relative = inventory_binding(canonical, project, raw)
    (project / relative).write_bytes(raw)
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert loaded["career_library"]["source_reads"][0]["status"] == "read"
    assert loaded["items"][-1]["text"] == "Confirmed original claim.\n"
    (project / relative).write_text("Changed claim.")
    changed = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert changed["career_library"]["source_reads"][0]["status"] == "unpinned_git_revision"
    assert len(changed["items"]) == 1


def test_pinned_local_git_object_recovers_original_without_using_changed_worktree(
    canonical, tmp_path
):
    import subprocess

    project = tmp_path / "pinned-project"
    project.mkdir()
    raw = b"Verified original local object.\n"
    (project / "unfamiliar.tex").write_bytes(raw)
    for args in (
        ["init", "--quiet"],
        ["add", "unfamiliar.tex"],
        [
            "-c",
            "user.name=Synthetic",
            "-c",
            "user.email=synthetic@example.test",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
    ):
        subprocess.run(["git", "-C", str(project), *args], check=True, capture_output=True)
    head = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    library, _, base, relative = inventory_binding(canonical, project, raw, head=head)
    (project / relative).write_text("Changed live source.")
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert loaded["career_library"]["source_reads"][0]["status"] == "read"
    assert loaded["items"][-1]["text"] == raw.decode()
    assert (project / relative).read_text() == "Changed live source."


def test_retained_original_and_whole_javascript_fallback_are_explicit(canonical, tmp_path):
    raw = b'export const research = [{title: "Original interdisciplinary research"}];\n'
    library, _, base, _ = inventory_binding(
        canonical, tmp_path / "not-present", raw, retained=True, fragment="research[0]"
    )
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert loaded["career_library"]["source_reads"][0]["status"] == "read_whole_document"
    item = loaded["items"][-1]
    assert item["text"] == raw.decode()
    assert item["requested_locator"] == "research[0]"
    assert item["locator"] == "captured_file"
    assert item["source_read_status"] == "read_whole_document"


def test_inventory_cannot_substitute_a_different_file_identity(canonical, tmp_path):
    library, root, base, _ = inventory_binding(canonical, tmp_path, b"Original.\n")
    _, _, _, _, write, manifest, descriptor = canonical
    catalog = json.loads((root / "catalog.json").read_text())
    catalog["records"][0]["source_links"][0]["content_identity"] = "sha256:" + "0" * 64
    descriptor["catalog"] = write("catalog.json", catalog)
    manifest.write_text(json.dumps(descriptor))
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert loaded["career_library"]["source_reads"][0]["status"] == "hash_mismatch"
    assert len(loaded["items"]) == 1


def test_discovery_links_never_turn_missing_capture_into_positive_source_or_failure(canonical):
    library, root, capture, base, write, manifest, descriptor = canonical
    catalog = json.loads((root / "catalog.json").read_text())
    catalog["records"][0]["source_links"][0]["role"] = "discovery-only"
    descriptor["catalog"] = write("catalog.json", catalog)
    manifest.write_text(json.dumps(descriptor))
    capture.unlink()
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert loaded["career_library"]["source_reads"][0]["status"] == "discovery_only"
    assert loaded["career_library"]["unavailable_sources"] == []
    assert len(loaded["items"]) == 1


@pytest.mark.parametrize(
    "payload,locator,expected",
    [
        (b'{"repository":{"name":"Exact repository"}}', "repository.name", '"Exact repository"'),
        (b'{"facts":"Exact fact"}', "$", '{"facts":"Exact fact"}'),
    ],
)
def test_root_and_bare_object_locators_are_literal(payload, locator, expected):
    from career_evidence_graph.application_career_library import _capture_text

    assert _capture_text(payload, locator) == expected


def test_pdf_capture_is_reported_as_unsupported_format_not_missing(canonical):
    library, root, _, base, write, manifest, descriptor = canonical
    payload = b"%PDF-1.4\nASCII binary document content"
    revision = hashlib.sha256(payload).hexdigest()
    (root / ".career-evidence/raw" / revision).write_bytes(payload)
    catalog = json.loads((root / "catalog.json").read_text())
    link = catalog["records"][0]["source_links"][0]
    link.update(content_identity="sha256:" + revision, locator="$")
    descriptor["catalog"] = write("catalog.json", catalog)
    descriptor["source_registry"] = write(
        "registry.json",
        {
            "sources": [
                {
                    "source_id": link["source_id"],
                    "availability": "available",
                    "capture": {"content_hash": link["content_identity"]},
                }
            ]
        },
    )
    manifest.write_text(json.dumps(descriptor))
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert loaded["career_library"]["source_reads"][0]["status"] == "unsupported_content_format"
    assert len(loaded["items"]) == 1


def test_large_registered_aggregate_reads_only_the_selected_fact(canonical):
    library, root, _, base, write, manifest, descriptor = canonical
    payload = json.dumps(
        {"facts": "Selected confirmed fact", "unselected": "x" * 2_500_000}
    ).encode()
    revision = hashlib.sha256(payload).hexdigest()
    (root / ".career-evidence/raw" / revision).write_bytes(payload)
    catalog = json.loads((root / "catalog.json").read_text())
    link = catalog["records"][0]["source_links"][0]
    link.update(content_identity="sha256:" + revision, locator="$.facts")
    descriptor["catalog"] = write("catalog.json", catalog)
    descriptor["source_registry"] = write(
        "registry.json",
        {
            "sources": [
                {
                    "source_id": link["source_id"],
                    "availability": "available",
                    "capture": {"content_hash": link["content_identity"]},
                }
            ]
        },
    )
    manifest.write_text(json.dumps(descriptor))
    loaded = library.snapshot_for_analysis(base, ["unseen-identity"])
    assert loaded["career_library"]["source_reads"][0]["status"] == "read"
    assert json.loads(loaded["items"][-1]["text"]) == "Selected confirmed fact"
    assert "unselected" not in json.dumps(loaded)
