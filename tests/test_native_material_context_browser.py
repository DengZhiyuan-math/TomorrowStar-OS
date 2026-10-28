"""Material targets retain the prepared control identity without page writes."""

import hashlib

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_assistance_json_browser import json_page as json_page
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page

from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.worker_browser


def test_material_target_uses_prepared_marker_and_retains_zero_limit(json_page):
    service, runner, page, reference, _ = json_page
    page.evaluate(
        """() => {
          const field = document.createElement('textarea');
          field.id = 'employer-letter';
          field.name = 'letter';
          field.setAttribute('aria-label', 'Cover letter');
          field.setAttribute('data-ts-worker-field', 'hosted-17-0');
          field.setAttribute('maxlength', '0');
          const group = document.createElement('section');
          group.setAttribute('data-field-path', 'application.letter');
          group.append(field);
          document.querySelector('form').append(group);
        }"""
    )
    before = page.content()
    checkpoint = service.store.path.read_bytes()

    context = runner.observe_assistance_context(reference)
    field = next(row for row in context["data"]["fields"] if row["id"] == "employer-letter")
    target = field["material_target"]

    assert target["worker_field"] == "hosted-17-0"
    assert target["worker_field"] != target["id"] == "employer-letter"
    assert target["draft_path"] == "application.letter"
    assert target["tag"] == target["type"] == "textarea"
    assert target["max_length"] == 0
    assert target["file_count"] == 0
    assert page.content() == before
    assert service.store.path.read_bytes() == checkpoint
    assert "screenshot" not in context


def test_unprepared_control_has_no_invented_material_marker(json_page):
    _, runner, _, reference, _ = json_page
    context = runner.observe_assistance_context(reference)
    email = next(row for row in context["data"]["fields"] if row["id"] == "email")

    assert email["material_target"]["worker_field"] == ""
    assert email["material_target"]["max_length"] is None
    assert email["value"] == "human@example.invalid"


@pytest.mark.parametrize("attribute,value", [("id", "x" * 201), ("maxlength", "invalid")])
def test_unrepresentable_unrelated_material_target_keeps_ordinary_context(
    json_page, attribute, value
):
    _, runner, page, reference, _ = json_page
    page.evaluate(
        """({attribute,value})=>{
        const field=document.createElement('textarea');
        field.name='unrelated'; field.setAttribute(attribute,value);
        document.querySelector('form').append(field);
    }""",
        {"attribute": attribute, "value": value},
    )

    context = runner.observe_assistance_context(reference)

    assert (
        next(row for row in context["data"]["fields"] if row["id"] == "email")["value"]
        == "human@example.invalid"
    )
    unrelated = next(row for row in context["data"]["fields"] if row["name"] == "unrelated")
    assert "material_target" not in unrelated


def test_owned_material_readback_hashes_actual_file_bytes(json_page, tmp_path):
    _, runner, page, reference, _ = json_page
    page.evaluate("""() => {
        const field=document.createElement('input');
        field.type='file'; field.id='letter-file'; field.name='letter';
        field.setAttribute('aria-label','Cover letter');
        field.setAttribute('data-ts-worker-field','hosted-18-0');
        document.querySelector('form').append(field);
    }""")
    path = tmp_path / "same-name.pdf"
    path.write_bytes(b"Synthetic FileList bytes; not a PDF-format acceptance test.")
    page.locator("#letter-file").set_input_files(path)
    context = runner.observe_assistance_context(reference)

    readback = runner._read_native_material_field(
        reference, "hosted-18-0", document=context["document"]
    )

    assert readback["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert readback["size_bytes"] == path.stat().st_size
    assert readback["filename"] == "same-name.pdf"
    assert readback["field"]["material_target"]["file_count"] == 1
    assert len(page.context.pages) == 1


def test_owned_file_readback_rejects_same_metadata_replacement_during_hash(json_page, tmp_path):
    _, runner, page, reference, _ = json_page
    page.evaluate("""() => {
        const field=document.createElement('input');
        field.type='file'; field.id='letter-race'; field.name='letter';
        field.setAttribute('aria-label','Cover letter');
        field.setAttribute('data-ts-worker-field','hosted-race-0');
        document.querySelector('form').append(field);
    }""")
    path = tmp_path / "same-name.pdf"
    path.write_bytes(b"original bytes")
    page.locator("#letter-race").set_input_files(path)
    context = runner.observe_assistance_context(reference)
    session = page.context.new_cdp_session(page)
    try:
        execution = session.send(
            "Page.createIsolatedWorld",
            {
                "frameId": context["document"]["frame_id"],
                "worldName": "tomorrowstar-material-readback",
            },
        )["executionContextId"]
        # Control only the yield duration. The real WebCrypto digest still hashes
        # the original bytes, while the Page installs a distinct actual File.
        session.send(
            "Runtime.evaluate",
            {
                "contextId": execution,
                "expression": """(() => {
                const original=crypto.subtle.digest.bind(crypto.subtle);
                crypto.subtle.digest=async (...args)=>{
                    document.documentElement.dataset.hashWaiting='yes';
                    await new Promise(resolve=>setTimeout(resolve,100));
                    return original(...args);
                };
            })()""",
            },
        )
        page.evaluate("""() => {
            const timer=setInterval(()=>{
                if(document.documentElement.dataset.hashWaiting!=='yes') return;
                clearInterval(timer);
                const field=document.querySelector('#letter-race'),old=field.files[0];
                const transfer=new DataTransfer();
                transfer.items.add(new File(['replaced bytes'],old.name,{type:old.type}));
                field.files=transfer.files;
                document.documentElement.dataset.fileReplaced='yes';
            },5);
        }""")
        with pytest.raises(PortalDataError, match="回读"):
            runner._read_native_material_field(
                reference, "hosted-race-0", document=context["document"]
            )
        assert page.locator("html").get_attribute("data-file-replaced") == "yes"
    finally:
        session.detach()


def test_yielded_native_session_is_not_used_for_host_material_context(json_page):
    """Host re-observation during a native call must not call the yielded session."""
    from types import SimpleNamespace

    _, runner, _, reference, _ = json_page

    def yielded_owner(*, pump):
        raise PortalDataError("cua_session_yielded", "原生页面权限已交出，脚本不能操作。", 409)

    client = SimpleNamespace(
        handoff_active=True, failed=False, process=SimpleNamespace(poll=lambda: None)
    )
    runner.cua = SimpleNamespace(client=client, observe_owner=yielded_owner)
    context = runner.observe_assistance_context(reference)

    assert context["owner"]["status"] == "yielded"
    assert any(row["id"] == "email" for row in context["data"]["fields"])
