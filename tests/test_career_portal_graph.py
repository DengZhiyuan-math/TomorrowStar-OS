"""Synthetic relationship graphs must preserve documentary evidence boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_evidence_graph import career_portal_graph
from career_evidence_graph.career_portal_data import CareerCatalog, PortalDataError
from career_evidence_graph.career_portal_graph import CareerGraph, build_graph


def document(
    identifier: str,
    content: str | None,
    *,
    kind: str = "report",
    path: str | None = None,
) -> dict[str, object]:
    return {
        "id": identifier,
        "title": identifier.title(),
        "kind": kind,
        "source_name": path or f"reports/{identifier}.md",
        "content": content,
        "available": content is not None,
        "status": "documentary",
    }


def candidate_table(*rows: tuple[str, str, str], context: str = "Alpha project") -> str:
    return (
        "# Candidate skills\n\n"
        f"## {context}\n\n"
        "Experience source: `sources/alpha.md`\n\n"
        "| Candidate Skill | Why it is a candidate | Examination state |\n"
        "| --- | --- | --- |\n"
        + "".join(f"| {skill} | {reason} | {state} |\n" for skill, reason, state in rows)
    )


def skill_nodes(graph: dict) -> list[dict]:
    return [node for node in graph["nodes"] if node["type"] == "skill"]


def document_node(graph: dict, identifier: str) -> dict:
    matches = [
        node
        for node in graph["nodes"]
        if node["type"] == "document" and identifier in node["evidence_ids"]
    ]
    assert len(matches) == 1
    return matches[0]


def incident_edges(graph: dict, node: dict) -> list[dict]:
    return [edge for edge in graph["edges"] if node["id"] in {edge["source"], edge["target"]}]


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in nested_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in nested_keys(child)}
    return set()


def test_empty_graph_preserves_loader_warnings_without_inventing_nodes() -> None:
    warning = "One cloud document is unavailable."
    graph = build_graph([], [warning])
    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert warning in graph["warnings"]


def test_unavailable_cloud_document_is_visible_without_invented_relationships() -> None:
    graph = build_graph([document("cloud", None)])
    assert document_node(graph, "cloud")
    assert not skill_nodes(graph)
    assert not graph["edges"]
    assert graph["warnings"]


@pytest.mark.parametrize("target", ["https://[company]", "https://[::1", "https://／company"])
def test_malformed_reference_preserves_other_graph_relationships(target):
    content = "# Alpha\n\n[Related](beta.md)\n\n## Technology\n\nPython.\n"
    beta = document("beta", "# Beta\n")
    expected = build_graph([document("alpha", content), beta])

    graph = build_graph([document("alpha", content + f"\n[External]({target})\n"), beta])

    assert graph["nodes"] == expected["nodes"]
    assert graph["edges"] == expected["edges"]
    assert any("reports/alpha.md" in warning for warning in graph["warnings"])


def test_explicit_technology_mentions_have_documentary_source_citations() -> None:
    content = "# Alpha\n\n## Technology\n\nPython and FastAPI support the service.\n"
    graph = build_graph([document("alpha", content)])
    labels = {node["label"] for node in skill_nodes(graph)}
    assert {"Python", "FastAPI"} <= labels
    projects = [node for node in graph["nodes"] if node["type"] == "project"]
    assert len(projects) == 1
    for skill in skill_nodes(graph):
        assert skill["status"] in {"candidate", "documentary"}
        edges = incident_edges(graph, skill)
        assert edges
        for edge in edges:
            assert "alpha" in edge["evidence_ids"]
            basis = json.dumps(edge["basis"], ensure_ascii=False)
            assert "reports/alpha.md" in basis
            assert "Python and FastAPI support the service." in basis
            assert "reports/alpha.md:5" in basis


@pytest.mark.parametrize(
    "content",
    [
        "# Alpha\n\nPython appears in a generic project narrative.\n",
        "# Alpha\n\n## Hiring requirements\n\nPython and Docker desired.\n",
        "# Alpha\n\n## Technology\n\nA custom stack.\n\n## Future work\n\nUse Docker.\n",
    ],
)
def test_terms_outside_supported_technology_context_do_not_become_claims(content: str) -> None:
    graph = build_graph([document("alpha", content)])
    labels = {node["label"] for node in skill_nodes(graph)}
    assert not labels


def test_technology_allowlist_uses_whole_tokens() -> None:
    graph = build_graph(
        [document("alpha", "# Alpha\n\n## Technology\n\nJavaScript and CPython extensions.\n")]
    )
    labels = {node["label"] for node in skill_nodes(graph)}
    assert "Java" not in labels
    assert "Python" not in labels


@pytest.mark.parametrize(
    ("description", "expected_skills"),
    [
        ("The rest of the design can go further.", set()),
        ("Go implements the REST service.", {"Go", "REST"}),
    ],
)
def test_ambiguous_technology_names_require_explicit_capitalization(
    description: str, expected_skills: set[str]
) -> None:
    graph = build_graph([document("alpha", f"# Alpha\n\n## Technology\n\n{description}\n")])
    assert {node["label"] for node in skill_nodes(graph)} == expected_skills


def test_explicit_boundary_excludes_infrastructure_skill_derivation() -> None:
    content = (
        "# Infrastructure\n\n"
        "Boundary: excluded from career skill evidence\n\n"
        "## Technology\n\nPython, Docker and FastAPI support unrelated operations.\n"
    )
    graph = build_graph([document("infra", content)])
    assert document_node(graph, "infra")
    assert all(node["type"] == "document" for node in graph["nodes"])
    assert not skill_nodes(graph)
    assert all(edge["type"] not in {"mentions", "candidate"} for edge in graph["edges"])


def test_candidate_table_retains_examination_state_without_promoting_capability() -> None:
    content = candidate_table(("Python", "Used in Alpha", "reviewed, score 100"))
    graph = build_graph(
        [document("candidates", content, kind="skill", path="skill-graph/candidates.md")]
    )
    skills = skill_nodes(graph)
    assert len(skills) == 1
    skill = skills[0]
    assert skill["label"] == "Python"
    assert skill["status"] == "candidate"
    edges = incident_edges(graph, skill)
    assert edges
    assert "reviewed, score 100" in json.dumps(edges, ensure_ascii=False)
    assert not ({"score", "mastery", "mastery_score", "confidence_score"} & nested_keys(graph))


def test_candidate_excluded_rows_are_skipped_but_deferred_rows_remain_candidates() -> None:
    content = candidate_table(
        ("Python", "User has yet to be asked", "deferred"),
        ("Docker", "Outside the claimed contribution", "excluded"),
        ("FastAPI", "Incorrect attribution", "rejected"),
    )
    graph = build_graph([document("candidates", content, kind="skill")])
    skills = skill_nodes(graph)
    assert {node["label"] for node in skills} == {"Python"}
    assert skills[0]["status"] == "candidate"
    assert "deferred" in json.dumps(incident_edges(graph, skills[0]))
    assert graph["warnings"]


@pytest.mark.parametrize(
    "examination_state",
    [
        "User-attributed design Contribution candidate; Codex implementation excluded.",
        "用户设计候选；Codex 实现已排除，设计贡献仍待审核。",
    ],
)
def test_candidate_with_excluded_assisted_implementation_keeps_user_design_candidate(
    examination_state: str,
) -> None:
    content = candidate_table(("System design", "User designed the interface", examination_state))
    graph = build_graph([document("candidates", content, kind="skill")])
    skills = skill_nodes(graph)
    assert len(skills) == 1
    assert skills[0]["label"] == "System design"
    assert skills[0]["status"] == "candidate"
    assert examination_state in json.dumps(incident_edges(graph, skills[0]), ensure_ascii=False)


@pytest.mark.parametrize(
    "examination_state",
    [
        "Excluded from user Contribution and Skill evidence.",
        "Rejected because the implementation belongs to someone else.",
        "明确排除：不属于用户贡献。",
        "不纳入用户技能证据。",
        "已排除，责任归属不符。",
    ],
)
def test_explicit_row_exclusion_prefix_prevents_candidate_relationship(
    examination_state: str,
) -> None:
    content = candidate_table(("System design", "External work", examination_state))
    graph = build_graph([document("candidates", content, kind="skill")])
    assert not skill_nodes(graph)
    assert graph["warnings"]


def test_same_skill_connects_different_projects_without_merging_the_projects() -> None:
    graph = build_graph(
        [
            document("alpha", "# Alpha\n\n## Technology\n\nPython.\n"),
            document("beta", "# Beta\n\n## Technology\n\nPython.\n"),
        ]
    )
    skills = skill_nodes(graph)
    assert len(skills) == 1
    projects = {node["id"] for node in graph["nodes"] if node["type"] == "project"}
    assert len(projects) == 2
    neighbors = {
        endpoint
        for edge in incident_edges(graph, skills[0])
        for endpoint in (edge["source"], edge["target"])
        if endpoint != skills[0]["id"]
    }
    assert projects <= neighbors


def test_same_source_path_unifies_report_and_candidate_context_without_fuzzy_labels() -> None:
    graph = build_graph(
        [
            document(
                "alpha",
                "# Alpha\n\nExperience source: `sources/alpha.md`\n\n## Technology\n\nPython.\n",
            ),
            document(
                "candidates",
                candidate_table(("Docker", "Container workflow", "pending")),
                kind="skill",
                path="skill-graph/candidates.md",
            ),
            document("source", "# Alpha source\n", kind="source", path="sources/alpha.md"),
        ]
    )
    projects = [node for node in graph["nodes"] if node["type"] == "project"]
    assert len(projects) == 1
    assert {node["label"] for node in skill_nodes(graph)} == {"Python", "Docker"}
    for skill in skill_nodes(graph):
        assert any(
            projects[0]["id"] in {edge["source"], edge["target"]}
            for edge in incident_edges(graph, skill)
        )


@pytest.mark.parametrize(
    "reference",
    [
        "[Source](../sources/alpha.md)",
        "`sources/alpha.md`",
        "[[sources/alpha]]",
    ],
)
def test_references_link_only_catalogued_documents(reference: str) -> None:
    graph = build_graph(
        [
            document("alpha", f"# Alpha\n\n{reference}\n"),
            document("source", "# Source\n", kind="source", path="sources/alpha.md"),
        ]
    )
    origin = document_node(graph, "alpha")
    target = document_node(graph, "source")
    assert any(
        edge["type"] == "references"
        and {edge["source"], edge["target"]} == {origin["id"], target["id"]}
        for edge in graph["edges"]
    )


@pytest.mark.parametrize(
    "reference",
    [
        "[Remote](https://example.test/sources/alpha.md)",
        "[Private](../../sources/alpha.md)",
        "[Raw](../.career-evidence/raw/alpha.md)",
        "[Unknown](../sources/not-in-catalog.md)",
        "[Absolute](/private/source/alpha.md)",
    ],
)
def test_external_raw_and_uncatalogued_references_cannot_create_links(reference: str) -> None:
    graph = build_graph(
        [
            document("alpha", f"# Alpha\n\n{reference}\n"),
            document("source", "# Source\n", kind="source", path="sources/alpha.md"),
        ]
    )
    assert not [edge for edge in graph["edges"] if edge["type"] == "references"]


def test_ambiguous_bare_wikilink_is_not_assigned_to_an_arbitrary_same_stem() -> None:
    graph = build_graph(
        [
            document("alpha", "# Alpha\n\n[[detail]]\n"),
            document("source", "# Source\n", kind="source", path="sources/detail.md"),
            document(
                "contribution",
                "# Contribution\n",
                kind="contribution",
                path="contributions/detail.md",
            ),
        ]
    )
    assert not [edge for edge in graph["edges"] if edge["type"] == "references"]


def test_graph_ids_are_stable_and_every_edge_endpoint_exists() -> None:
    documents = [
        document("alpha", "# Alpha\n\n## Technology\n\nPython and FastAPI.\n"),
        document("beta", "# Beta\n\n## Technology\n\nPython and Docker.\n"),
    ]
    first = build_graph(documents)
    second = build_graph(list(reversed(documents)))
    assert {node["id"] for node in first["nodes"]} == {node["id"] for node in second["nodes"]}
    assert {edge["id"] for edge in first["edges"]} == {edge["id"] for edge in second["edges"]}
    nodes = {node["id"] for node in first["nodes"]}
    assert len(nodes) == len(first["nodes"])
    assert len({edge["id"] for edge in first["edges"]}) == len(first["edges"])
    assert all(edge["source"] in nodes and edge["target"] in nodes for edge in first["edges"])


def test_exact_document_identity_does_not_casefold_distinct_catalog_paths() -> None:
    graph = build_graph(
        [
            document("upper", "# Shared title\n", path="reports/Alpha.md"),
            document("lower", "# Shared title\n", path="reports/alpha.md"),
        ]
    )
    assert document_node(graph, "upper")["id"] != document_node(graph, "lower")["id"]
    assert len([node for node in graph["nodes"] if node["type"] == "project"]) == 2


def test_snapshot_reuses_unchanged_content_and_invalidates_changed_and_removed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    source = reports / "alpha.md"
    source.write_text("# Alpha\n\n## Technology\n\nPython.\n")
    reads = []

    def read(path: Path) -> str:
        reads.append(path)
        return path.read_text()

    monkeypatch.setattr(career_portal_graph, "read_document", read)
    projection = CareerGraph(CareerCatalog(tmp_path))
    first = projection.snapshot()
    assert {node["label"] for node in skill_nodes(first)} == {"Python"}
    assert projection.snapshot() == first
    assert reads == [source]
    source.write_text("# Alpha\n\n## Technology\n\nFastAPI and Docker.\n")
    changed = projection.snapshot()
    assert {node["label"] for node in skill_nodes(changed)} == {"FastAPI", "Docker"}
    assert reads == [source, source]
    source.unlink()
    removed = projection.snapshot()
    assert removed["nodes"] == []
    assert removed["edges"] == []


def test_snapshot_failed_read_stays_documentary_and_retries_after_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    source = reports / "alpha.md"
    source.write_text("# Alpha\n\n## Technology\n\nPython.\n")

    def unreadable(_path: Path) -> str:
        raise PortalDataError("document-unavailable", "Synthetic unavailable file", 503)

    monkeypatch.setattr(career_portal_graph, "read_document", unreadable)
    projection = CareerGraph(CareerCatalog(tmp_path))
    failed = projection.snapshot()
    assert len(failed["nodes"]) == 1
    assert failed["nodes"][0]["type"] == "document"
    assert not failed["edges"]
    assert len(failed["warnings"]) == 1
    monkeypatch.setattr(career_portal_graph, "read_document", Path.read_text)
    recovered = projection.snapshot()
    assert {node["label"] for node in skill_nodes(recovered)} == {"Python"}
    assert not recovered["warnings"]


@pytest.mark.parametrize("candidate_source", ["sources/alpha.md", "reports/alpha-summary.md"])
def test_project_directory_and_explicit_report_aliases_resolve_one_candidate_context(
    candidate_source: str,
) -> None:
    candidate = candidate_table(("Docker", "User container workflow", "pending")).replace(
        "sources/alpha.md", candidate_source
    )
    graph = build_graph(
        [
            document(
                "project",
                "# Alpha project\n\n[Full report](../alpha-summary.md)\n",
                path="reports/projects/alpha.md",
            ),
            document(
                "summary",
                "# Alpha full report\n\n## Technology\n\nPython.\n",
                path="reports/alpha-summary.md",
            ),
            document(
                "source",
                "# Source note\n\n[Full report](../reports/alpha-summary.md)\n",
                kind="source",
                path="sources/alpha.md",
            ),
            document(
                "catalog",
                "# Project index\n\n`reports/alpha-summary.md` and `sources/alpha.md`\n",
                path="reports/github-project-catalog.md",
            ),
            document("readme", "# Reports guide\n", path="reports/projects/README.md"),
            document("candidates", candidate, kind="skill", path="skill-graph/candidates.md"),
        ]
    )
    projects = [node for node in graph["nodes"] if node["type"] == "project"]
    assert len(projects) == 1
    assert projects[0]["label"] == "Alpha project"
    assert {node["label"] for node in skill_nodes(graph)} == {"Python", "Docker"}
    for skill in skill_nodes(graph):
        assert any(
            projects[0]["id"] in {edge["source"], edge["target"]}
            for edge in incident_edges(graph, skill)
        )
    assert document_node(graph, "catalog")
    assert document_node(graph, "readme")
    assert document_node(graph, "summary")


def test_flat_report_fallback_excludes_readme_index_and_catalog_documents() -> None:
    graph = build_graph(
        [
            document("alpha", "# Alpha\n\n## Technology\n\nPython.\n"),
            document("readme", "# Documentation\n", path="reports/README.md"),
            document("index", "# Index\n", path="reports/project-index.md"),
            document("catalog", "# Catalog\n", path="reports/github-catalog.md"),
        ]
    )
    assert [node["label"] for node in graph["nodes"] if node["type"] == "project"] == ["Alpha"]
    assert len([node for node in graph["nodes"] if node["type"] == "document"]) == 4


def test_repeated_relationships_merge_without_losing_distinct_source_citations() -> None:
    graph = build_graph(
        [
            document(
                "alpha",
                "# Alpha\n\nExperience source: `sources/alpha.md`\n\n"
                "## Technology\n\nPython for services.\nPython for analysis.\n",
            ),
            document(
                "candidates",
                candidate_table(("Python", "Candidate user contribution", "pending")),
                kind="skill",
                path="skill-graph/candidates.md",
            ),
            document("source", "# Source\n", kind="source", path="sources/alpha.md"),
        ]
    )
    relationships = [(edge["source"], edge["target"], edge["type"]) for edge in graph["edges"]]
    assert len(relationships) == len(set(relationships))
    skills = skill_nodes(graph)
    assert len(skills) == 1
    edges = incident_edges(graph, skills[0])
    assert len(edges) == 1
    assert edges[0]["evidence_ids"] == ["alpha", "candidates"]
    assert "reports/alpha.md:7 · Python for services." in edges[0]["basis"]
    assert "reports/alpha.md:8 · Python for analysis." in edges[0]["basis"]
    assert "skill-graph/candidates.md:" in edges[0]["basis"]
