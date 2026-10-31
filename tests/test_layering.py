"""Scope rules that would otherwise rot quietly: the Windows path stays open."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ("backend.py", "cli.py", "errors.py", "gui.py", "session.py", "state.py", "__init__.py")
LINUX_WORDS = re.compile(r"/sys|sysfs|udev|systemd|kbd_backlight|multi_intensity|/\.config\b")


class LayeringTests(unittest.TestCase):
    def test_shared_code_never_mentions_linux_hardware(self):
        for name in SHARED:
            text = (ROOT / "clevo_kbd" / name).read_text()
            self.assertIsNone(LINUX_WORDS.search(text), name)

    def test_only_the_backend_package_opens_a_device_path(self):
        for name in SHARED:
            text = (ROOT / "clevo_kbd" / name).read_text()
            self.assertNotIn("linux_sysfs", text, name)

    def test_linux_only_files_live_under_packaging(self):
        linux_files = {path.name for path in (ROOT / "packaging" / "linux").iterdir()}
        self.assertIn("90-clevo-kbd.rules", linux_files)
        self.assertIn("clevo-kbd-restore.service", linux_files)
        self.assertIn("clevo-kbd-resume@.service", linux_files)
        code = {path.name for path in (ROOT / "clevo_kbd").rglob("*") if path.is_file()}
        self.assertFalse(linux_files & code)

    def test_every_text_file_is_lf(self):
        for path in ROOT.rglob("*"):
            if path.is_file() and not {"__pycache__", ".git"} & set(path.relative_to(ROOT).parts):
                self.assertNotIn(b"\r\n", path.read_bytes(), path)


if __name__ == "__main__":
    unittest.main()
