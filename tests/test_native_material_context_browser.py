"""Material targets retain the prepared control identity without page writes."""

import hashlib
import json

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


def test_filename_shown_finds_the_relocated_form_item_or_its_form(json_page, capsys):
    """r12: a re-rendered upload widget unmounts its input; the ledger's stable
    identity finds the new item, else the form shows the name."""
    _, runner, page, reference, _ = json_page
    page.evaluate(
        """() => {
          const form = document.querySelector('form');
          const old = document.createElement('div');
          old.id = 'cv-form-item';
          const input = document.createElement('input');
          input.type = 'file';
          old.append(input);
          form.append(old);
          // The widget re-renders: the same id, a new element, no file input.
          old.remove();
          const item = document.createElement('div');
          item.id = 'cv-form-item';
          item.textContent = '  Jane_Doe   CV.PDF  ';
          form.append(item);
          const group = document.createElement('div');
          group.setAttribute('data-field-path', 'application.letter');
          group.textContent = 'letter.pdf';
          form.append(group);
          const other = document.createElement('input');
          other.type = 'file';
          form.append(other);
          const note = document.createElement('p');
          note.textContent = 'shown-in-form.pdf';
          form.append(note);
          const elsewhere = document.createElement('p');
          elsewhere.textContent = 'outside.pdf';
          document.body.prepend(elsewhere);
        }"""
    )
    document = runner.observe_assistance_context(reference)["document"]
    before = page.content()
    item = {"id": "cv-form-item", "draft_path": ""}
    capsys.readouterr()

    def scope(filename, target):
        result = runner._native_filename_shown(page, filename, document=document, target=target)
        line = capsys.readouterr().out.strip().splitlines()[-1]
        assert line.startswith("native_filename_shown: ")
        assert json.loads(line.removeprefix("native_filename_shown: ")) == result
        assert set(result) == {"shown", "scope", "error"} and result["error"] is False
        return result["scope"] if result["shown"] else None

    assert scope("jane_doe cv.pdf", item) == "container"
    assert scope("letter.pdf", {"id": "", "draft_path": "application.letter"}) == "container"
    # Only the form shows it: through the found item, or with no item at all.
    assert scope("shown-in-form.pdf", item) == "form"
    assert scope("shown-in-form.pdf", {"id": "gone", "draft_path": ""}) == "form"
    assert scope("shown-in-form.pdf", None) == "form"
    # Outside the form, absent, or on another document: not shown.
    assert scope("outside.pdf", item) is None
    assert scope("missing.pdf", item) is None
    other = dict(document, loader_id="other")
    assert runner._native_filename_shown(page, "jane_doe cv.pdf", document=other, target=item) == {
        "shown": False,
        "scope": "",
        "error": False,
    }
    assert page.content() == before


def test_filename_shown_reports_an_upload_error_in_its_scope(json_page):
    """2026-11-03: the name stood above "That didn't work. Please try again."."""
    _, runner, page, reference, _ = json_page
    page.evaluate(
        """() => {
          const form = document.querySelector('form');
          const item = document.createElement('div');
          item.id = 'cv-form-item';
          item.append('resume.pdf 27.25 KB');
          const alert = document.createElement('p');
          alert.setAttribute('role', 'alert');
          alert.textContent = "That didn't work. Please try again.";
          item.append(alert);
          form.append(item);
          const quiet = document.createElement('div');
          quiet.id = 'letter-form-item';
          quiet.append('letter.pdf');
          const live = document.createElement('div');
          live.setAttribute('aria-live', 'polite');
          quiet.append(live);
          form.append(quiet);
        }"""
    )
    document = runner.observe_assistance_context(reference)["document"]

    def read(filename, identifier):
        return runner._native_filename_shown(
            page, filename, document=document, target={"id": identifier, "draft_path": ""}
        )

    assert read("resume.pdf", "cv-form-item") == {
        "shown": True,
        "scope": "container",
        "error": True,
    }
    # An empty live region is no error.
    assert read("letter.pdf", "letter-form-item") == {
        "shown": True,
        "scope": "container",
        "error": False,
    }


def test_context_names_each_controls_form_item_and_hidden_twin(json_page):
    """A Radix combobox and its aria-hidden native select share one form item id."""
    _, runner, page, reference, _ = json_page
    page.evaluate(
        """() => {
          const item = document.createElement('div');
          item.id = 'title-form-item';
          const button = document.createElement('button');
          button.type = 'button';
          button.id = 'title-trigger';
          button.setAttribute('role', 'combobox');
          button.setAttribute('aria-label', 'Salutation');
          button.textContent = 'Select title...';
          const twin = document.createElement('select');
          twin.name = 'title';
          twin.setAttribute('aria-hidden', 'true');
          twin.append(new Option('Mr', 'mr'));
          const wrap = document.createElement('span');
          wrap.append(twin);
          item.append(button, wrap);
          document.querySelector('form').append(item);
        }"""
    )
    fields = runner.observe_assistance_context(reference)["data"]["fields"]
    combobox = next(row for row in fields if row["id"] == "title-trigger")
    twin = next(row for row in fields if row["name"] == "title")
    assert combobox["container_id"] == twin["container_id"] == "title-form-item"
    assert combobox["hidden"] is False and twin["hidden"] is True
    assert all(
        isinstance(row["container_id"], str) and type(row["hidden"]) is bool for row in fields
    )


def test_a_nested_release_does_not_shorten_the_context_read(json_page, monkeypatch):
    # 2026-11-05: Hexagon and BCG timed out after the document check, whose 1 s
    # release had left the whole 5 s session at 1 s; the owner and page checks after
    # it are native driver reads, together more than a second.
    import time

    _service, runner, _page, reference, _ = json_page
    original = runner._assistance_page_checker

    def slow(assistance_ref, *, after_stop=False):
        page, check = original(assistance_ref, after_stop=after_stop)

        def slow_check():
            time.sleep(1.1)
            return check()

        return page, slow_check

    monkeypatch.setattr(runner, "_assistance_page_checker", slow)
    context = runner.observe_assistance_context(reference)
    assert context["status"] == "captured" and context["data"]["fields"]
