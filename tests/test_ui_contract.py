"""Library metadata and native bounds regressions, isolated from the live archive."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if sys.platform=="win32":
    import clip


@unittest.skipUnless(sys.platform=="win32","Windows collector")
class LibraryContract(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        env=patch.dict(os.environ,{"CLIP_HOME":str(self.root),"PROMPT_FABRIC":str(self.root/"books"),"STARLIGHT_VAULT":str(self.root/"vault")})
        env.start();self.addCleanup(env.stop)

    def test_navigation_counts_agree_with_actual_library_filters(self):
        music=clip.ingest("Cinematic piano and strings, 84 BPM, no vocals")
        note=clip.ingest("An idea to keep for the next project")
        old=clip.ingest("You are an editor. Return a concise scene.")
        clip.set_state(music["id"],"saved")
        clip.set_state(old["id"],"resolved")
        counts=clip.health_snapshot()["library"]
        for key,query in [("all",""),("prompts","type:prompt"),("suno","use:suno"),
                          ("saved","state:saved"),("archive","state:archived"),("history","state:any")]:
            self.assertEqual(counts[key],len(clip.load_board_rows(query)),key)
        clip.set_state(note["id"],"archived")
        self.assertEqual(clip.health_snapshot()["library"]["archive"],1)

    def test_repeated_copy_exposes_last_seen_without_replacing_source_date(self):
        item=clip.ingest("A repeated source with separate occurrence timestamps")
        with patch.object(clip.clip_store,"now",return_value="2030-01-01T12:00:00.000000Z"):
            clip.ingest("A repeated source with separate occurrence timestamps")
        row=clip.board_items("state:any")["items"][0]
        self.assertEqual(row["id"],item["id"])
        self.assertEqual(row["last_seen_at"],"2030-01-01T12:00:00.000000Z")
        self.assertNotEqual(row["captured_at"],row["last_seen_at"])

    def test_window_fits_small_and_large_monitor_bounds(self):
        for screen in [(640,480),(1366,768),(1920,1080)]:
            with self.subTest(screen=screen),patch.object(clip.user32,"GetSystemMetrics",side_effect=screen):
                x,y,width,height=clip.palette_bounds()
                self.assertGreater(width,0);self.assertGreater(height,0)
                self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
                self.assertLessEqual(x+width,screen[0]);self.assertLessEqual(y+height,screen[1])


if __name__=="__main__":
    unittest.main()
