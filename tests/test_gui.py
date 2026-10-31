"""Drives the real window under Qt's offscreen platform.

Offscreen opens no display connection, so this cannot touch a running desktop.
"""

import json
import os
import unittest
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from clevo_kbd.gui import PAGE_CONTROLS, PAGE_MESSAGE, MainWindow  # noqa: E402
from tests.fake_sysfs import DRIVER_ZONE_LEDS, FakeRootTestCase  # noqa: E402

LEFT, CENTRE, RIGHT = DRIVER_ZONE_LEDS
SETTLE_MS = 120


class GuiTestCase(FakeRootTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self):
        window = MainWindow()
        window.show()
        self.addCleanup(window.close)
        QTest.qWait(10)
        return window

    def pick(self, window, zone, color):
        """Click the zone's swatch, then choose a colour in the live dialog."""
        QTest.mouseClick(window.swatches[zone], Qt.MouseButton.LeftButton)
        QTest.qWait(10)
        window.picker.setCurrentColor(QColor(color))
        QTest.qWait(SETTLE_MS)


class ControlsTests(GuiTestCase):
    def setUp(self):
        super().setUp()
        self.fake.add_three_zones()

    def test_opening_the_window_writes_nothing(self):
        before = self.fake.snapshot()
        window = self.window()
        QTest.qWait(SETTLE_MS)
        window.close()
        self.assertEqual(self.fake.snapshot(), before)
        self.assertFalse(self.state_file.exists())

    def test_it_shows_three_zones_in_order(self):
        window = self.window()
        self.assertEqual(window.pages.currentIndex(), PAGE_CONTROLS)
        self.assertEqual(list(window.swatches), ["left", "centre", "right"])

    def test_picking_a_colour_applies_live_to_one_zone(self):
        window = self.window()
        self.pick(window, "left", "#123456")
        self.assertEqual(self.fake.intensity(LEFT), "18 52 86\n")
        self.assertEqual(self.fake.intensity(CENTRE), "255 255 255\n")
        self.assertTrue(window.picker.isVisible())

    def test_dragging_through_colours_coalesces_to_the_last(self):
        window = self.window()
        QTest.mouseClick(window.swatches["right"], Qt.MouseButton.LeftButton)
        real_set_color = window.session.set_color
        with mock.patch.object(window.session, "set_color", side_effect=real_set_color) as writes:
            for value in range(0, 200, 20):
                window.picker.setCurrentColor(QColor(value, 0, 0))
            QTest.qWait(SETTLE_MS)
        self.assertEqual(writes.call_count, 1)
        self.assertEqual(self.fake.intensity(RIGHT), "180 0 0\n")

    def test_link_sets_all_three(self):
        window = self.window()
        QTest.mouseClick(window.link, Qt.MouseButton.LeftButton)
        self.assertTrue(window.link.isChecked())
        self.pick(window, "centre", "#00ff00")
        for name in DRIVER_ZONE_LEDS:
            self.assertEqual(self.fake.intensity(name), "0 255 0\n")

    def test_slider_applies_live(self):
        window = self.window()
        window.power.setChecked(True)
        QTest.qWait(10)
        window.slider.setValue(64)
        QTest.qWait(SETTLE_MS)
        for name in DRIVER_ZONE_LEDS:
            self.assertEqual(self.fake.brightness(name), "64")
        self.assertEqual(window.level.text(), "64")

    def test_switch_turns_off_and_back_to_the_same_level(self):
        window = self.window()
        window.power.setChecked(True)
        window.slider.setValue(90)
        QTest.qWait(SETTLE_MS)
        window.power.setChecked(False)
        self.assertEqual(self.fake.brightness(LEFT), "0")
        self.assertFalse(window.slider.isEnabled())
        window.power.setChecked(True)
        self.assertEqual(self.fake.brightness(LEFT), "90")
        self.assertEqual(window.slider.value(), 90)

    def test_switching_on_with_nothing_saved_shows_the_level_it_chose(self):
        window = self.window()
        window.power.setChecked(True)
        self.assertEqual(self.fake.brightness(LEFT), "255")
        self.assertEqual(window.slider.value(), 255)

    def test_closing_saves_a_change_made_just_before(self):
        window = self.window()
        self.pick(window, "left", "#abcdef")
        window.close()
        self.assertEqual(json.loads(self.state_file.read_text())["colors"]["left"], "#abcdef")

    def test_closing_inside_the_write_delay_still_applies_the_change(self):
        window = self.window()
        QTest.mouseClick(window.swatches["left"], Qt.MouseButton.LeftButton)
        window.picker.setCurrentColor(QColor("#fedcba"))
        self.assertTrue(window.write_timer.isActive())
        window.close()
        self.assertEqual(self.fake.intensity(LEFT), "254 220 186\n")
        self.assertEqual(json.loads(self.state_file.read_text())["colors"]["left"], "#fedcba")

    def test_a_reopened_window_shows_the_saved_level_while_off(self):
        window = self.window()
        window.power.setChecked(True)
        window.slider.setValue(33)
        QTest.qWait(SETTLE_MS)
        window.power.setChecked(False)
        window.close()
        again = self.window()
        self.assertFalse(again.power.isChecked())
        self.assertEqual(again.slider.value(), 33)

    def test_screenshot_for_a_human(self):
        window = self.window()
        window.power.setChecked(True)
        self.pick(window, "left", "#ff0000")
        self.pick(window, "centre", "#00ff00")
        self.pick(window, "right", "#0000ff")
        window.picker.hide()
        window.slider.setValue(128)
        QTest.qWait(SETTLE_MS)
        target = os.environ.get("CLEVO_KBD_SCREENSHOT")
        if target:
            self.assertTrue(window.grab().save(target))


class NoDeviceTests(GuiTestCase):
    def test_it_explains_instead_of_crashing_and_can_recheck(self):
        window = self.window()
        self.assertEqual(window.pages.currentIndex(), PAGE_MESSAGE)
        self.assertIn("No keyboard backlight LED device", window.message.text())
        target = os.environ.get("CLEVO_KBD_SCREENSHOT_EMPTY")
        if target:
            self.assertTrue(window.grab().save(target))
        self.fake.add_three_zones()
        window.reload()
        self.assertEqual(window.pages.currentIndex(), PAGE_CONTROLS)


class WriteFailureTests(GuiTestCase):
    @unittest.skipIf(os.geteuid() == 0, "root ignores file modes")
    def test_a_denied_write_shows_the_fix_and_saves_nothing(self):
        self.fake.add_three_zones()
        (self.fake.leds / LEFT / "multi_intensity").chmod(0o444)
        window = self.window()
        self.pick(window, "left", "#ff0000")
        self.assertTrue(window.banner.isVisible())
        self.assertIn("install-system.sh", window.banner.text())
        window.close()
        self.assertFalse(self.state_file.exists())


if __name__ == "__main__":
    unittest.main()
