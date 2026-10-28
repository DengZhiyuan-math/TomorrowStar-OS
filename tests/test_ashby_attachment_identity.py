"""A server attachment identity cannot prove two different material byte streams."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_ashby_drafts import URL, form

from career_evidence_graph.ashby_drafts import DraftSession


def session(*, same_id=True, same_bytes=False):
    draft = DraftSession({"job_url": URL, "filename": "resume.pdf", "file_sha256": "a" * 64})
    resume = {"id": "resume", "filename": "resume.pdf", "sha256": "a" * 64}
    cover = {
        "id": "cover",
        "filename": "cover-letter.pdf",
        "sha256": "a" * 64 if same_bytes else "b" * 64,
        "draft_path": "cover",
    }
    server = form({"resume": {"id": "attachment-resume", "filename": resume["filename"]}})
    server["sections"][0]["fieldEntries"].append(
        {
            "field": {"path": "cover", "title": "Cover letter"},
            "fieldValue": {
                "id": "attachment-resume" if same_id else "attachment-cover",
                "filename": cover["filename"],
            },
            "isRequired": True,
            "isHidden": False,
        }
    )
    draft._form(server)
    draft.files = {
        "resume": resume | {"attachment_id": "attachment-resume"},
        "cover": cover | {"attachment_id": "attachment-resume" if same_id else "attachment-cover"},
    }
    return draft, resume, cover, server


@pytest.mark.parametrize("same_id,same_bytes", [(True, False), (False, False), (True, True)])
def test_file_readback_rejects_only_proven_cross_path_byte_conflict(same_id, same_bytes):
    draft, resume, cover, _ = session(same_id=same_id, same_bytes=same_bytes)
    expected = not same_id or same_bytes
    assert draft.file_verified({"draft_path": "resume"}, resume) is expected
    assert draft.file_verified({"draft_path": "cover"}, cover) is expected


def test_conflicting_link_keeps_previous_attachment_evidence():
    draft, _, cover, server = session()
    del draft.files["cover"]
    before = deepcopy(draft.files)
    draft.active = {"path": "cover", "material": cover}
    draft.handle = {"handle": "new-cover-upload-handle"}
    request = object()
    draft.pending[request] = ("link", None)
    response = SimpleNamespace(
        request=request, status=200, json=lambda: {"data": {"setFormValueToFile": server}}
    )
    with pytest.raises(ValueError, match="file link mismatch"):
        draft.response(response)
    assert draft.files == before
    assert not draft.linked and not draft.done


def test_same_path_material_version_may_replace_its_previous_identity():
    draft, _, cover, _ = session(same_id=False)
    draft.fields["cover"]["fieldValue"] = {"id": "new-cover-id", "filename": cover["filename"]}
    replacement = cover | {"sha256": "c" * 64}
    draft.files["cover"] = replacement | {"attachment_id": "new-cover-id"}
    assert draft.file_verified({"draft_path": "cover"}, replacement)
