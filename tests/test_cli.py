import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from clevo_kbd.backends.linux_sysfs import LinuxSysfsBackend
from clevo_kbd.cli import main
from clevo_kbd.state import config_dir
from tests.fake_sysfs import FakeRootTestCase

LEFT, CENTRE, RIGHT = "rgb:kbd_backlight", "rgb:kbd_backlight_1", "rgb:kbd_backlight_2"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTests(FakeRootTestCase):
    def setUp(self):
        super().setUp()
        self.fake.add_three_zones()

    def saved(self):
        return json.loads(self.state_file.read_text())

    def test_set_one_zone(self):
        code, _, _ = run("set", "--zone", "left", "--color", "#ff0000")
        self.assertEqual(code, 0)
        self.assertEqual(self.fake.intensity(LEFT), "255 0 0\n")
        self.assertEqual(self.fake.intensity(CENTRE), "255 255 255\n")
        self.assertEqual(self.saved()["colors"]["left"], "#ff0000")

    def test_set_all_zones_is_the_default(self):
        run("set", "--color", "#102030")
        for name in (LEFT, CENTRE, RIGHT):
            self.assertEqual(self.fake.intensity(name), "16 32 48\n")

    def test_american_spelling_of_centre(self):
        code, _, _ = run("set", "--zone", "center", "--color", "#00ff00")
        self.assertEqual(code, 0)
        self.assertEqual(self.fake.intensity(CENTRE), "0 255 0\n")

    def test_bad_colour_changes_nothing(self):
        before = self.fake.snapshot()
        code, _, err = run("set", "--zone", "left", "--color", "red-ish")
        self.assertEqual(code, 2)
        self.assertIn("Not a colour", err)
        self.assertEqual(self.fake.snapshot(), before)
        self.assertFalse(self.state_file.exists())

    def test_brightness(self):
        code, _, _ = run("brightness", "128")
        self.assertEqual(code, 0)
        self.assertEqual(self.fake.brightness(LEFT), "128")
        self.assertEqual(self.saved()["brightness"], 128)

    def test_brightness_out_of_range(self):
        code, _, err = run("brightness", "999")
        self.assertEqual(code, 2)
        self.assertIn("0 to 255", err)
        self.assertFalse(self.state_file.exists())

    def test_off_then_on_returns_to_the_same_level(self):
        run("brightness", "77")
        run("off")
        self.assertEqual(self.fake.brightness(LEFT), "0")
        self.assertFalse(self.saved()["on"])
        self.assertEqual(self.saved()["brightness"], 77)
        run("on")
        self.assertEqual(self.fake.brightness(LEFT), "77")

    def test_on_from_a_dark_keyboard_with_nothing_saved_uses_full(self):
        run("on")
        self.assertEqual(self.fake.brightness(LEFT), "255")

    def test_status(self):
        run("set", "--zone", "right", "--color", "#0000ff")
        run("brightness", "10")
        code, out, _ = run("status")
        self.assertEqual(code, 0)
        self.assertIn("right       #0000ff", out)
        self.assertIn("brightness  10/255 (on)", out)

    def test_apply_with_nothing_saved_writes_nothing(self):
        before = self.fake.snapshot()
        code, out, _ = run("apply")
        self.assertEqual(code, 0)
        self.assertIn("Nothing saved", out)
        self.assertEqual(self.fake.snapshot(), before)


class RestoreTests(FakeRootTestCase):
    def setUp(self):
        super().setUp()
        self.fake.add_three_zones()
        run("set", "--zone", "left", "--color", "#ff0000")
        run("set", "--zone", "centre", "--color", "#00ff00")
        run("set", "--zone", "right", "--color", "#0000ff")
        run("brightness", "128")

    def test_apply_recovers_everything_after_a_reboot(self):
        self.fake.forget_like_a_reboot()
        self.assertEqual(self.fake.intensity(LEFT), "255 255 255\n")
        code, _, _ = run("apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.fake.intensity(LEFT), "255 0 0\n")
        self.assertEqual(self.fake.intensity(CENTRE), "0 255 0\n")
        self.assertEqual(self.fake.intensity(RIGHT), "0 0 255\n")
        for name in (LEFT, CENTRE, RIGHT):
            self.assertEqual(self.fake.brightness(name), "128")

    def test_apply_rewrites_brightness_the_driver_still_reports(self):
        """Firmware can lose a value the driver's cache still shows."""
        writes = []
        real_write = LinuxSysfsBackend._write

        def recording_write(path, text):
            writes.append(path.name)
            real_write(path, text)

        self.assertEqual(self.fake.brightness(LEFT), "128")
        with mock.patch.object(LinuxSysfsBackend, "_write", staticmethod(recording_write)):
            run("apply")
        self.assertEqual(writes.count("brightness"), 3)
        self.assertEqual(writes.count("multi_intensity"), 3)

    def test_apply_keeps_an_off_keyboard_off(self):
        run("off")
        self.fake.forget_like_a_reboot()
        run("apply")
        self.assertEqual(self.fake.brightness(LEFT), "0")
        self.assertEqual(self.fake.intensity(CENTRE), "0 255 0\n")

    def test_apply_is_idempotent(self):
        run("apply")
        first = self.fake.snapshot()
        run("apply")
        self.assertEqual(self.fake.snapshot(), first)

    def test_corrupt_state_stops_apply_and_leaves_the_leds_alone(self):
        self.fake.forget_like_a_reboot()
        self.state_file.write_text("{ not json")
        before = self.fake.snapshot()
        code, _, err = run("apply")
        self.assertEqual(code, 1)
        self.assertIn("not usable", err)
        self.assertEqual(self.fake.snapshot(), before)

    def test_a_later_change_replaces_a_corrupt_file(self):
        self.state_file.write_text("[]")
        code, _, err = run("brightness", "60")
        self.assertEqual(code, 0)
        self.assertIn("warning", err)
        self.assertEqual(json.loads(self.state_file.read_text())["brightness"], 60)

    def test_saved_file_has_no_platform_detail(self):
        text = self.state_file.read_text()
        self.assertEqual(sorted(json.loads(text)),
                         ["brightness", "colors", "link_zones", "on", "version"])
        for leak in ("/sys", "kbd_backlight", "/home", "leds"):
            self.assertNotIn(leak, text)


class NoDeviceCliTests(FakeRootTestCase):
    def test_every_hardware_command_explains_and_exits_3(self):
        for argv in (("status",), ("set", "--color", "#ffffff"), ("brightness", "1"),
                     ("on",), ("off",)):
            code, _, err = run(*argv)
            self.assertEqual(code, 3, argv)
            self.assertIn("No keyboard backlight LED device", err)
            self.assertNotIn("Traceback", err)
        self.assertFalse(self.state_file.exists())


class ConfigDirTests(unittest.TestCase):
    def test_linux_uses_xdg(self):
        self.assertEqual(config_dir("linux", {"XDG_CONFIG_HOME": "/x"}),
                         Path("/x/clevo-kbd"))

    def test_linux_ignores_a_relative_xdg_as_the_spec_requires(self):
        self.assertEqual(config_dir("linux", {"XDG_CONFIG_HOME": "rel"}),
                         Path.home() / ".config" / "clevo-kbd")

    def test_linux_default(self):
        self.assertEqual(config_dir("linux", {}), Path.home() / ".config" / "clevo-kbd")

    def test_windows_uses_appdata_and_not_dot_config(self):
        self.assertEqual(config_dir("win32", {"APPDATA": "C:/Users/x/AppData/Roaming"}),
                         Path("C:/Users/x/AppData/Roaming/clevo-kbd"))


if __name__ == "__main__":
    unittest.main()
