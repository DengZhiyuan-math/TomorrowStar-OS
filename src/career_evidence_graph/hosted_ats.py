"""Bounded reads and native controls for supervised hosted ATS forms."""

from __future__ import annotations

import hashlib
import json
import re
from email import policy
from email.parser import BytesParser
from urllib.parse import parse_qs, urlsplit

from .application_automation import _job_identity
from .ats_forms import FORM_OBSERVATION
from .career_portal_data import PortalDataError

FINAL_OPERATIONS = {
    "submit",
    "submitapplication",
    "submitapplicationform",
    "submitsingleapplicationformaction",
    "apisubmitsingleapplicationformaction",
}
_GRAPHQL_TOKEN = re.compile(
    r"\.\.\.|[A-Za-z_][A-Za-z_0-9]*|-?(?:0|[1-9][0-9]*)"
    r"(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|[!$():=@\[\]{}|&]"
)


def graphql_tokens(query: str) -> list[str] | None:
    """Read bounded syntax, preserving string boundaries without interpreting values.

    GraphQL block strings escape a triple quote with a backslash. A non-greedy
    string regex can mistake that escape for the end and hide an executable field.
    See https://spec.graphql.org/October2021/#sec-String-Value.
    """
    if not isinstance(query, str) or len(query) > 128_000:
        return None
    tokens, index = [], 0
    while index < len(query):
        if query[index] in " \t\r\n,\ufeff":
            index += 1
        elif query[index] == "#":
            while index < len(query) and query[index] not in "\r\n":
                index += 1
        elif query.startswith('"""', index):
            index += 3
            while index < len(query):
                if query.startswith('\\"""', index):
                    index += 4
                elif query.startswith('"""', index):
                    index += 3
                    tokens.append("0")
                    break
                else:
                    index += 1
            else:
                return None
        elif query[index] == '"':
            index += 1
            while index < len(query):
                if query[index] == "\\":
                    index += 2
                elif query[index] == '"':
                    index += 1
                    tokens.append("0")
                    break
                elif query[index] in "\r\n":
                    return None
                else:
                    index += 1
            else:
                return None
        else:
            token = _GRAPHQL_TOKEN.match(query, index)
            if token is None:
                return None
            tokens.append(token[0])
            index += len(token[0])
    return tokens


def graphql_names(query: str) -> set[str]:
    """Inspect names after safely skipping quoted values and comments."""
    tokens = graphql_tokens(query)
    # Invalid/unsupported syntax cannot hide a recognizable final name. Draft
    # admission separately rejects it; this fallback grants no execution.
    if tokens is None:
        return set(re.findall(r"\w+", query))
    names, parentheses = set(), 0
    for index, token in enumerate(tokens):
        if token == "(":
            parentheses += 1
        elif token == ")":
            parentheses -= 1
        elif parentheses == 0 and tokens[index + 1 : index + 2] != [":"]:
            # Aliases and argument/variable names do not execute business fields.
            names.add(token)
    return names


def is_final_submission(request, job: dict | None) -> bool:
    """Recognize known final business operations independently of read/write grants.

    An unrecognized endpoint or persisted GraphQL query remains unknown. This
    predicate never grants dispatch; the runner must still establish its purpose.
    """
    parsed = urlsplit(request.url)
    if job and request.method == "POST":
        target = urlsplit(job["job_url"])
        if job["platform"] == "lever" and (
            parsed.netloc == target.netloc and parsed.path.rstrip("/") == target.path + "/apply"
        ):
            return True
        if job["platform"] == "greenhouse" and (
            parsed.hostname in {"boards.greenhouse.io", "job-boards.greenhouse.io"}
            and parsed.path.rstrip("/") == target.path
        ):
            return True
    payloads = []
    if parsed.query:
        params = parse_qs(parsed.query)
        # Inspect every value: a duplicate query parameter must not hide a final
        # operation behind whichever value the remote framework selects.
        for key in ("operationName", "op", "query"):
            payloads.extend(
                {"operationName" if key == "op" else key: value} for value in params.get(key, [])
            )
    raw = getattr(request, "post_data_buffer", None)
    if isinstance(raw, bytes) and 0 < len(raw) <= 128_000:
        try:
            body = json.loads(raw)
            payloads.extend(body if isinstance(body, list) else [body])
        except (ValueError, UnicodeError):
            pass
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        operation = payload.get("operationName")
        query = payload.get("query")
        names = graphql_names(query) if isinstance(query, str) else set()
        if isinstance(operation, str):
            names.add(operation)
        if any(name.casefold() in FINAL_OPERATIONS for name in names):
            return True
    return False


# Source-owned DOM code. Page content is data, never an instruction or script.
INSPECT_HOSTED = r"""async (generic=false) => {
 const visible = e => Boolean(e.getClientRects().length) &&
   getComputedStyle(e).visibility !== 'hidden';
 const candidates=[...document.querySelectorAll('form,[role=form]')].filter(e=>visible(e) &&
   e.querySelector('input[type=email],input[type=file],[role=tabpanel]'));
 const form = generic ? (candidates.length===1 ? candidates[0] :
   candidates.length===0 && document.querySelectorAll('input[type=email]').length===1 ?
     document.body : null) :
   document.querySelector('form#application-form,form#application_form');
 FORM_OBSERVATION
 const panels=[...form?.querySelectorAll('[role=tabpanel]')||[]];
 const hiddenPanel = p => p.hidden || p.getAttribute('aria-hidden')==='true' || !visible(p);
 const inactive = e => Boolean(e.closest('[role=tabpanel]') &&
   hiddenPanel(e.closest('[role=tabpanel]')));
 const activePanels=panels.filter(p=>!hiddenPanel(p));
 let stage=generic && activePanels.length===1 && activePanels[0].id &&
   [...document.querySelectorAll('[id]')].filter(e=>e.id===activePanels[0].id).length===1 ?
     activePanels[0].id : '';
 const clean = s => (s || '').replace(/[✱*]/g,'').trim().replace(/\s+/g,' ');
 const fieldLabel = e => {
   if(e.labels?.length) return e.labels[0];
   const group=e.closest('fieldset');
   if(group) return group.querySelector('legend,:scope > label');
   for(let parent=e.parentElement, n=0; parent && n<3; parent=parent.parentElement,n++) {
     const labels=parent.querySelectorAll('label');
     if(labels.length===1 && parent.querySelectorAll('input:not([type=hidden]),textarea,select')
       .length===1) return labels[0];
   }
   return null;
 };
 const requiredLabel = e => Boolean(e && (/[✱*]/.test(e.textContent) ||
   /[✱*]/.test(getComputedStyle(e,'::after').content)));
 const label = e => {
   const nativeLabel=(generic ? fieldLabel(e) : e.labels?.[0])?.cloneNode(true);
   nativeLabel?.querySelectorAll('input,textarea,select,button').forEach(control=>control.remove());
   const row = e.closest('.application-question,.file-upload,.select,.checkbox-group,.radio-group');
   const linked = e.getAttribute('aria-labelledby') || row?.getAttribute('aria-labelledby');
   return clean(linked ? linked.split(' ')
     .map(id=>document.getElementById(id)?.textContent||'').join(' ') :
     row?.querySelector('.application-label,.upload-label,legend')?.textContent ||
     (generic ? nativeLabel?.textContent || e.getAttribute('aria-label') :
       nativeLabel?.textContent));
 };
 const stepButtons=generic ? [...form?.querySelectorAll(
   'button,input[type=button],a[rel~=next]')||[]]
   .filter(e=> {
     if(!visible(e) || inactive(e) || e.getAttribute('role')==='combobox') return false;
     const target=panels.find(p=>p.id===e.getAttribute('aria-controls'));
     // An earlier tabpanel is Back. A listbox opener is a field control.
     if(target && stage && panels.indexOf(target)<panels.indexOf(activePanels[0])) return false;
     return Boolean(target) || e.matches('a[rel~=next]') ||
       /^(next|continue|下一步|继续)$/i.test(clean(e.textContent||e.value));
   }) : [];
 let navigation=null;
 let unknownNavigation=generic && panels.length>0 && !stage;
 if(stepButtons.length) {
   const button=stepButtons[0];
   const targetId=button.getAttribute('aria-controls');
   const targets=panels.filter(p=>p.id===targetId);
   const target=targets[0];
   if(stepButtons.length===1 && stage && button.tagName==='BUTTON' &&
     button.getAttribute('type')?.toLowerCase()==='button' && !button.disabled &&
     !button.hasAttribute('formaction') && target && targets.length===1 &&
     panels.indexOf(target)>panels.indexOf(activePanels[0]) && hiddenPanel(target) && targetId &&
     [...document.querySelectorAll('[id]')].filter(e=>e.id===targetId).length===1) {
     const id=button.dataset.tsWorkerNavigation ||
       'hosted-next-'+(window.__tsWorkerNextNavigation=(window.__tsWorkerNextNavigation||0)+1);
     button.dataset.tsWorkerNavigation=id;
     navigation={control_id:id,from_step:stage,to_step:targetId};
   } else if(stepButtons.length===1 && panels.length===0 &&
     button.matches('a[rel~=next]') &&
     /^(next|continue|下一步|继续)$/i.test(clean(button.textContent)) &&
     !button.hasAttribute('download') && !button.hasAttribute('ping') &&
     (!button.target || button.target==='_self')) {
     const id=button.dataset.tsWorkerNavigation ||
       'hosted-next-'+(window.__tsWorkerNextNavigation=(window.__tsWorkerNextNavigation||0)+1);
     button.dataset.tsWorkerNavigation=id;
     stage=location.href;
     navigation={control_id:id,from_step:stage,to_step:button.href};
   } else unknownNavigation=true;
 }
 window.__tsWorkerNextField=Math.max(window.__tsWorkerNextField||0,
   ...[...document.querySelectorAll('[data-ts-worker-field]')].map(e=>
     Number(/^hosted-(\d+)-\d+$/.exec(e.dataset.tsWorkerField)?.[1]||0)));
 const ownedFields=window.__tsWorkerFields || (window.__tsWorkerFields=new WeakMap(
   [...document.querySelectorAll('[data-ts-worker-field]')]
     .map(e=>[e,e.dataset.tsWorkerField])));
 const fileHash=async file => file ? Array.from(new Uint8Array(await crypto.subtle.digest(
   'SHA-256',await file.arrayBuffer())),b=>b.toString(16).padStart(2,'0')).join('') : '';
 const fields=[], validationErrors=[], seen=new Set();
 const coveredLabels=new Set(), coveredControls=new Set();
 const coveredGroups=new Set();
 let ambiguousControl=false;
 for (const e of form?.querySelectorAll('input,textarea,select,button[role=combobox]') || []) {
   if(inactive(e)) continue;
   const buttonCombobox=generic && e.tagName==='BUTTON' && e.getAttribute('role')==='combobox';
   if(buttonCombobox && !e.disabled) {
     const ids=(e.getAttribute('aria-controls')||'').trim().split(/\s+/).filter(Boolean);
     const targets=[...document.querySelectorAll('[id]')].filter(x=>x.id===ids[0]);
     if(e.getAttribute('type')?.toLowerCase()!=='button' || e.hasAttribute('formaction') ||
       !e.hasAttribute('aria-valuetext') || ids.length!==1 || targets.length!==1 ||
       targets[0].getAttribute('role')!=='listbox' ||
       targets[0].getAttribute('aria-multiselectable')==='true') {
       ambiguousControl=true;
       continue;
     }
   }
   const semanticGroup=generic ? e.type==='radio' ? e.closest('[role=radiogroup]') :
     e.type==='checkbox' ? e.closest('[role=checkbox]') : null : null;
   const semanticLabels=(semanticGroup?.getAttribute('aria-labelledby')||'').split(' ')
     .filter(Boolean).map(id=>document.getElementById(id));
   const labeledGroup=semanticGroup && visible(semanticGroup) && semanticLabels.length===1 &&
     semanticLabels[0] && visible(semanticLabels[0]) &&
     Boolean(clean(semanticLabels[0].textContent));
   if (['hidden','submit','button','reset'].includes(e.type) && !buttonCombobox || e.disabled ||
     e.getAttribute('aria-hidden')==='true' && !labeledGroup) continue;
   if (e.type!=='file' && !visible(e)) continue;
   let type=e.tagName==='SELECT'?'select':e.tagName==='TEXTAREA'?'textarea':e.type;
   if(e.getAttribute('role')==='combobox') type='combobox';
   const container=generic && type==='combobox' ? e.closest('[data-ui]') : null;
   const proxyCandidates=container && e.id==='input_'+container.dataset.ui+'_input' ?
     [...container.querySelectorAll(':scope > input[aria-hidden="true"]')]
       .filter(x=>x.name===container.dataset.ui && x.type==='text' && !x.disabled) : [];
   const proxy=proxyCandidates.length===1 ? proxyCandidates[0] : null;
   if(proxyCandidates.length>1 || proxy && coveredControls.has(proxy)) {
     ambiguousControl=true;
     continue;
   }
   const grouped=['radio','checkbox'].includes(type) && e.name;
   const group=grouped ? [...form.querySelectorAll('input')]
     .filter(x=>x.name===e.name && x.type===e.type && !inactive(x)) : [e];
   if(generic && grouped && group.some(x=>x.closest(
     type==='radio' ? '[role=radiogroup]' : '[role=checkbox]')!==semanticGroup)) {
     ambiguousControl=true;
     continue;
   }
   if(grouped && seen.has(e.name)) continue;
   if(grouped) seen.add(e.name);
   if(group.some(x=>x.dataset.tsWorkerField &&
     ownedFields.get(x)!==x.dataset.tsWorkerField)) {
     ambiguousControl=true;
     continue;
   }
   group.forEach(x=>{if(ownedFields.has(x)) x.dataset.tsWorkerField=ownedFields.get(x);});
   const priorIds=group.map(x=>x.dataset.tsWorkerField).filter(Boolean);
   const priorPrefixes=new Set(priorIds.map(id=>id.replace(/-\d+$/,'')));
   if(priorPrefixes.size>1 || priorIds.some(id=> !/^hosted-\d+-\d+$/.test(id) ||
     [...document.querySelectorAll('[data-ts-worker-field]')]
       .filter(x=>x.dataset.tsWorkerField===id).length!==1)) {
     ambiguousControl=true;
     continue;
   }
   const id=priorPrefixes.size ? [...priorPrefixes][0] :
     'hosted-'+(window.__tsWorkerNextField=(window.__tsWorkerNextField||0)+1);
   let question=label(e);
   const groupLabel=labeledGroup ? semanticLabels[0] :
     e.closest('fieldset')?.querySelector('legend,:scope > label');
   if(grouped) question=clean(e.getAttribute('description') ||
     groupLabel?.textContent || question);
   if(generic && e.type==='file' && !question && !e.required) continue;
   let nextSlot=Math.max(-1,...priorIds.map(value=>Number(value.split('-').at(-1))))+1;
   group.forEach(x=>{
     if(!x.dataset.tsWorkerField) x.dataset.tsWorkerField=id+'-'+nextSlot++;
     ownedFields.set(x,x.dataset.tsWorkerField);
   });
   group.forEach(x=>coveredControls.add(x));
   if(labeledGroup && grouped) coveredGroups.add(semanticGroup);
   if(proxy) coveredControls.add(proxy);
   coveredLabels.add(fieldLabel(e));
   if(grouped) coveredLabels.add(groupLabel);
   for(const labelId of (e.getAttribute('aria-labelledby')||'').split(' '))
     coveredLabels.add(document.getElementById(labelId));
   if(/^(eeo\[|surveysResponses\[)/.test(e.name)) question='Disclosure: '+question;
   const row=e.closest('.application-question,.file-upload,.select');
   const required=group.some(x=>x.required||x.getAttribute('aria-required')==='true') ||
     proxy?.required || proxy?.getAttribute('aria-required')==='true' ||
     labeledGroup && (semanticGroup.getAttribute('aria-required')==='true' ||
       requiredLabel(semanticGroup)) ||
     row?.getAttribute('aria-required')==='true' || /[✱*]/.test(e.labels?.[0]?.textContent ||
       row?.querySelector('.application-label')?.textContent || '') ||
     generic && (requiredLabel(grouped ? groupLabel : fieldLabel(e)) ||
       (e.getAttribute('aria-labelledby')||'').split(' ')
         .some(id=>requiredLabel(document.getElementById(id))));
   const selected=e.closest('.select')?.querySelector('.select__single-value');
   const options=type==='select' ? [...e.options]
     .filter(o=>o.value && !o.disabled).map(o=>o.text.trim()) :
     grouped ? group.map(x=>clean(x.labels?.[0]?.textContent)||x.value) : [];
   const value=type==='select' ? (e.selectedOptions[0]?.value?e.selectedOptions[0].text.trim():'') :
     type==='combobox' ? clean(buttonCombobox ? e.getAttribute('aria-valuetext') :
       selected?.textContent ||
       e.closest('.select')?.querySelector('[class*="singleValue"]')?.textContent ||
       (generic && e.getAttribute('aria-expanded')==='false' ? e.value : '')) :
     grouped ? group.filter(x=>x.checked)
       .map(x=>clean(x.labels?.[0]?.textContent)||x.value).join(' | ') : e.value;
   const file=e.type==='file'?e.files[0]:null;
   const sha=await fileHash(file);
   group.forEach(x=>associatedErrors(x).forEach(message=>
     validationErrors.push({id,message})));
   fields.push({id,control_ids:group.map(x=>x.dataset.tsWorkerField),type,question,required:Boolean(required),options,value,file_sha256:sha,
     draft_path:e.closest('[data-field-path]')?.dataset.fieldPath||'',
     valid:grouped ? !required||group.some(x=>x.checked) :
       type==='combobox' ? (!required||Boolean(value)) && (!proxy||proxy.checkValidity()) :
         e.checkValidity(),
     multiple:Boolean(type==='checkbox' && group.length>1 || e.multiple ||
       e.closest('.select')?.querySelector('.select__multi-value')),
     filename:e.type==='file'?e.files[0]?.name||'':'',
     resume:e.type==='file'&&(e.name==='resume'||e.id==='resume'||
       generic && /\b(resume|cv|curriculum vitae)\b|简历/i.test(question)),
     remote_upload:e.type==='file'&&e.closest('.file-upload')?.dataset.allowS3==='true'});
 }
 for(const group of form?.querySelectorAll('.file-upload')||[]) {
   if(inactive(group)) continue;
   if(group.querySelector('input[type=file]')) continue;
   const filename=clean(group.querySelector('.file-upload__filename')?.textContent);
   if(!filename) continue;
   const labelId=group.getAttribute('aria-labelledby');
   let marker=ownedFields.get(group);
   if(group.dataset.tsWorkerField && group.dataset.tsWorkerField!==marker || marker &&
     (!/^hosted-\d+-\d+$/.test(marker) ||
       [...document.querySelectorAll('[data-ts-worker-field]')]
         .filter(e=>e.dataset.tsWorkerField===marker).length>1)) {
     ambiguousControl=true;
     continue;
   }
   if(!marker) marker='hosted-'+(++window.__tsWorkerNextField)+'-0';
   group.dataset.tsWorkerField=marker;
   ownedFields.set(group,marker);
   fields.push({id:marker.replace(/-\d+$/,''),control_ids:[marker],type:'file',question:clean(
     document.getElementById(labelId)?.textContent),required:group.ariaRequired==='true',
     options:[],value:'',valid:true,multiple:false,filename,file_sha256:'',
     resume:labelId==='upload-label-resume',remote_upload:group.dataset.allowS3==='true'});
 }
 const resumeInputs=[...form?.querySelectorAll('input[type=file]')||[]].filter(e=>
   e.name==='resume'||e.id==='resume'||generic &&
     /\b(resume|cv|curriculum vitae)\b|简历/i.test(label(e)));
 const retainedResume=stage ? await Promise.all(resumeInputs.filter(inactive).map(async e=>{
   const file=e.files[0];
   const sha=await fileHash(file);
   return {filename:file?.name||'',file_sha256:sha,
     valid:e.isConnected && !e.disabled && e.files[0]===file && e.checkValidity(),
     multiple:Boolean(e.multiple || e.files.length>1)};
 })) : [];
 return {title:document.title,stage,navigation,resume_count:resumeInputs.length,
   document_token:documentToken,user_activity:{...activity.fields},
   parser:parserObservation(form),validation_errors:validationErrors,
   retained_resume:retainedResume,
   remote_resume:resumeInputs.some(e=>e.closest('.file-upload')?.dataset.allowS3==='true'),
   unknown_navigation:unknownNavigation,
   role:clean(document.querySelector('h1,.posting-headline h2')?.textContent),fields,
   unsupported:ambiguousControl || generic && ([...form?.querySelectorAll('label,legend')||[]]
     .some(e=>visible(e) && !inactive(e) && requiredLabel(e) && !coveredLabels.has(e)) ||
     [...form?.querySelectorAll('input,textarea,select,button[role=combobox]')||[]].some(e=>
       !inactive(e) && e.type!=='hidden' && !e.disabled &&
       (e.required||e.getAttribute('aria-required')==='true') &&
       !coveredControls.has(e)) || [...form?.querySelectorAll(
         '[role=checkbox],[role=radiogroup]')||[]].some(e=>visible(e) && !inactive(e) &&
           (e.getAttribute('aria-required')==='true'||requiredLabel(e)) && !coveredGroups.has(e))),
   challenge:[...document.querySelectorAll('input[type=password],input[autocomplete="one-time-code"],'+
     'iframe[title*="challenge" i],iframe[title*="captcha" i]')]
     .some(visible)};
}""".replace("FORM_OBSERVATION", FORM_OBSERVATION)


def page_url(job: dict) -> str:
    return job["job_url"] + ("/apply" if job["platform"] == "lever" else "")


def matches_page(url: str, job: dict, *, document_url: str | None = None) -> bool:
    if document_url is not None:
        return url == document_url and document_step_target(job["job_url"], document_url, job)
    try:
        platform, normalized = _job_identity(url, allow_generic=job["platform"] == "generic")
    except PortalDataError:
        return False
    if platform == "generic":
        return normalized == job["job_url"]
    expected = urlsplit(job["job_url"])
    actual = urlsplit(normalized)
    return (
        platform == job["platform"]
        and actual.path == expected.path
        and (platform == "greenhouse" or actual.hostname == expected.hostname)
    )


def document_step_target(source: str, target: str, job: dict) -> bool:
    """Keep an explicit document step inside the same original query-bound job."""
    original, before, after = map(urlsplit, (job["job_url"], source, target))
    original_query = parse_qs(original.query, keep_blank_values=True)
    after_query = parse_qs(after.query, keep_blank_values=True)
    steps = {key: value for key, value in after_query.items() if key not in original_query}
    return bool(
        job["platform"] == "generic"
        and after.scheme == before.scheme == original.scheme == "https"
        and after.netloc == before.netloc == original.netloc
        and after.path == before.path == original.path
        and not after.fragment
        and after != before
        and original_query
        and all(after_query.get(key) == value for key, value in original_query.items())
        and steps
        and set(steps) <= {"step", "stage", "page"}
        and all(
            len(values) == 1
            and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", values[0])
            and re.sub(r"[^a-z]", "", values[0].casefold())
            not in FINAL_OPERATIONS | {"apply", "finish", "complete", "confirm"}
            for values in steps.values()
        )
    )


def observe(page, job: dict, *, document_url: str | None = None) -> dict:
    if page.is_closed() or not matches_page(page.url, job, document_url=document_url):
        raise PortalDataError("page_changed", "页面跳转或岗位来源已变更。", 409)
    result = page.evaluate(INSPECT_HOSTED, job["platform"] == "generic")
    navigation = result.get("navigation")
    if (
        navigation
        and navigation["from_step"].startswith("https://")
        and not document_step_target(navigation["from_step"], navigation["to_step"], job)
    ):
        raise PortalDataError("navigation_changed", "下一步已离开原岗位，请核验原页。", 409)
    if result["challenge"]:
        raise PortalDataError("user_authentication", "请在可见浏览器处理登录或验证。", 409)
    expected_title = (
        f"{job['company']} - {job['role_title']}"
        if job["platform"] == "lever"
        else f"Job Application for {job['role_title']} at {job['company']}"
    )

    def normalize(text):
        return " ".join(text.split()).casefold()

    identity_matches = (
        normalize(result["role"]) == normalize(job["role_title"])
        and normalize(job["company"]) in normalize(result["title"])
        if job["platform"] == "generic"
        else normalize(result["title"]) == normalize(expected_title)
        and (not result["role"] or normalize(result["role"]) == normalize(job["role_title"]))
    )
    if not identity_matches:
        raise PortalDataError("identity_changed", "真实页面的公司或岗位需要核验。", 409)
    fields = result["fields"]
    if (
        result.get("unsupported")
        or result.get("unknown_navigation")
        or not fields
        and not result.get("stage")
        or any(not q["question"] for q in fields)
    ):
        raise PortalDataError("unsupported_structure", "真实表单标签需要人工核验。", 409)
    files = [q for q in fields if q["type"] == "file" and q["resume"]]
    if (
        result.get("stage")
        and (result["resume_count"] > 1 or result["remote_resume"])
        or not result.get("stage")
        and (len(files) != 1 or files[0]["remote_upload"])
    ):
        raise PortalDataError("unsupported_attachments", "此附件发送路径尚未验证。", 409)
    return result


def control(page, question: dict, index: int = 0):
    identifiers = question.get("control_ids")
    identifier = identifiers[index] if identifiers else f"{question['id']}-{index}"
    return page.locator(f'[data-ts-worker-field="{identifier}"]')


def fill(page, question: dict, value: str) -> None:
    if question.get("multiple") or (
        question["type"] == "checkbox" and len(question["options"]) > 1
    ):
        raise PortalDataError("unsupported_structure", "多选控件需要人工核验。", 409)
    field = control(page, question)
    if question["type"] == "select":
        field.select_option(label=value)
    elif question["type"] == "combobox":
        field.click()
        field.fill(value)
        option = page.get_by_role("option", name=value, exact=True)
        option.wait_for(state="visible", timeout=5000)
        if option.count() != 1:
            raise PortalDataError("ambiguous_option", "选项不唯一，请人工选择。", 409)
        option.click()
    elif question["type"] in {"radio", "checkbox"}:
        for i, label in enumerate(question["options"]):
            item = control(page, question, i)
            if label == value:
                item.check()
            elif question["type"] == "checkbox":
                item.uncheck()
    elif question["type"] in {"text", "email", "tel", "url", "number", "date", "textarea"}:
        field.fill(value)
    else:
        raise PortalDataError("unsupported_control", "此控件需要人工处理。", 409)


def multipart_parts(request) -> list:
    content_type = request.headers.get("content-type", "")
    raw = request.post_data_buffer
    if not content_type.startswith("multipart/form-data;") or raw is None or len(raw) > 720_000:
        return []
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + raw
    )
    return list(message.iter_parts()) if message.is_multipart() and not message.defects else []


def is_resume_parse(request, job: dict) -> bool:
    """Recognize native resume parsing and verify the selected PDF, without grants."""
    parsed, expected = urlsplit(request.url), urlsplit(job["job_url"])
    if (
        job["platform"] != "lever"
        or request.method != "POST"
        or parsed.scheme != "https"
        or parsed.netloc != expected.netloc
        or parsed.path != "/parseResume"
        or parsed.query
    ):
        return False
    parts = multipart_parts(request)
    names = [part.get_param("name", header="content-disposition") for part in parts]
    if len(names) != 2 or set(names) != {"accountId", "resume"}:
        return False
    account = parts[names.index("accountId")]
    raw_account = account.get_payload(decode=True)
    if (
        len(account.items()) != 1
        or account.get_params(header="content-disposition")
        != [("form-data", ""), ("name", "accountId")]
        or not isinstance(raw_account, bytes)
        or not re.fullmatch(rb"[A-Za-z0-9_.-]{1,256}", raw_account)
    ):
        return False
    resume = parts[names.index("resume")]
    body = resume.get_payload(decode=True)
    return body is not None and hashlib.sha256(body).hexdigest() == job["file_sha256"]


def allows_read(request, jobs: list[dict]) -> bool:
    """Identify candidate public reads; the runner binds discovery to an owned open intent."""
    parsed = urlsplit(request.url)
    if request.method != "GET" or parsed.scheme != "https":
        return False
    if request.is_navigation_request():
        return any(
            (job["platform"] == "generic" or not parsed.query)
            and matches_page(
                parsed._replace(fragment="").geturl(),
                {**job, "job_url": urlsplit(job["job_url"])._replace(fragment="").geturl()},
            )
            for job in jobs
        )
    # These domains alone never authorize a request after answers have been entered.
    return (
        request.resource_type in {"script", "stylesheet", "image", "font"}
        and parsed.hostname
        in {
            "job-boards.cdn.greenhouse.io",
            "boards.cdn.greenhouse.io",
            "recruiting.cdn.greenhouse.io",
            "js.hcaptcha.com",
            "www.gstatic.com",
            "www.recaptcha.net",
        }
    ) or parsed.hostname in {
        "jobs.lever.co",
        "jobs.eu.lever.co",
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
    }
