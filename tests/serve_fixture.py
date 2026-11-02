"""Ten-minute, local-only UI fixture. Never reads the real clipboard or vault."""
from pathlib import Path
import json
import os
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix="starlight-clipboard-qa-") as folder:
    root = Path(folder)
    os.environ.update(CLIP_HOME=str(root/"store"),PROMPT_FABRIC=str(root/"fabric"),STARLIGHT_VAULT=str(root/"vault"))
    import clip
    # This fixed capability belongs to disposable synthetic fixtures only.
    clip.secrets.token_urlsafe = lambda count: "fixture-only"
    for text,title in [
        ("Cinematic solo piano, 84 BPM, warm strings, no vocals","Suno fixture"),
        ("You are an editor. Preserve the original idea and return a useful draft.","Prompt fixture"),
        ("An idea: collect field recordings of rain for the next piano project.","Idea fixture"),
        ("A long original worth recovering. "*500,"Long-text fixture"),
        ("https://developers.cloudflare.com/workers-ai/","Reference fixture"),
    ]:
        clip.ingest(text,app="fixture.exe",title=title)
    clip.process_pending()
    clip.start_panel_server()
    endpoint=Path(sys.argv[1])
    endpoint.write_text(json.dumps({"url":f"http://127.0.0.1:{clip.PANEL['port']}/?k=fixture-only",
                                    "pid":os.getpid(),"root":str(root),"stop":str(endpoint.with_suffix('.stop'))}),encoding="utf-8")
    try:
        deadline=time.monotonic()+600
        while time.monotonic()<deadline and not endpoint.with_suffix('.stop').exists():
            time.sleep(.2)
    finally:
        clip.PANEL["server"].shutdown()
        clip.PANEL["server"].server_close()
