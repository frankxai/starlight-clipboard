"""Standalone synthetic preview and real-browser interaction checks. No private data."""
from datetime import datetime, timezone, timedelta
import argparse
import json
from pathlib import Path


def build(state="library", qa=False):
    now = datetime.now(timezone.utc)
    music = ("Midnight piano, silver strings\n\nCinematic neo-classical piano, 84 BPM, felt keys and intimate room tone. "
             "Slowly unfolding silver strings, a patient low pulse, and no vocals.\n\nArrangement\nA sparse opening. "
             "Let the melody settle before the strings arrive. One restrained lift, then return to the piano alone.\n\n"
             "Mood\nQuiet confidence. A late-night city seen through rain. Warm, spacious and unhurried.")
    seeds = [
        (music,"prompt","suno","Chrome","saved",1),
        ("Rain recordings for the next piano project\n\nSmall, everyday sounds: bicycle bells, station announcements and the first rain on warm pavement.","text","","Starlight","saved",0),
        ("A clear creative direction\n\nYou are an editor. Preserve the original intention, find the useful detail and return a short title with a practical next step.","prompt","","Codex","active",0),
        ("const source = { id, capturedAt, useCase };\nconst result = await memory.file(source);\n\nif (result.recallVerified) {\n  showReceipt(result.memoryId);\n}","code","","VS Code","active",0),
        ("https://developers.cloudflare.com/browser-run/","url","","Edge","active",0),
        ("A retained long original\n\n" + "An original detail worth recovering. "*350,"text","","Chrome","active",0),
        ("An older direction, ready to recover.","text","","Starlight","archived",0),
        ("","secret","","","active",0),
    ]
    clips=[]
    for i,(body,kind,use,app,status,pinned) in enumerate(seeds,1):
        at=(now-timedelta(hours=i if i<4 else i+20)).isoformat().replace("+00:00","Z")
        clips.append(dict(id=i,kind=kind,use_case=use,app=app,title="Source-linked memory receipt" if kind=="code" else "",
                          body=body[:400],full=body,preview=" ".join(body.split())[:240] or "[redacted]",more=len(body)>400,
                          state=status,copies=3 if i==1 else 1,pinned=pinned,captured_at=at,last_seen_at=at,
                          stored=bool(body),image=False,reason="Suno is a suggested use case. Submission is unverified." if use else ""))
    mock = r'''
window.__CLIPBOARD_DEMO__=true;
window.__fixtureClips=__DATA__;
window.__fixtureCalls=[];
window.fetch=function(url,options={}){
 const u=new URL(url,"https://fixture.invalid"),path=u.pathname,q=u.searchParams.get("q")||"";
 window.__fixtureCalls.push({path,q,body:options.body?JSON.parse(options.body):null});
 const delay=path==="/api/detail"?150:path==="/api/add"?100:path==="/api/book"?100:q.includes("piano")?130:8;
 return new Promise((resolve,reject)=>{
  if(options.signal?.aborted){reject(options.signal.reason||new DOMException("Aborted","AbortError"));return}
  const abort=()=>{clearTimeout(timer);reject(options.signal.reason||new DOMException("Aborted","AbortError"))};
  const timer=setTimeout(()=>{
   options.signal?.removeEventListener("abort",abort);
   if(path==="/api/items"&&window.__qaFailNextItems){window.__qaFailNextItems=false;reject(new TypeError("Synthetic connection interruption"));return}
   let data={ok:true};const all=window.__fixtureClips;
   if(path==="/api/items"){
    let rows=all.slice();const state=q.match(/state:(\w+)/)?.[1],kind=q.match(/type:(\w+)/)?.[1],use=q.match(/use:(\w+)/)?.[1],app=q.match(/app:(\w+)/)?.[1];
    if(state&&state!=="any")rows=rows.filter(x=>x.state===state);else if(!state)rows=rows.filter(x=>!["archived","resolved"].includes(x.state));
    if(kind)rows=rows.filter(x=>x.kind===kind);if(use)rows=rows.filter(x=>x.use_case===use);if(app)rows=rows.filter(x=>x.app.toLowerCase().includes(app.toLowerCase()));
    const text=q.replace(/(?:state|type|use|app|on):\S+/g,"").trim().toLowerCase();
    if(text)rows=rows.filter(x=>(x.full+" "+x.app).toLowerCase().includes(text));
    rows.sort((a,b)=>b.pinned-a.pinned||new Date(b.last_seen_at)-new Date(a.last_seen_at));data={items:rows};
   }else if(path==="/api/detail")data={body:all.find(x=>x.id===Number(u.searchParams.get("id")))?.full||""};
   else if(path==="/api/health"){
    const active=all.filter(x=>!["archived","resolved"].includes(x.state));const at=new Date().toISOString();
    data={collector_running:true,records:all.length,last_capture_at:at,library:{all:active.length,prompts:active.filter(x=>x.kind==="prompt").length,suno:active.filter(x=>x.use_case==="suno").length,saved:all.filter(x=>x.state==="saved").length,archive:all.filter(x=>x.state==="archived").length,history:all.length},integrations:{memory_configured:true,encrypted_backup:{created_at:at}},last_backup:{created_at:at}};
   }else if(path==="/api/add"){
    const body=JSON.parse(options.body).text,id=Math.max(...all.map(x=>x.id))+1,at=new Date().toISOString();
    all.push({id,kind:"text",use_case:"",app:"Starlight",title:"Saved idea",body,full:body,preview:body,more:false,state:"saved",copies:1,pinned:0,captured_at:at,last_seen_at:at,stored:true,image:false});data={ok:true,id};
   }else if(path==="/api/state"){const body=JSON.parse(options.body);all.find(x=>x.id===body.id).state=body.state}
   else if(path==="/api/brain")data={ok:true,state:"recall_verified",memory_id:"synthetic-only"};
   else if(path==="/api/backup")data={ok:true,snapshot:"synthetic-only",encrypted:{state:"encrypted_local"}};
   resolve(new Response(JSON.stringify(data),{status:200,headers:{"Content-Type":"application/json"}}));
  },delay);
  options.signal?.addEventListener("abort",abort,{once:true});
 });
};
'''.replace("__DATA__",json.dumps(clips,ensure_ascii=False)).replace("new Date().toISOString()",json.dumps(now.isoformat()))
    driver = r'''
(async()=>{
 const checks=[],sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const wait=async(fn,label)=>{for(let i=0;i<120;i++){if(fn())return;await sleep(10)}throw new Error(label)};
 const check=(label,value)=>{checks.push({label,pass:!!value});if(!value)throw new Error(label)};
 const key=(target,name,extra={})=>target.dispatchEvent(new KeyboardEvent("keydown",{key:name,bubbles:true,cancelable:true,...extra}));
 const input=document.getElementById("q"),$=id=>document.getElementById(id);
 try{
  await wait(()=>$("list").querySelectorAll("[role=option]").length>0,"initial rows");await sleep(180);
  check("full retained preview",$("preview").textContent.includes("Warm, spacious and unhurried"));
  input.focus();key(input,"ArrowDown");check("arrow navigation",input.getAttribute("aria-activedescendant")==="copy-2");
  $("new-idea").focus();key($("new-idea"),"k",{ctrlKey:true});check("search shortcut focus",document.activeElement===input);check("search has visible focus",parseFloat(getComputedStyle(input.parentElement).outlineWidth)>=2);
  $("new-idea").click();check("composer focus",document.activeElement===$("idea-text"));
  $("idea-text").value="Keep this unsaved field recording idea";$("idea-text").dispatchEvent(new Event("input"));key($("idea-text"),"Escape");
  $("new-idea").click();check("interrupted draft retained",$("idea-text").value.includes("field recording"));
  $("idea").requestSubmit();await sleep(25);$("idea-text").value="A newer draft while the first saves";await sleep(170);
  check("newer draft survives delayed save",!$("idea").hidden&&$("idea-text").value.includes("newer draft"));
  check("newer draft keeps focus",document.activeElement===$("idea-text"));
  $("idea-text").value="";$("cancel-idea").click();$("clear").click();await sleep(35);
  input.value="piano";input.dispatchEvent(new Event("input"));await sleep(95);input.value="editor";input.dispatchEvent(new Event("input"));await sleep(260);
  check("interrupted search chooses latest query",[...$("list").querySelectorAll("[role=option]")].every(x=>x.id==="copy-3"));
  window.__qaFailNextItems=true;input.value="not-found";input.dispatchEvent(new Event("input"));await sleep(120);
  check("connection failure offers retry",!$("retry").hidden);
  check("stale results cannot paste",$("paste").disabled);
  const pasted=window.__fixtureCalls.filter(x=>x.path==="/api/paste").length;key(input,"Enter");await sleep(15);
  check("stale enter cannot apply old capture",window.__fixtureCalls.filter(x=>x.path==="/api/paste").length===pasted);
  $("clear").click();await sleep(35);$("copy-6").click();await sleep(20);$("copy-2").click();await sleep(190);
  check("stale long preview cannot replace selection",$("preview").textContent.includes("bicycle bells")&&!$("preview").textContent.includes("An original detail worth recovering"));
  $("copy-8").click();check("excluded payload disables copy",$("copy").disabled&&$("book").disabled&&$("brain").disabled);
  document.querySelector('[data-view="suno"]').click();await sleep(35);$("copy-1").click();$("book").click();$("book").click();await sleep(150);
  const books=window.__fixtureCalls.filter(x=>x.path==="/api/book");check("duplicate action click suppressed",books.length===1);check("music routes to private Suno book",books[0].body.scope==="suno");
  $("health-toggle").click();check("health expansion announced",$("health-toggle").getAttribute("aria-expanded")==="true");key($("health-toggle"),"Escape");check("health escape restores focus",$("health-panel").hidden&&document.activeElement===$("health-toggle"));
  document.querySelector('[data-view="archive"]').click();await sleep(35);$("copy-7").click();$("archive").click();await sleep(50);
  check("archive restore retains original",window.__fixtureClips.find(x=>x.id===7).state==="active"&&window.__fixtureClips.find(x=>x.id===7).full==="An older direction, ready to recover.");
  check("empty result disables actions",$("list").textContent.includes("Nothing here yet")&&$("paste").disabled);
  $("new-idea").click();$("idea-text").value="One finished idea to keep";$("idea").requestSubmit();await sleep(160);
  check("saved idea is selected and composer closes",$("idea").hidden&&document.querySelector('[data-view="saved"]').getAttribute("aria-pressed")==="true"&&$("preview").textContent.includes("One finished idea to keep"));
  const rules=[...document.styleSheets[0].cssRules];const reduced=rules.find(r=>r.conditionText?.includes("prefers-reduced-motion"));check("reduced motion rules present",!!reduced);
  const style=document.createElement("style");style.textContent=[...reduced.cssRules].map(r=>r.cssText).join("\n");document.head.append(style);check("reduced motion disables transitions",getComputedStyle($("new-idea")).transitionDuration==="0s");style.remove();
  check("no document horizontal overflow",document.documentElement.scrollWidth<=innerWidth);
  check("viewport has no horizontal offset",Math.abs(scrollX)<1&&Math.abs(visualViewport?.offsetLeft||0)<1);
  check("viewport scale is one",Math.abs((visualViewport?.scale||1)-1)<.02);
  check("workspace and shell fit viewport",[".shell",".workspace",".stage"].every(s=>{const r=document.querySelector(s).getBoundingClientRect();return r.x>=-1&&r.right<=innerWidth+1}));
  check("top actions remain inside workspace",["hide","new-idea","health-toggle"].every(id=>{const r=$(id).getBoundingClientRect();return r.x>=0&&r.right<=innerWidth}));
  check("navigation scrolls inside its rail",document.querySelector(".nav").getBoundingClientRect().width<=innerWidth);
  check("interface text encoding intact",$("q").placeholder.includes("idea…")&&$("status").textContent.includes("·"));
  if(matchMedia("(pointer:coarse)").matches){document.querySelector('[role="option"][aria-selected="true"]').click();const targets=["hide","new-idea","health-toggle","date","app-filter","pin","copy","paste","book","brain","archive"];check("touch targets at least 44px",targets.every(id=>$(id).getBoundingClientRect().height>=44));}
  $("clear").click();await sleep(35);$("copy-1").click();await sleep(180);
  if(__STATE__==="library"){$("shell").dataset.detail="false";input.focus()}else if(__STATE__==="health"){$("health-toggle").click()}
  if(innerWidth<=600&&__STATE__==="detail")check("mobile detail has return path",getComputedStyle($("back")).display!=="none");
  window.__qaReport={passed:checks.length,checks,scope:"Synthetic real Chromium DOM. Key events dispatched; touch emulated. Reduced-motion declarations forced for computed-style verification.",viewport:{width:innerWidth,height:innerHeight,touch:matchMedia("(pointer:coarse)").matches,visualWidth:visualViewport?.width,scale:visualViewport?.scale,offsetLeft:visualViewport?.offsetLeft,scrollX}};
 }catch(error){window.__qaReport={error:String(error),checks};}
 const pre=document.createElement("pre");pre.id="qa-results";pre.hidden=true;pre.textContent=JSON.stringify(window.__qaReport);document.body.append(pre);document.documentElement.dataset.qaReady="true";
})();
'''.replace("__STATE__",json.dumps(state))
    source = Path(__file__).resolve().parents[1]/"board.html"
    html = source.read_text(encoding="utf-8").replace("__TOKEN__","fixture-only")
    html=html.replace("<script>","<script>"+mock+"</script><script>",1)
    if qa:
        html=html.replace("</body>","<script>"+driver+"</script></body>")
    elif state!="library":
        html=html.replace("</body>",'<script>setTimeout(()=>document.getElementById("copy-1").click(),80)</script></body>')
    return html


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--state",choices=["library","detail","health"],default="library")
    parser.add_argument("--qa",action="store_true")
    args=parser.parse_args()
    args.output.write_text(build(args.state,args.qa),encoding="utf-8",newline="\n")
    print(json.dumps({"output":str(args.output),"synthetic_only":True,"qa":args.qa}))
