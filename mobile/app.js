import {openStore,getState,deviceIdentity,allDrafts,writeDraft,commit,emptyPacket,makeCapture,validate,merge,exportSelection,matching,MAX_HANDOFF} from "./store.js";

const $=id=>document.getElementById(id);
let db,library=emptyPacket(),kind="all",visible=[],original=null,pendingImport=null,importSerial=0;
let revision=0,draftQueue=Promise.resolve(),recoveredDraft=null,starting=false,ready=false,localDevice="";
// Each document owns its draft. Cloning a tab must not clone its writer identity.
const draftId="draft:"+crypto.randomUUID();
const fields=()=>({body:$("body").value,category:$("category").value,tags:$("tags").value});
function notice(value,error=false,target="message") {$(target).textContent=value;$(target).dataset.error=String(error);}
function openDialog(id,trigger) {const dialog=$(id);dialog.returnFocus=trigger || document.activeElement;dialog.showModal();}
for(const button of document.querySelectorAll("[data-close]")) button.onclick=()=>$(button.dataset.close).close();
for(const dialog of document.querySelectorAll("dialog")) dialog.addEventListener("close",()=>dialog.returnFocus?.isConnected && dialog.returnFocus.focus({preventScroll:true}));
$("connection").onclick=event=>openDialog("connection-dialog",event.currentTarget);
$("how").onclick=event=>openDialog("connection-dialog",event.currentTarget);
$("transfer").onclick=event=>{openDialog("transfer-dialog",event.currentTarget);$("export").textContent="Export "+visible.length+" matching originals";};

function persistDraft(snapshot=fields(),version=revision) {
  if(!db) return Promise.reject(Error("Local storage is not ready. Keep this window open and copy your text."));
  draftQueue=draftQueue.catch(()=>{}).then(()=>writeDraft(db,draftId,snapshot,version));
  draftQueue.then(()=>{if(revision===version) $("draft-status").textContent=snapshot.body.trim() ? "Draft saved on this device" : "Stored here when you save.";},error=>{if(revision===version){$("draft-status").textContent="Draft not stored";notice(error.message,true);}});
  return draftQueue;
}
for(const id of ["body","category","tags"]) $(id).addEventListener("input",()=>{revision++;$("draft-status").textContent="Storing draft…";persistDraft().catch(()=>{});});
$("paste").onclick=async()=>{
  const field=$("body"),before=field.value,version=revision;
  try {
    if(!navigator.clipboard?.readText) throw Error("Clipboard reading is unavailable here. Long-press the composer and paste instead.");
    const value=await navigator.clipboard.readText();
    if(revision!==version || field.value!==before) {notice("Your draft changed while paste was pending. Paste again when ready.",true);return;}
    if(!value) {notice("The clipboard is empty or paste permission was denied. You can paste manually.",true);return;}
    if(value.length>100000) throw Error("This clipboard text exceeds 100,000 characters. Save a smaller selection; your draft is unchanged.");
    field.value=before ? before+"\n"+value : value;
    if(field.value.length>100000) {field.value=before;throw Error("The combined draft exceeds 100,000 characters. Save the current draft first.");}
    revision++;await persistDraft();field.focus();notice("Pasted into your draft. Keep it when ready.");
  } catch(error) {notice(error.message || "Paste permission was denied. Long-press the composer to paste.",true);field.focus();}
};
$("capture-form").onsubmit=async event=>{
  event.preventDefault();if(!ready || $("save").disabled) return;
  const snapshot=fields(),version=revision,button=$("save");button.disabled=true;button.textContent="Keeping…";
  try {
    const packet=makeCapture(snapshot.body,snapshot.category,snapshot.tags,localDevice);
    await persistDraft(snapshot,version);
    const cleanup=[{id:draftId,revision:version},...(recoveredDraft ? [recoveredDraft] : [])];
    library=await commit(db,packet,cleanup);recoveredDraft=null;
    if(revision===version) {$("body").value="";$("tags").value="";revision++;$("draft-status").textContent="Original saved on this device";}
    render();notice(revision===version+1 ? "Original kept locally. Export a second copy when you want to carry it forward." : "Original kept. Your newer draft is still here.");
  } catch(error) {notice(error.message,true);}
  finally {button.disabled=!ready;button.textContent="Keep on this device";}
};
$("body").addEventListener("keydown",event=>{if((event.ctrlKey || event.metaKey) && event.key==="Enter") {event.preventDefault();$("capture-form").requestSubmit();}});

function render() {
  visible=matching(library,{query:$("search").value,date:$("date").value,kind});
  $("result-count").textContent=visible.length+" of "+library.records.length+" retained originals";
  const list=$("items");list.replaceChildren();
  for(const row of visible.slice(0,100)) {
    const li=document.createElement("li"),button=document.createElement("button");button.className="item";button.type="button";
    const heading=document.createElement("div");heading.className="item-heading";
    const body=row.body.trim(),firstLine=body.split("\n")[0];
    const headingText=firstLine.match(/^(.{1,100}?[.!?])(?:\s|$)/u)?.[1] || firstLine;
    const title=document.createElement("h3");title.textContent=headingText;
    const date=document.createElement("time");date.dateTime=row.captured_at;date.textContent=new Date(row.captured_at).toLocaleDateString(undefined,{month:"short",day:"numeric"});
    heading.append(title,date);
    const excerpt=document.createElement("p");excerpt.textContent=body.slice(headingText.length).trim();excerpt.hidden=!excerpt.textContent;
    const category=document.createElement("span");category.className="item-label";category.textContent=row.use_case==="suno" ? "Suno direction" : row.kind==="prompt" ? "Prompt" : "Original";
    const tags=document.createElement("span");tags.className="item-tags";tags.textContent=library.tags.filter(tag=>tag.uid===row.uid).slice(0,3).map(tag=>tag.label).join(" · ");
    button.append(heading,excerpt,category,tags);button.onclick=()=>showOriginal(row,button);li.append(button);list.append(li);
  }
  $("empty").hidden=visible.length>0;
  $("empty-title").textContent=library.records.length ? "No originals match this view." : "A little space for your next idea.";
  $("empty-copy").textContent=library.records.length ? "Try another word, date or library type. Your retained originals are unchanged." : "Paste a prompt or write something above. It stays in this browser until you export or clear its data.";
  if(visible.length>100) $("result-count").textContent+=" · showing newest 100; narrow the search for more";
}
for(const id of ["search","date"]) $(id).addEventListener("input",render);
for(const button of document.querySelectorAll("[data-kind]")) button.onclick=()=>{kind=button.dataset.kind;for(const tab of document.querySelectorAll("[data-kind]")) tab.setAttribute("aria-pressed",String(tab===button));render();};
function showOriginal(row,trigger) {
  original=row;$("reader-body").textContent=row.body;
  const device=row.device.startsWith("phone:") ? "Mobile library "+row.device.slice(-6) : row.device;
  $("reader-meta").textContent=new Date(row.captured_at).toLocaleString()+" · "+device+" · "+(row.source_app==="starlight-mobile" ? "Starlight" : row.source_app);
  $("reader-tags").textContent=library.tags.filter(tag=>tag.uid===row.uid).map(tag=>tag.label+" · "+tag.source).join(" / ");
  notice("The retained original is unchanged.",false,"reader-status");openDialog("reader-dialog",trigger);
}
$("copy-original").onclick=async()=>{
  const row=original,button=$("copy-original");if(!row) return;button.disabled=true;
  try {if(!navigator.clipboard?.writeText) throw Error("Select the original text and copy it manually.");await navigator.clipboard.writeText(row.body);if(original===row) notice("Original copied.",false,"reader-status");}
  catch(error) {notice(error.message,true,"reader-status");}
  finally {button.disabled=false;}
};

$("export").onclick=async()=>{
  try {
    if(!visible.length) throw Error("Choose a view with at least one retained original.");
    const packet=exportSelection(library,visible.map(row=>row.uid));
    const blob=new Blob([JSON.stringify(packet)],{type:"application/json"});
    const name="Starlight-private-library-"+new Date().toISOString().slice(0,10)+".json";
    const file=typeof File!=="undefined" ? new File([blob],name,{type:"application/json"}) : null;
    if(file && navigator.canShare?.({files:[file]})) {
      await navigator.share({files:[file],title:"Private Starlight library"});
      notice("Handoff shared through the destination you chose. Keep the original on this device.",false,"transfer-status");
    } else {
      const url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      notice("Download requested. Check the file before treating it as a second copy.",false,"transfer-status");
    }
  } catch(error) {notice(error.name==="AbortError" ? "Sharing cancelled. Your originals remain here." : error.message,true,"transfer-status");}
};
$("import-file").onchange=async()=>{
  const serial=++importSerial;pendingImport=null;$("apply-import").disabled=true;
  const file=$("import-file").files[0];if(!file) return;
  try {
    if(file.size>MAX_HANDOFF) throw Error("This file exceeds 450 KB. Export a smaller desktop selection.");
    const packet=validate(JSON.parse(await file.text()));if(serial!==importSerial) return;
    merge(library,packet);pendingImport=packet;
    $("import-preview").textContent=packet.records.length+" originals, "+packet.collections.length+" vibe definitions and "+packet.tags.length+" labels validated. Existing originals will be reused.";
    $("apply-import").disabled=!ready;notice("Review the counts, then import.",false,"transfer-status");
  } catch(error) {if(serial===importSerial) notice(error.message,true,"transfer-status");}
};
$("apply-import").onclick=async()=>{
  if(!ready || !pendingImport) return;
  const packet=pendingImport,serial=importSerial;$("apply-import").disabled=true;
  try {library=await commit(db,packet);render();if(serial===importSerial){pendingImport=null;$("import-file").value="";$("import-preview").textContent="Import committed locally.";}notice("Originals and dates retained. Repeating this handoff reuses matching sources.",false,"transfer-status");}
  catch(error) {notice(error.message,true,"transfer-status");}
  finally {if(serial===importSerial) $("apply-import").disabled=!pendingImport;}
};
$("persist").onclick=async()=>{
  try {const granted=await navigator.storage?.persist?.();$("storage-state").textContent=granted ? "Persistent storage granted by this browser. Export another copy for device loss." : "Persistent storage was not granted. Export a second copy; clearing browser data still removes this library.";}
  catch {$("storage-state").textContent="Persistent storage is unavailable. Export a second copy.";}
};

async function start() {
  if(starting) return;starting=true;$("retry").hidden=true;
  try {
    db=await openStore();localDevice=await deviceIdentity(db);library=validate(await getState(db,"library") || emptyPacket(),false);
    const drafts=await allDrafts(db),draft=drafts.find(row=>row.id===draftId) || drafts[0];
    if(draft) {
      if(draft.id!==draftId) recoveredDraft={id:draft.id,revision:draft.revision};
      $("body").value=draft.body;$("category").value=draft.category || "idea";$("tags").value=draft.tags || "";
      revision=Math.max(1,draft.revision || 1);await persistDraft();notice("Recovered your unfinished draft from local storage.");
    }
    ready=true;$("save").disabled=false;render();
    if(new URL(location.href).searchParams.get("shared")==="saved") {notice("Shared text committed locally. Find it in your collection.");history.replaceState(null,"",location.pathname);}
  } catch(error) {ready=false;$("save").disabled=true;$("result-count").textContent="Local storage is unavailable";$("retry").hidden=false;notice(error.message,true);}
  finally {starting=false;}
}
$("retry").onclick=start;
start();
if("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("./sw.js",{type:"module"}).then(()=>navigator.serviceWorker.ready).then(()=>{$("offline-state").textContent="App shell ready offline";}).catch(()=>{$("offline-state").textContent="Offline shell unavailable · retry online";});
} else $("offline-state").textContent="HTTPS needed for installation and sharing";
window.addEventListener("pageshow",async()=>{if(db && ready){try{library=validate(await getState(db,"library") || emptyPacket(),false);render();}catch{notice("Could not refresh local originals. Retry without clearing browser data.",true);}}});
