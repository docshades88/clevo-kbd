import os
import unittest
from unittest import mock

from clevo_kbd.backends import create_backend
from clevo_kbd.backends.linux_sysfs import LinuxSysfsBackend
from clevo_kbd.errors import (
    InvalidValueError,
    NoDeviceError,
    UnsupportedPlatformError,
    WriteDeniedError,
)
from tests.fake_sysfs import (
    FakeRootTestCase,
    kernel_accepts_multi_intensity,
    percent_i_values,
)


class KernelRuleTests(unittest.TestCase):
    """Prove the acceptance rule can fail before trusting it to pass."""

    def test_accepts_the_shapes_the_kernel_accepts(self):
        self.assertTrue(kernel_accepts_multi_intensity(b"255 0 0\n"))
        self.assertTrue(kernel_accepts_multi_intensity(b"255 0 0"))

    def test_rejects_too_few_values(self):
        self.assertFalse(kernel_accepts_multi_intensity(b"255 0\n"))

    def test_rejects_trailing_data(self):
        self.assertFalse(kernel_accepts_multi_intensity(b"255 0 0 9\n"))

    def test_rejects_commas(self):
        self.assertFalse(kernel_accepts_multi_intensity(b"255,0,0\n"))

    def test_sees_the_octal_trap(self):
        self.assertEqual(percent_i_values(b"010 0 0\n"), [8, 0, 0])


class DiscoveryTests(FakeRootTestCase):
    def test_no_device_is_a_plain_error(self):
        with self.assertRaises(NoDeviceError) as caught:
            LinuxSysfsBackend().list_zones()
        self.assertIn("README", str(caught.exception))

    def test_missing_leds_directory_is_the_same_error(self):
        with self.assertRaises(NoDeviceError):
            LinuxSysfsBackend(self.tmp / "nowhere").list_zones()

    def test_three_leds_map_to_left_centre_right(self):
        self.fake.add_three_zones()
        zones = LinuxSysfsBackend().list_zones()
        self.assertEqual([z.name for z in zones], ["left", "centre", "right"])
        self.assertTrue(all(z.has_color for z in zones))

    def test_suffix_order_is_numeric_not_text(self):
        for index in (10, 2, 1):
            self.fake.add_rgb(f"rgb:kbd_backlight_{index}")
        self.fake.add_rgb("rgb:kbd_backlight")
        backend = LinuxSysfsBackend()
        ordered = backend._scan()
        self.assertEqual(
            [led.path.name for led in ordered],
            ["rgb:kbd_backlight", "rgb:kbd_backlight_1",
             "rgb:kbd_backlight_2", "rgb:kbd_backlight_10"],
        )

    def test_unrelated_leds_are_ignored(self):
        self.fake.add_three_zones()
        self.assertEqual(len(LinuxSysfsBackend().list_zones()), 3)

    def test_one_zone_keyboard(self):
        self.fake.add_rgb("rgb:kbd_backlight")
        self.assertEqual([z.name for z in LinuxSysfsBackend().list_zones()], ["keyboard"])

    def test_white_only_keyboard_has_no_colour(self):
        self.fake.add_white("white:kbd_backlight")
        backend = LinuxSysfsBackend()
        self.assertFalse(backend.list_zones()[0].has_color)
        self.assertIsNone(backend.read_state().colors["keyboard"])
        with self.assertRaises(InvalidValueError):
            backend.set_color("keyboard", (1, 2, 3))


class ColourTests(FakeRootTestCase):
    def setUp(self):
        super().setUp()
        self.fake.add_three_zones()
        self.backend = LinuxSysfsBackend()

    def test_each_zone_gets_only_its_own_colour(self):
        self.backend.set_color("left", (255, 0, 0))
        self.backend.set_color("centre", (0, 255, 0))
        self.backend.set_color("right", (0, 0, 255))
        self.assertEqual(self.fake.intensity("rgb:kbd_backlight"), "255 0 0\n")
        self.assertEqual(self.fake.intensity("rgb:kbd_backlight_1"), "0 255 0\n")
        self.assertEqual(self.fake.intensity("rgb:kbd_backlight_2"), "0 0 255\n")

    def test_written_bytes_pass_the_kernel_rule_and_mean_what_we_said(self):
        for rgb in ((0, 0, 0), (255, 255, 255), (8, 9, 10), (1, 100, 255)):
            self.backend.set_color("left", rgb)
            data = self.fake.intensity("rgb:kbd_backlight").encode()
            self.assertTrue(kernel_accepts_multi_intensity(data), data)
            self.assertEqual(tuple(percent_i_values(data)), rgb)

    def test_channel_order_comes_from_multi_index(self):
        self.fake.add_rgb("x:kbd_backlight_3", channels="blue green red")
        backend = LinuxSysfsBackend(self.fake.root)
        names = [led.path.name for led in backend._scan()]
        self.assertIn("x:kbd_backlight_3", names)
        fourth = backend.list_zones()[3].name
        backend.set_color(fourth, (10, 20, 30))
        self.assertEqual(self.fake.intensity("x:kbd_backlight_3"), "30 20 10\n")
        self.assertEqual(backend.read_state().colors[fourth], (10, 20, 30))

    def test_intensity_scales_to_max_brightness(self):
        self.fake.add_rgb("y:kbd_backlight_4", max_brightness=100)
        backend = LinuxSysfsBackend()
        zone = backend.list_zones()[3].name
        backend.set_color(zone, (255, 0, 51))
        self.assertEqual(self.fake.intensity("y:kbd_backlight_4"), "100 0 20\n")

    def test_read_round_trips(self):
        self.backend.set_color("right", (18, 52, 86))
        self.assertEqual(self.backend.read_state().colors["right"], (18, 52, 86))

    def test_out_of_range_never_reaches_the_kernel(self):
        before = self.fake.snapshot()
        for rgb in ((256, 0, 0), (0, -1, 0)):
            with self.assertRaises(InvalidValueError):
                self.backend.set_color("left", rgb)
        self.assertEqual(self.fake.snapshot(), before)

    def test_unknown_zone_names_the_real_ones(self):
        with self.assertRaises(InvalidValueError) as caught:
            self.backend.set_color("middle", (1, 2, 3))
        self.assertIn("left, centre, right", str(caught.exception))


class BrightnessTests(FakeRootTestCase):
    def setUp(self):
        super().setUp()
        self.fake.add_three_zones()
        self.backend = LinuxSysfsBackend()

    def test_all_zones_receive_it(self):
        self.backend.set_brightness(128)
        for name in ("rgb:kbd_backlight", "rgb:kbd_backlight_1", "rgb:kbd_backlight_2"):
            self.assertEqual(self.fake.brightness(name), "128")
        self.assertEqual(self.backend.read_state().brightness, 128)

    def test_range_is_enforced(self):
        for value in (-1, 256):
            with self.assertRaises(InvalidValueError):
                self.backend.set_brightness(value)
        self.assertEqual(self.fake.brightness("rgb:kbd_backlight"), "0")

    def test_power_off_is_zero_and_on_restores_the_level(self):
        self.backend.set_power(True, 200)
        self.assertTrue(self.backend.read_state().on)
        self.backend.set_power(False, 200)
        self.assertFalse(self.backend.read_state().on)
        self.backend.set_power(True, 200)
        self.assertEqual(self.backend.read_state().brightness, 200)

    def global_brightness_writes(self, action):
        """Model the Clevo driver: a write to one zone updates all three."""
        writes = []
        real_write = LinuxSysfsBackend._write

        def fake_write(path, text):
            writes.append(path.parent.name)
            for name in ("rgb:kbd_backlight", "rgb:kbd_backlight_1", "rgb:kbd_backlight_2"):
                real_write(self.fake.leds / name / "brightness", text)

        with mock.patch.object(LinuxSysfsBackend, "_write", staticmethod(fake_write)):
            action()
        return writes

    def test_global_driver_needs_one_write_per_slider_step(self):
        writes = self.global_brightness_writes(lambda: self.backend.set_brightness(90))
        self.assertEqual(writes, ["rgb:kbd_backlight"])

    def test_refresh_writes_every_zone_even_when_values_match(self):
        self.backend.set_brightness(90)
        writes = self.global_brightness_writes(
            lambda: self.backend.set_brightness(90, refresh=True))
        self.assertEqual(len(writes), 3)


class PermissionTests(FakeRootTestCase):
    @unittest.skipIf(os.geteuid() == 0, "root ignores file modes")
    def test_read_only_attribute_gives_the_fix_not_a_traceback(self):
        self.fake.add_three_zones()
        attribute = self.fake.leds / "rgb:kbd_backlight" / "multi_intensity"
        attribute.chmod(0o444)
        with self.assertRaises(WriteDeniedError) as caught:
            LinuxSysfsBackend().set_color("left", (1, 2, 3))
        self.assertIn("install-system.sh", str(caught.exception))

    def test_a_missing_attribute_is_never_created(self):
        self.fake.add_three_zones()
        attribute = self.fake.leds / "rgb:kbd_backlight" / "multi_intensity"
        attribute.unlink()
        with self.assertRaises(NoDeviceError):
            LinuxSysfsBackend()._write(attribute, "1 2 3\n")
        self.assertFalse(attribute.exists())


class FactoryTests(unittest.TestCase):
    def test_linux_gets_the_sysfs_backend(self):
        self.assertIsInstance(create_backend("linux"), LinuxSysfsBackend)

    def test_windows_has_no_backend_yet_and_says_so(self):
        with self.assertRaises(UnsupportedPlatformError):
            create_backend("win32")


if __name__ == "__main__":
    unittest.main()
