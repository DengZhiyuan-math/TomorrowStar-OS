"""Fixed DOM reads for an owned Page; no selectors or code supplied by page text."""

INSPECT = r"""() => {
 const trim = (s,n=4000) => String(s??'').slice(0,n);
 const controls = [...document.querySelectorAll(
   'input,textarea,select,[role=combobox],[role=checkbox],[role=radio]')];
 if(controls.length>500) throw Error('observation_field_limit');
 const fields=controls.filter(e=>!['hidden','submit','button','reset'].includes(e.type)).map(e=>{
   const type=e.type||e.getAttribute('role')||e.tagName.toLowerCase();
   const password=type==='password';
   const files=type==='file' ? [...e.files] : [];
   if(files.length>20) throw Error('observation_file_limit');
   return {
     id:trim(e.id,200), name:trim(e.name,200), type,
     label:trim([...e.labels||[]].map(x=>x.textContent).join(' ')||
       e.getAttribute('aria-label')||(e.getAttribute('aria-labelledby')||'').split(/\s+/)
         .map(id=>document.getElementById(id)?.textContent||'').join(' '),1000),
     value:password?'':trim(type==='checkbox'||type==='radio' ? e.checked :
       e.value ?? e.getAttribute('aria-valuetext') ?? e.getAttribute('aria-checked')),
     redacted:password, required:Boolean(e.required||e.getAttribute('aria-required')==='true'),
     disabled:Boolean(e.disabled), readonly:Boolean(e.readOnly),
     valid:e.validity ? e.validity.valid : null,
     aria_invalid:e.getAttribute('aria-invalid'),
     visible:Boolean(e.getClientRects().length)&&getComputedStyle(e).visibility!=='hidden',
     files:files.map(f=>({name:trim(f.name,500),size:f.size,type:trim(f.type,200)}))
   };
 });
 const attachments=[...document.querySelectorAll('.file-upload__filename')]
   .filter(e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden')
   .slice(0,100).map(e=>({name:trim(e.textContent,1000),source:'visible_filename'}));
 return {url:location.href,title:trim(document.title,1000),fields,attachments,
   remote_save_verified:false};
}"""
