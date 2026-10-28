"""Fixed selectors and paths for the two isolated ATS preview forms."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .application_automation import _job_identity
from .career_portal_data import PortalDataError

# Shared, source-owned observation only. Unrelated alerts are not field errors.
FORM_OBSERVATION = r"""
 const documentToken = window.__tomorrowstarMaterialDocument ||
   (window.__tomorrowstarMaterialDocument = crypto.randomUUID());
 const activity=window.__tsWorkerFormActivity ||
   (window.__tsWorkerFormActivity={sequence:0,fields:{}});
 if(!activity.listening) {
   activity.listening=true;
   for(const kind of ['input','change']) document.addEventListener(kind,event=>{
     const e=event.target;
     if(!event.isTrusted || !e?.matches?.('input,textarea,select')) return;
     const pending=activity.pendingInputs || (activity.pendingInputs=new WeakMap());
     if(kind==='change' && pending.has(e) && pending.get(e)===e.value) {
       pending.delete(e);
       return;
     }
     if(kind==='input') pending.set(e,e.value);
     else pending.delete(e);
     const key=e.dataset.tsWorkerField?.replace(/-\d+$/,'') || e.id || e.name;
     if(key) activity.fields[key]=++activity.sequence;
   },true);
 }
 const observationVisible = e => Boolean(e && e.getClientRects().length) &&
   getComputedStyle(e).visibility !== 'hidden';
 const parserObservation = (form, upload=null) => {
   const marked=[form,...form?.querySelectorAll('[data-parser-state]')||[],upload]
     .filter(e=>observationVisible(e));
   const declared=marked.map(e=>e.dataset.parserState).filter(Boolean);
   const failure=[...document.querySelectorAll('.resume-upload-failure')]
     .some(observationVisible);
   const working=[...document.querySelectorAll('.resume-upload-working')]
     .some(observationVisible);
   if(failure || declared.some(v=>['failed','failure','error'].includes(v)))
     return {status:'failed',signal:failure?'lever-failure':'declared-failure'};
   if(working || form?.getAttribute('aria-busy')==='true' ||
     declared.some(v=>['active','working','pending','parsing','uploading'].includes(v)))
     return {status:'active',signal:working?'lever-working':
       form?.getAttribute('aria-busy')==='true'?'form-aria-busy':'declared-active'};
   if(declared.some(v=>['complete','completed','success'].includes(v)))
     return {status:'complete',signal:'declared-complete'};
   return {status:'unknown',signal:'no-parser-signal'};
 };
 const associatedErrors = e => {
   if(!observationVisible(e)) return [];
   const explicit=e.getAttribute('aria-errormessage');
   const ids=(explicit||e.getAttribute('aria-describedby')||'')
     .split(/\s+/).filter(Boolean);
   return ids.flatMap(id=> {
     const nodes=[...document.querySelectorAll('[id]')].filter(node=>node.id===id);
     if(nodes.length!==1 || !observationVisible(nodes[0]) || !explicit &&
       !nodes[0].matches('[role=alert],[data-error],.error,.field-error,.error-message')) return [];
     const message=(nodes[0].textContent||'').trim().replace(/\s+/g,' ');
     return message?[message]:[];
   });
 };
"""


@dataclass(frozen=True)
class ATSForm:
    platform: str
    selector: str
    row: str
    label: str
    upload_status: str

    def page_path(self, identifier: str) -> str:
        return f"/{self.platform}/{identifier}"

    def upload_path(self, identifier: str) -> str:
        prefix = "" if self.platform == "lever" else "/greenhouse"
        return f"{prefix}/upload/{identifier}"

    def submit_path(self, identifier: str) -> str:
        prefix = "" if self.platform == "lever" else "/greenhouse"
        return f"{prefix}/submit/{identifier}"

    def inspect_script(self) -> str:
        # Only these source-owned constants become script parameters.
        selectors = json.dumps(
            {
                "form": self.selector,
                "row": self.row,
                "label": self.label,
                "upload": self.upload_status,
            }
        )
        return """() => {
 const s = SELECTORS, form = document.querySelector(s.form);
 FORM_OBSERVATION
 return {
 document_token:documentToken,user_activity:{...activity.fields},
 parser:parserObservation(form,document.querySelector(s.upload)),
 validation_errors:form ? [...form.querySelectorAll('input,textarea,select')]
   .flatMap(e=>associatedErrors(e).map(message=>({id:e.id,message}))) : [],
 identity: Object.fromEntries(['company','role','jobUrl'].map(k =>
   [k, document.querySelector('main')?.dataset[k]])),
 fields: form ? [...form.querySelectorAll('input:not([type=hidden]),textarea,select')].map(e => ({
 id:e.id, type:e.tagName==='SELECT'?'select':e.type||'text', multiple:Boolean(e.multiple),
 question:(e.labels?.[0]?.textContent ||
   e.closest(s.row)?.querySelector(s.label)?.textContent || '')
   .trim().replace(/\\s*\\*$/, ''),
 required:e.required || /\\*/.test(e.labels?.[0]?.textContent || ''),
 options:e.tagName==='SELECT'?[...e.options].filter(o=>o.value).map(o=>o.text.trim()):[],
 value:e.tagName==='SELECT'?(e.selectedOptions[0]?.value ?
   e.selectedOptions[0].text.trim():''):e.value,
 filename:e.type==='file'?e.files[0]?.name||'':'', valid:e.checkValidity()
 })) : [],
 upload:Object.assign({}, document.querySelector(s.upload)?.dataset)
 };
}""".replace("SELECTORS", selectors).replace("FORM_OBSERVATION", FORM_OBSERVATION)


FORMS = {
    "lever": ATSForm(
        "lever",
        "form.application-form",
        ".application-question",
        ".application-label",
        "#upload-status",
    ),
    "greenhouse": ATSForm(
        "greenhouse", "form#application_form", ".field", "label", "#resume_upload_status"
    ),
}


def form_for(job: dict) -> ATSForm:
    platform, _ = _job_identity(job["job_url"])
    if job.get("platform", platform) != platform:
        raise PortalDataError("platform_changed", "岗位平台身份已变更。", 409)
    return FORMS[platform]
