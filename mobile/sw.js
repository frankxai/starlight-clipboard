import {openStore,commit,makeCapture,deviceIdentity} from "./store.js";
const CACHE="starlight-capture-v1";
const ASSETS=["./","./index.html","./style.css","./app.js","./store.js","./manifest.webmanifest","./icon.png"];
self.addEventListener("install",event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS))));
self.addEventListener("activate",event=>event.waitUntil(self.clients.claim()));
self.addEventListener("fetch",event=>{
  const url=new URL(event.request.url),base=new URL("./",self.location.href);
  if(url.origin!==base.origin || !url.pathname.startsWith(base.pathname)) return;
  if(event.request.method==="POST" && url.pathname===new URL("./share",base).pathname) {
    event.respondWith((async()=>{
      const type=event.request.headers.get("content-type") || "";
      if(!type.startsWith("application/x-www-form-urlencoded")) return new Response("Unsupported share. Open Starlight and paste the text.",{status:415});
      const raw=await event.request.text();
      if(new TextEncoder().encode(raw).length>500000) return new Response("Share too large. Open Starlight and save a smaller selection.",{status:413});
      const form=new URLSearchParams(raw),body=[form.get("text"),form.get("url")].filter(Boolean).join("\n");
      try {
        const db=await openStore();
        try {
          const packet=makeCapture(body,"idea","",await deviceIdentity(db));
          packet.records[0].source_title=(form.get("title") || "Shared text · source app unknown").slice(0,200);
          await commit(db,packet);
        } finally {db.close();}
        return Response.redirect(new URL("./?shared=saved",base),303);
      } catch {
        // Never forward a private share payload to a hosting server.
        return new Response("This share could not be saved locally. Return to the source and retry, or open Starlight and paste it. No upload was attempted.",{status:507,headers:{"Content-Type":"text/plain; charset=utf-8"}});
      }
    })());
    return;
  }
  if(event.request.method!=="GET") return;
  const key=event.request.mode==="navigate" ? new URL("./index.html",base).href : event.request.url;
  event.respondWith(caches.match(key).then(cached=>cached || fetch(event.request)));
});
