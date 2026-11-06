"""Start the collector detached when `clips board` finds it stopped. Pure helpers; no Windows imports."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable


class CollectorStartError(RuntimeError):
    pass


def spawn_command(script: Path, executable: str | None = None) -> list[str]:
    """Same launcher as start-clipd.vbs: pythonw.exe beside the interpreter, running `<script> watch`."""
    exe = Path(executable or sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return [str(windowless if windowless.is_file() else exe), str(script), "watch"]


def spawn_detached(script: Path) -> None:
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(spawn_command(script), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags)


def ensure_collector(panel: Path, running: Callable[[], bool], script: Path, *, spawn: Callable[[Path], None] = spawn_detached,
                     timeout: float = 10.0, interval: float = 0.25, clock: Callable[[], float] = time.time,
                     sleep: Callable[[float], None] = time.sleep) -> bool:
    """Return True if the collector was already running, False if started now; raise if it never came up.

    A leftover panel.json from an earlier run does not count: it must be rewritten after the spawn.
    """
    if running() and panel.is_file():
        return True
    started = clock()
    spawn(script)
    while clock() - started < timeout:
        try:
            fresh = panel.is_file() and panel.stat().st_mtime >= started - 1
        except OSError:
            fresh = False
        if fresh and running():
            return False
        sleep(interval)
    raise CollectorStartError(f"Started the collector but {panel.name} did not appear within {timeout:g} seconds.")
