// Offline capture and the existing desktop handoff contract. No network client.
export const SCHEMA = "starlight.clipboard-library.v1";
export const MAX_HANDOFF = 450000;
const encoder = new TextEncoder();
const recordKeys = ["uid", "body", "kind", "captured_at", "last_seen_at", "source_app", "source_title", "device", "use_case"];
const text = (value, max, empty = false) => {
  if (typeof value !== "string" || value.length > max || (!empty && !value.trim())) throw Error("An entry is empty or exceeds its text limit.");
  return value;
};
const identity = value => {
  if (!/^[A-Za-z0-9:_-]{1,160}$/.test(text(value, 160))) throw Error("An entry has an unsupported identity.");
  return value;
};
const exact = (value, keys) => value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).sort().join("|") === [...keys].sort().join("|");
const iso = value => {
  text(value, 40);
  const parts=value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,7})?(?:Z|[+-](\d{2}):(\d{2}))$/);
  if (!parts || !Number.isFinite(Date.parse(value))) throw Error("An entry has an invalid source date.");
  const [,year,month,day,hour,minute,second,offsetHour="0",offsetMinute="0"]=parts.map(value=>value===undefined ? undefined : Number(value));
  const days=[31,(year%4===0 && (year%100!==0 || year%400===0))?29:28,31,30,31,30,31,31,30,31,30,31];
  if(year<1 || month<1 || month>12 || day<1 || day>days[month-1] || hour>23 || minute>59 || second>59 || Number(offsetHour)>23 || Number(offsetMinute)>59) throw Error("An entry has an invalid source date.");
  return value;
};
export function emptyPacket() {
  return {schema: SCHEMA, created_at: new Date().toISOString(), privacy: "private-unencrypted-export", records: [], collections: [], members: [], tags: []};
}
export function validate(packet, handoff = true) {
  if (!exact(packet, ["schema", "created_at", "privacy", "records", "collections", "members", "tags"]) || packet.schema !== SCHEMA || packet.privacy !== "private-unencrypted-export") throw Error("Choose a Starlight library handoff v1 file.");
  iso(packet.created_at);
  if (handoff && encoder.encode(JSON.stringify(packet)).length > MAX_HANDOFF) throw Error("This handoff exceeds 450 KB. Export a smaller selection.");
  const bounds = {records: handoff ? 999 : 2000, collections: 100, members: 5000, tags: handoff ? 5000 : 40000};
  for (const [key, max] of Object.entries(bounds)) if (!Array.isArray(packet[key]) || packet[key].length > max) throw Error("This library exceeds its entry limit. Export your work before adding more.");
  if (!handoff && encoder.encode(JSON.stringify(packet)).length > 10000000) throw Error("This browser library reached its 10 MB limit. Export your work before adding more.");
  const ids = new Set(), groups = new Set(), labels = new Map();
  for (const row of packet.records) {
    if (!exact(row, recordKeys)) throw Error("A capture has unsupported fields.");
    identity(row.uid); if (ids.has(row.uid)) throw Error("The handoff repeats an original identity."); ids.add(row.uid);
    text(row.body, 100000); iso(row.captured_at); iso(row.last_seen_at);
    for (const [key, max] of [["source_app",80],["source_title",200],["device",80]]) text(row[key], max, true);
    if (!["text","prompt","code","url","command","path"].includes(row.kind) || !["","suno"].includes(row.use_case)) throw Error("A capture has a protected or unsupported type.");
  }
  for (const group of packet.collections) {
    if (!exact(group,["id","name","description","mode","query"])) throw Error("A vibe has unsupported fields.");
    identity(group.id); if (groups.has(group.id)) throw Error("The handoff repeats a vibe identity."); groups.add(group.id);
    text(group.name,80); text(group.description,500,true); text(group.query,500,true);
    if (!["manual","smart"].includes(group.mode)) throw Error("A vibe has an unsupported mode.");
  }
  for (const member of packet.members) if (!exact(member,["collection","uid"]) || !groups.has(member.collection) || !ids.has(member.uid)) throw Error("A vibe membership has no retained original.");
  for (const tag of packet.tags) {
    if (!exact(tag,["uid","label","source","reason"]) || !ids.has(tag.uid)) throw Error("A tag has no retained original.");
    text(tag.label,40); text(tag.reason,240,true);
    if (!["user","agent","local-rule"].includes(tag.source)) throw Error("A tag has an unsupported author.");
    const set = labels.get(tag.uid) || new Set(); set.add(tag.label); labels.set(tag.uid,set);
    if (set.size > 20) throw Error("Keep no more than 20 tags on one capture.");
  }
  return packet;
}
export function makeCapture(body, category = "idea", labels = "", device = "This phone") {
  text(body,100000); text(device,80);
  const row = {uid:"mobile:"+crypto.randomUUID(),body,kind:category === "idea" ? "text" : "prompt",
    captured_at:new Date().toISOString(),last_seen_at:new Date().toISOString(),source_app:"starlight-mobile",
    source_title:category === "suno" ? "Music direction · submission unknown" : "Deliberate mobile capture",device,use_case:category === "suno" ? "suno" : ""};
  const tags = [...new Set(labels.split(",").map(value=>value.normalize("NFKC").trim().toLocaleLowerCase()).filter(Boolean))];
  if (tags.length > 20 || tags.some(tag=>tag.length > 40 || /[\u0000-\u001f]/.test(tag))) throw Error("Use up to 20 short tags, separated by commas.");
  const packet = emptyPacket(); packet.records=[row]; packet.tags=tags.map(label=>({uid:row.uid,label,source:"user",reason:"Chosen during mobile capture"}));
  return validate(packet);
}
export function merge(existing, incoming) {
  validate(existing,false); validate(incoming);
  const result = structuredClone(existing), originals = new Map(result.records.map(row=>[row.uid,row]));
  for (const row of incoming.records) {
    const prior = originals.get(row.uid);
    if (prior && recordKeys.some(key=>prior[key] !== row[key])) throw Error("An original with this identity differs. Review it on desktop; this library is unchanged.");
    if (!prior) {result.records.push(row); originals.set(row.uid,row);}
  }
  const groups = new Map(result.collections.map(group=>[group.id,group]));
  for (const group of incoming.collections) {
    const prior = groups.get(group.id);
    if (prior && ["name","description","mode","query"].some(key=>prior[key] !== group[key])) throw Error("A vibe differs from this library. Resolve its variant on desktop before importing.");
    if (!prior) {result.collections.push(group); groups.set(group.id,group);}
  }
  for (const [name,key] of [["members",row=>row.collection+"\0"+row.uid],["tags",row=>row.uid+"\0"+row.label]]) {
    const seen = new Map(result[name].map((row,index)=>[key(row),index]));
    for (const row of incoming[name]) {
      const position = seen.get(key(row));
      if (position === undefined) {seen.set(key(row),result[name].length);result[name].push(row);}
      else if (name === "tags" && result[name][position].source !== "user" && row.source === "user") result[name][position]=row;
    }
  }
  result.created_at=new Date().toISOString();
  return validate(result,false);
}
export function exportSelection(packet, ids) {
  const selected = new Set(ids);
  const output = {...structuredClone(packet),created_at:new Date().toISOString()};
  output.records=output.records.filter(row=>selected.has(row.uid));
  output.members=output.members.filter(row=>selected.has(row.uid));
  output.tags=output.tags.filter(row=>selected.has(row.uid));
  return validate(output);
}
export function matching(packet, {query="",date="",kind="all",tag=""} = {}) {
  const lower = query.toLocaleLowerCase();
  return packet.records.filter(row=>{
    const tags=packet.tags.filter(label=>label.uid===row.uid).map(label=>label.label);
    const when=new Date(row.captured_at),day=[when.getFullYear(),String(when.getMonth()+1).padStart(2,"0"),String(when.getDate()).padStart(2,"0")].join("-");
    return (!date || day===date) && (!tag || tags.includes(tag)) &&
      (kind==="all" || (kind==="suno" ? row.use_case==="suno" : kind==="prompts" ? row.kind==="prompt" : row.kind==="text")) &&
      (!lower || [row.body,row.source_title,row.source_app,...tags].join(" ").toLocaleLowerCase().includes(lower));
  }).sort((a,b)=>b.captured_at.localeCompare(a.captured_at));
}

export function openStore() {
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open("starlight-clipboard-mobile",1);let blocked=false;
    request.onupgradeneeded=()=>request.result.createObjectStore("state",{keyPath:"key"});
    request.onsuccess=()=>{const db=request.result;if(blocked){db.close();return;}db.onversionchange=()=>db.close();resolve(db);};
    request.onerror=()=>reject(Error("Local storage could not open. Your text is still in the composer; copy it before leaving."));
    request.onblocked=()=>{blocked=true;reject(Error("Close another old Starlight mobile window, then retry."));};
  });
}
export function getState(db, key) {
  return new Promise((resolve,reject)=>{
    const transaction=db.transaction("state","readonly"),request=transaction.objectStore("state").get(key);
    transaction.oncomplete=()=>resolve(request.result?.value);
    transaction.onerror=()=>reject(Error("Local storage could not be read. Retry without clearing browser data."));
  });
}
export function deviceIdentity(db) {
  return new Promise((resolve,reject)=>{
    const transaction=db.transaction("state","readwrite"),store=transaction.objectStore("state"),request=store.get("device");
    let value;
    request.onsuccess=()=>{value=request.result?.value || "phone:"+crypto.randomUUID();if(!request.result)store.put({key:"device",value});};
    transaction.oncomplete=()=>resolve(value);
    transaction.onabort=()=>reject(Error("The local device identity could not be stored. Keep your text and retry."));
    transaction.onerror=()=>{};
  });
}
export function allDrafts(db) {
  return new Promise((resolve,reject)=>{
    const transaction=db.transaction("state","readonly"),request=transaction.objectStore("state").getAll();
    transaction.oncomplete=()=>resolve(request.result.filter(row=>row.key.startsWith("draft:") && row.value.body?.trim()).map(row=>({id:row.key,...row.value})).sort((a,b)=>b.updated_at.localeCompare(a.updated_at)));
    transaction.onerror=()=>reject(Error("Draft recovery failed. Retry without clearing browser data."));
  });
}
export function writeDraft(db,id,fields,revision) {
  return new Promise((resolve,reject)=>{
    const transaction=db.transaction("state","readwrite"),store=transaction.objectStore("state");
    store.put({key:id,value:{...fields,revision,updated_at:new Date().toISOString()}});
    transaction.oncomplete=()=>resolve();
    transaction.onabort=()=>reject(Error("The draft could not be stored. Keep this window open and copy your text."));
    transaction.onerror=()=>{};
  });
}
export function commit(db,packet,draft=null) {
  return new Promise((resolve,reject)=>{
    const transaction=db.transaction("state","readwrite"),store=transaction.objectStore("state"),request=store.get("library");
    let result, problem;
    request.onsuccess=()=>{
      try {
        result=merge(request.result?.value || emptyPacket(),packet);
        store.put({key:"library",value:result});
        for(const saved of (Array.isArray(draft) ? draft : draft ? [draft] : [])) {
          const pending=store.get(saved.id);
          pending.onsuccess=()=>{if(pending.result?.value.revision===saved.revision) store.delete(saved.id);};
        }
      } catch(error) {problem=error;transaction.abort();}
    };
    transaction.oncomplete=()=>resolve(result);
    transaction.onabort=()=>reject(problem || Error("Save did not commit. Your original and draft are unchanged; retry."));
    transaction.onerror=()=>{};
  });
}
