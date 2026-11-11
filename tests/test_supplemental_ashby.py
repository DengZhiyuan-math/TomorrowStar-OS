"""Each Ashby material uses an independent upload handle and server field readback."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_ashby_drafts import QUERIES, UPLOAD, URL, form, setup_service
from test_supplemental_materials import application, selection, source_data
from worker_preview_support import advance_until

from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner


@pytest.mark.worker_browser
@pytest.mark.parametrize(
    "failure", [None, "cover_link_lost", "reuse_resume_handle", "wrong_resume_filename"]
)
def test_ashby_cover_uses_own_handle_and_exact_draft_path(tmp_path, monkeypatch, failure):
    from pathlib import Path

    from playwright.sync_api import Error, sync_playwright

    from career_evidence_graph import application_materials, application_resume

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    monkeypatch.setattr(application_materials, "run_codex_exec", selection)
    monkeypatch.setattr(
        application_resume,
        "export_pdf",
        lambda html, pdf: pdf.write_bytes(
            (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
        ),
    )
    service, initial = setup_service(tmp_path, monkeypatch)
    service.store.material_sources = source_data
    state = service.store.load()
    job = state["jobs"][0]
    app = service.store.applications.get_application(job["application_id"])
    updated = service.store.applications.update_application(
        job["application_id"],
        {"job_description": application()["job_description"]},
        app["revision"],
    )
    job["revision"] = updated["revision"]
    service.store.save(state)
    values, handles, writes = {}, {}, []

    def server_form():
        current = form(values)
        current["sections"][0]["fieldEntries"].append(
            {
                "field": {"path": "cover", "title": "Cover letter"},
                "fieldValue": values.get("cover"),
                "isRequired": True,
                "isHidden": False,
            }
        )
        return current

    html = (
        (
            '<title>Engineer @ Synthetic</title><h1>Engineer</h1><div id="r'
            'oot"></div><script>\n    const queries=QUERIES,init=INITIAL;\n  '
            "  async function call(op,variables){return (await fetch('/api/"
            "non-user-graphql?op='+op,{method:'POST',headers:{'Content-Type"
            "':'application/json'},body:JSON.stringify({operationName:op,qu"
            "ery:queries[op],variables})})).json()}\n    fetch('/api/non-use"
            "r-graphql?op=ApiJobPosting',{method:'POST',headers:{'Content-T"
            "ype':'application/json'},body:init}).then(r=>r.json()).then(()"
            "=>{\n      document.querySelector('#root').innerHTML=`<form><la"
            'bel>Name<input id="name" data-field-path="name" required></lab'
            'el><label>Email<input id="email" data-field-path="email" type='
            '"email" required></label><label>Source<input id="source" data-'
            'field-path="source" required></label><label>Resume<input id="r'
            'esume" data-field-path="resume" type="file" required></label><'
            'label>Cover letter<input id="cover" data-field-path="cover" ty'
            'pe="file" required></label><button type="submit">Submit</butto'
            "n></form>`;\n      const base={organizationHostedJobsPageName:'"
            "synthetic',formRenderIdentifier:'render-one',formDefinitionIde"
            "ntifier:'definition-one'};\n      for(const id of ['name','emai"
            "l','source'])document.getElementById(id).onblur=()=>call('ApiS"
            "etFormValue',{...base,path:id,value:document.getElementById(id"
            ").value});\n      for(const id of ['resume','cover'])document.g"
            "etElementById(id).onchange=async()=>{\n       const file=docume"
            "nt.getElementById(id).files[0];const r=await call('ApiCreateFi"
            "leUploadHandle',{organizationHostedJobsPageName:'synthetic',fi"
            "leUploadContext:'NonUserFormEngine',filename:file.name,content"
            "Type:file.type,contentLength:file.size});const h=r.data.fileUp"
            "loadHandle,data=new FormData();data.append('Content-Type',file"
            ".type);for(const[k,v]of Object.entries(h.fields))data.append(k"
            ",v);data.append('file',file);await fetch(h.url,{method:'POST',"
            "body:data});await call('ApiSetFormValueToFile',{...base,path:i"
            "d,fileHandle:h.handle});\n      };window.finalActions=0;documen"
            "t.querySelector('form').onsubmit=e=>{e.preventDefault();window"
            ".finalActions++};\n    });</script>"
        )
        .replace("QUERIES", json.dumps(QUERIES))
        .replace("INITIAL", json.dumps(initial))
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            start_run(service.store)
            engine = ApplicationRunner(service.store, context)

            def intercept(route):
                def fetch(**options):
                    assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                    request = route.request
                    if request.method == "GET":
                        fields = {"status": 200, "body": html, "content_type": "text/html"}
                    elif request.url == UPLOAD:
                        writes.append(("upload", "bytes"))
                        fields = {"status": 204, "headers": {"access-control-allow-origin": "*"}}
                    else:
                        op = request.post_data_json["operationName"]
                        variables = request.post_data_json["variables"]
                        if op == "ApiJobPosting":
                            result = {
                                "jobPosting": {
                                    "id": URL.split("/")[4],
                                    "title": "Engineer",
                                    "applicationForm": server_form(),
                                }
                            }
                        elif op == "ApiSetFormValue":
                            values[variables["path"]] = {"value": variables["value"]}
                            result = {"setFormValue": server_form()}
                        elif op == "ApiCreateFileUploadHandle":
                            handle = "handle-" + variables["filename"]
                            handles[handle] = variables["filename"]
                            writes.append(("handle", variables["filename"]))
                            result = {
                                "fileUploadHandle": {
                                    "handle": handle,
                                    "url": UPLOAD,
                                    "fields": {"key": handle},
                                }
                            }
                        else:
                            assert op == "ApiSetFormValueToFile"
                            path, handle = variables["path"], variables["fileHandle"]
                            writes.append(("link", path))
                            filename = handles[handle]
                            if failure == "wrong_resume_filename" and path == "resume":
                                filename = "cover-letter.pdf"
                            if failure == "reuse_resume_handle" and path == "cover":
                                # Keep the verified resume intact; corrupt only the
                                # cover's server readback by reusing the other handle.
                                handle = values["resume"]["id"]
                            values[path] = {"id": handle, "filename": filename}
                            if failure == "cover_link_lost" and path == "cover":
                                raise Error("Synthetic cover link response lost")
                            result = {"setFormValueToFile": server_form()}
                        fields = {"status": 200, "json": {"data": result}}
                    return SimpleNamespace(
                        status=fields["status"], fields=fields, dispose=lambda: None
                    )

                wrapper = SimpleNamespace(
                    request=route.request,
                    fetch=fetch,
                    fulfill=lambda *, response: route.fulfill(**response.fields),
                    abort=lambda reason: route.abort(reason),
                )
                engine._live_guard(wrapper)

            context.route("**/*", intercept)
            current = advance_until(
                service,
                engine,
                lambda row: (
                    row["status"] == ("ready_for_review" if failure is None else "needs_recheck")
                ),
            )
            assert current["status"] == (
                "ready_for_review" if failure is None else "needs_recheck"
            ), current
            cover_attempts = 0 if failure == "wrong_resume_filename" else 1
            assert writes.count(("handle", "cover-letter.pdf")) == cover_attempts
            assert writes.count(("link", "cover")) == cover_attempts
            if failure == "reuse_resume_handle":
                draft = engine.drafts[engine.pages[job["application_id"]]]
                assert draft.files["resume"]["sha256"] == job["file_sha256"]
                assert draft.files["resume"]["attachment_id"] == values["resume"]["id"]
                assert "cover" not in draft.files
                assert current["intent"]["action"] == "upload"
                assert current["intent"]["draft_path"] == "cover"
            if failure is None:
                assert writes.count(("handle", "resume.pdf")) == 1
                assert writes.count(("link", "resume")) == 1
                draft = engine.drafts[engine.pages[job["application_id"]]]
                assert set(draft.files) == {"resume", "cover"}
                assert draft.files["resume"]["handle"] != draft.files["cover"]["handle"]
            else:
                before = deepcopy(writes)
                for _ in range(3):
                    engine.tick()
                assert writes == before
            assert engine.pages[job["application_id"]].evaluate("window.finalActions") == 0
        finally:
            browser.close()


@pytest.mark.parametrize("mutation", [None, "resume_id", "resume_sha", "resume_missing"])
def test_required_resume_and_cover_each_need_their_own_current_bytes_and_id(
    tmp_path, monkeypatch, mutation
):
    from career_evidence_graph.ashby_drafts import DraftSession
    from career_evidence_graph.career_portal_data import PortalDataError

    service, _ = setup_service(tmp_path, monkeypatch)
    job = service.store.load()["jobs"][0]
    cover = {
        "id": "cover",
        "filename": "cover-letter.pdf",
        "sha256": "a" * 64,
        "draft_path": "cover",
    }
    job["materials"] = [cover]
    draft = DraftSession(job)
    server_form = form({"resume": {"id": "known-resume", "filename": job["filename"]}})
    server_form["sections"][0]["fieldEntries"] = [
        row
        for row in server_form["sections"][0]["fieldEntries"]
        if row["field"]["path"] == "resume"
    ]
    server_form["sections"][0]["fieldEntries"].append(
        {
            "field": {"path": "cover", "title": "Cover letter"},
            "fieldValue": {"id": "known-cover", "filename": cover["filename"]},
            "isRequired": True,
            "isHidden": False,
        }
    )
    draft._form(server_form)
    draft.uploaded = draft.linked = True
    draft.files = {
        "resume": {
            "id": "resume",
            "filename": job["filename"],
            "sha256": job["file_sha256"],
            "attachment_id": "known-resume",
        },
        "cover": cover | {"attachment_id": "known-cover"},
    }
    observed = {
        "fields": [
            {"draft_path": "resume", "type": "file", "resume": True},
            {"draft_path": "cover", "type": "file", "resume": False},
        ]
    }
    assert draft.verify(observed, [], lambda q, value: value)["server_readback"]
    if mutation == "resume_id":
        draft.fields["resume"]["fieldValue"]["id"] = "foreign-same-filename"
    elif mutation == "resume_sha":
        draft.files["resume"]["sha256"] = cover["sha256"]
    elif mutation == "resume_missing":
        del draft.files["resume"]
    if mutation:
        with pytest.raises(PortalDataError):
            draft.verify(observed, [], lambda q, value: value)
