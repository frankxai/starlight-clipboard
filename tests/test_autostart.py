"""board() auto-start helpers; process start is mocked, no clipboard or Windows needed."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import clip_autostart as auto


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class EnsureCollector(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.panel = Path(self.temp.name) / "panel.json"
        self.script = Path("clip.py")
        self.clock = Clock()

    def run_ensure(self, running, spawn, **kw):
        return auto.ensure_collector(self.panel, running, self.script, spawn=spawn, clock=self.clock, sleep=self.clock.sleep, **kw)

    def test_running_collector_is_not_spawned(self):
        self.panel.write_text("{}")
        spawn = MagicMock()
        self.assertTrue(self.run_ensure(lambda: True, spawn))
        spawn.assert_not_called()

    def test_stopped_collector_is_spawned_and_awaited(self):
        state = {"up": False}

        def spawn(script):
            state["up"] = True
            self.panel.write_text("{}")
            os.utime(self.panel, (self.clock.now + 1, self.clock.now + 1))

        spawn = MagicMock(side_effect=spawn)
        self.assertFalse(self.run_ensure(lambda: state["up"], spawn))
        spawn.assert_called_once_with(self.script)

    def test_stale_panel_file_does_not_count_and_times_out(self):
        self.panel.write_text("{}")
        os.utime(self.panel, (0, 0))
        spawn = MagicMock()
        with self.assertRaises(auto.CollectorStartError):
            self.run_ensure(lambda: False, spawn)
        spawn.assert_called_once()
        self.assertGreaterEqual(self.clock.now - 1000.0, 10.0)

    def test_spawn_detached_uses_popen_with_devnull(self):
        with patch.object(auto.subprocess, "Popen") as popen:
            auto.spawn_detached(Path("/x/clip.py"))
        args, kwargs = popen.call_args
        self.assertEqual(args[0][1:], [str(Path("/x/clip.py")), "watch"])
        self.assertIs(kwargs["stdin"], auto.subprocess.DEVNULL)
        self.assertTrue(kwargs["close_fds"])


if __name__ == "__main__":
    unittest.main()
