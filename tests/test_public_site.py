"""Synthetic checks for the explicit public presentation boundary."""

import json
from pathlib import Path

import pytest

from career_evidence_graph.public_site import export_public_site


def test_export_updates_one_snapshot_and_keeps_private_material_out(tmp_path: Path) -> None:
    source = tmp_path / "selected.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "public-site-source/v1",
                "publication_status": "public",
                "profile": {"name": "Synthetic Person"},
                "ai_projects": [
                    {
                        "visibility": "public",
                        "id": "sample",
                        "title": "Sample project",
                        "type": "Research",
                        "summary": "Bounded experiment.",
                        "skills": ["Python"],
                    },
                    {"title": "Hidden project", "type": "Private", "summary": "Private notes"},
                ],
            }
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "public.json"
    result = export_public_site(source, destination)
    published = json.loads(destination.read_text())
    assert published["profile"]["name"] == "Synthetic Person"
    assert [item["title"] for item in published["aiProjects"]] == ["Sample project"]
    assert published["skills"][0]["name"] == "Python"
    assert published["skills"][0]["authority"] == "declared"
    assert "Hidden project" not in destination.read_text()
    assert "mastery" not in destination.read_text()
    assert result["changed"] is True
    assert export_public_site(source, destination)["changed"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"publication_status": "draft"},
        {"raw_answers": "Private answer"},
        {"profile": {"name": "Synthetic", "mastery": 90}},
        {"profile": {"name": "Synthetic", "summary": "/Users/synthetic/private"}},
        {"profile": {"name": "Synthetic", "summary": "<script>alert(1)</script>"}},
        {"profile": {"name": "Synthetic", "summary": '<script src="https://example.com/"'}},
        {
            "profile": {
                "name": "Synthetic",
                "links": [{"label": "Local", "href": "http://127.0.0.1:8765"}],
            }
        },
    ],
)
def test_invalid_public_selection_preserves_previous_site(tmp_path: Path, change: dict) -> None:
    selected = {
        "schema_version": "public-site-source/v1",
        "publication_status": "public",
        "profile": {"name": "Synthetic"},
    }
    selected.update(change)
    source = tmp_path / "selected.json"
    source.write_text(json.dumps(selected))
    destination = tmp_path / "public.json"
    destination.write_text('{"previous": true}\n')
    with pytest.raises(ValueError):
        export_public_site(source, destination)
    assert destination.read_text() == '{"previous": true}\n'


@pytest.mark.parametrize(
    "host",
    [
        "127.1",
        "127.0.1",
        "0177.0.0.1",
        "0x7f.0.0.1",
        "127.0.0.1.",
        "localhost.",
        "LOCALHOST.",
        "app.localhost.",
        "app.local.",
        "app.internal.",
        "127%2e1",
        "127。1",
        "localhost。",
        "app.localhost。",
    ],
)
@pytest.mark.parametrize("placement", ["link", "markup"])
def test_local_host_variants_cannot_enter_public_snapshot(tmp_path, host, placement):
    url = f"https://{host}/jobs/42"
    profile = {"name": "Synthetic"}
    if placement == "link":
        profile["links"] = [{"label": "Local", "href": url}]
    else:
        profile["summary"] = f'<a href="{url}">Local</a>'
    source = tmp_path / "selected.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "public-site-source/v1",
                "publication_status": "public",
                "profile": profile,
            }
        )
    )
    original = b'{"previous": true}\n'
    destination = tmp_path / "public.json"
    destination.write_bytes(original)

    with pytest.raises(ValueError, match="public-site-link-private"):
        export_public_site(source, destination)

    assert destination.read_bytes() == original


@pytest.mark.parametrize(
    "url",
    [
        "https://careers.example.test/jobs/42",
        "https://careers.example.test./jobs/42",
        "https://8.8.8.8/jobs/42",
        "/projects/sample",
        "mailto:synthetic@example.test",
    ],
)
def test_public_links_and_supported_local_routes_remain_accepted(tmp_path, url):
    source = tmp_path / "selected.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "public-site-source/v1",
                "publication_status": "public",
                "profile": {"name": "Synthetic", "links": [{"label": "Selected", "href": url}]},
            }
        )
    )
    destination = tmp_path / "public.json"

    export_public_site(source, destination)
    assert json.loads(destination.read_text())["profile"]["links"] == [
        {"label": "Selected", "href": url}
    ]


@pytest.mark.parametrize("control", ["\t", "\n", "\r", "\x00", "\x1f", "\x7f"])
@pytest.mark.parametrize("placement", ["link", "markup"])
def test_control_characters_cannot_hide_a_local_host(tmp_path, control, placement):
    url = f"/{control}/127.0.0.1:8765/private"
    profile = {"name": "Synthetic"}
    if placement == "link":
        profile["links"] = [{"label": "Local", "href": url}]
    else:
        profile["summary"] = f'<a href="{url}">Local</a>'
    source = tmp_path / "selected.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "public-site-source/v1",
                "publication_status": "public",
                "profile": profile,
            }
        )
    )
    destination = tmp_path / "public.json"
    original = b'{"previous":true}\n'
    destination.write_bytes(original)

    with pytest.raises(ValueError, match="public-site-link-invalid"):
        export_public_site(source, destination)

    assert destination.read_bytes() == original


@pytest.mark.parametrize(
    "url",
    [
        r"https://127.0.0.1\public.example/private",
        r"https://localhost\public.example/private",
        r"https://192.168.1.2\public.example/private",
        r"http://10.0.0.1\public.example/private",
        r"https://[::1]\public.example/private",
        r"https://public.example/files\report",
        r"/\127.0.0.1/private",
    ],
)
@pytest.mark.parametrize("placement", ["link", "markup", "entity-markup"])
def test_backslashes_cannot_bypass_public_link_checks(tmp_path, url, placement):
    profile = {"name": "Synthetic"}
    if placement == "link":
        profile["links"] = [{"label": "Selected", "href": url}]
    else:
        if placement == "entity-markup":
            url = url.replace("\\", "&#92;")
        profile["summary"] = f'<a href="{url}">Selected</a>'
    source = tmp_path / "selected.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "public-site-source/v1",
                "publication_status": "public",
                "profile": profile,
            }
        )
    )
    destination = tmp_path / "public.json"
    original = b'{"previous":true}\n'
    destination.write_bytes(original)

    with pytest.raises(ValueError, match="public-site-link-invalid"):
        export_public_site(source, destination)

    assert destination.read_bytes() == original


def test_withdrawal_updates_the_snapshot_and_hidden_edits_do_not(tmp_path: Path) -> None:
    selected = {
        "schema_version": "public-site-source/v1",
        "publication_status": "public",
        "profile": {"name": "Synthetic"},
        "knowledge": [
            {
                "visibility": "public",
                "title": "Paper",
                "summary": "Public finding",
                "kind": "Research",
            },
            {"title": "Private draft", "summary": "Private work", "kind": "Draft"},
        ],
    }
    source = tmp_path / "selected.json"
    destination = tmp_path / "public.json"
    source.write_text(json.dumps(selected))
    export_public_site(source, destination)
    original = destination.read_bytes()
    selected["knowledge"][1]["summary"] = "New private notes"
    source.write_text(json.dumps(selected))
    assert export_public_site(source, destination)["changed"] is False
    assert destination.read_bytes() == original
    selected["knowledge"][0]["visibility"] = "private"
    source.write_text(json.dumps(selected))
    assert export_public_site(source, destination)["changed"] is True
    assert json.loads(destination.read_bytes())["knowledge"] == []


def test_export_rejects_linked_destination_and_source_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "selected.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "public-site-source/v1",
                "publication_status": "public",
                "profile": {"name": "Synthetic"},
            }
        )
    )
    original = source.read_bytes()
    linked = tmp_path / "public.json"
    linked.symlink_to(source)
    for target in (linked, source):
        with pytest.raises(ValueError):
            export_public_site(source, target)
        assert source.read_bytes() == original
