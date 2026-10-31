"""The window. Thin by design: every action goes through Session.

Changes apply live. Slider and colour drags fire quickly and each one reaches
the firmware, so writes are coalesced on a short timer.
"""

from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QGridLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .backend import RGB
from .backends import create_backend
from .errors import ClevoKbdError
from .session import Session
from .state import format_color

WRITE_DELAY_MS = 40
SAVE_DELAY_MS = 500
PAGE_MESSAGE, PAGE_CONTROLS = 0, 1


def default_session() -> Session:
    return Session(create_backend())


class MainWindow(QMainWindow):
    def __init__(self, session_factory: Callable[[], Session] = default_session) -> None:
        super().__init__()
        self.setWindowTitle("Keyboard Backlight")
        self.session_factory = session_factory
        self.session: Session | None = None
        self.swatches: dict[str, QPushButton] = {}
        self.colors: dict[str, RGB] = {}
        self.pending_colors: dict[str, RGB] = {}
        self.pending_brightness: int | None = None
        self.picker_zone: str | None = None
        self.syncing = False

        self.write_timer = QTimer(self, singleShot=True, interval=WRITE_DELAY_MS)
        self.write_timer.timeout.connect(self.flush)
        self.save_timer = QTimer(self, singleShot=True, interval=SAVE_DELAY_MS)
        self.save_timer.timeout.connect(self.save)

        self.banner = QLabel(wordWrap=True, visible=False)
        self.banner.setObjectName("banner")
        self.pages = QStackedWidget()
        self.pages.addWidget(self.build_message_page())
        self.pages.addWidget(self.build_controls_page())
        layout = QVBoxLayout()
        layout.addWidget(self.banner)
        layout.addWidget(self.pages)
        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

        self.picker = QColorDialog(self)
        self.picker.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        self.picker.setOption(QColorDialog.ColorDialogOption.NoButtons)
        self.picker.setModal(False)
        self.picker.currentColorChanged.connect(self.on_picker_color)

        self.reload()

    def build_message_page(self) -> QWidget:
        self.message = QLabel(wordWrap=True, alignment=Qt.AlignmentFlag.AlignCenter)
        retry = QPushButton("Check again")
        retry.clicked.connect(self.reload)
        layout = QVBoxLayout()
        layout.addStretch()
        layout.addWidget(self.message)
        layout.addWidget(retry)
        layout.addStretch()
        page = QWidget()
        page.setLayout(layout)
        return page

    def build_controls_page(self) -> QWidget:
        self.power = QCheckBox("Backlight on")
        self.power.toggled.connect(self.on_power)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimumWidth(240)
        self.slider.valueChanged.connect(self.on_slider)
        self.level = QLabel()
        self.link = QCheckBox("Set all zones together")
        self.link.toggled.connect(self.on_link)
        self.zone_grid = QGridLayout()

        brightness = QGridLayout()
        brightness.addWidget(QLabel("Brightness"), 0, 0)
        brightness.addWidget(self.slider, 0, 1)
        brightness.addWidget(self.level, 0, 2)

        layout = QVBoxLayout()
        layout.addWidget(self.power)
        layout.addLayout(brightness)
        layout.addSpacing(12)
        layout.addLayout(self.zone_grid)
        layout.addWidget(self.link)
        layout.addStretch()
        page = QWidget()
        page.setLayout(layout)
        return page

    def reload(self) -> None:
        """Read everything from the hardware. Never writes to it."""
        self.clear_error()
        self.flush_pending_discard()
        try:
            self.session = self.session_factory()
            zones = self.session.zones()
            live = self.session.read()
        except ClevoKbdError as error:
            self.session = None
            self.message.setText(str(error))
            self.pages.setCurrentIndex(PAGE_MESSAGE)
            return
        if self.session.load_error:
            self.show_error(str(self.session.load_error))

        self.syncing = True
        self.slider.setRange(0, live.max_brightness)
        # Off reads as brightness 0, so show the level that "on" would return to.
        self.slider.setValue(live.brightness or self.session.saved_brightness)
        self.level.setText(str(self.slider.value()))
        self.power.setChecked(live.on)
        self.slider.setEnabled(live.on)
        self.link.setChecked(self.session.link_zones)
        self.link.setVisible(sum(zone.has_color for zone in zones) > 1)
        self.syncing = False

        while self.zone_grid.count():
            self.zone_grid.takeAt(0).widget().deleteLater()
        self.swatches.clear()
        self.colors.clear()
        for row, zone in enumerate(zone for zone in zones if zone.has_color):
            swatch = QPushButton()
            swatch.setFixedSize(72, 28)
            swatch.setAccessibleName(f"{zone.name} colour")
            swatch.clicked.connect(lambda _=False, name=zone.name: self.open_picker(name))
            self.zone_grid.addWidget(QLabel(zone.name.capitalize()), row, 0)
            self.zone_grid.addWidget(swatch, row, 1)
            self.swatches[zone.name] = swatch
            self.show_color(zone.name, live.colors[zone.name] or (0, 0, 0))
        self.pages.setCurrentIndex(PAGE_CONTROLS)

    def show_color(self, zone: str, rgb: RGB) -> None:
        self.colors[zone] = rgb
        self.swatches[zone].setStyleSheet(
            f"background-color: {format_color(rgb)}; border: 1px solid palette(mid);"
            " border-radius: 4px;"
        )

    def open_picker(self, zone: str) -> None:
        self.picker_zone = zone
        self.syncing = True
        self.picker.setCurrentColor(QColor(*self.colors[zone]))
        self.syncing = False
        self.picker.setWindowTitle(f"{zone.capitalize()} colour")
        self.picker.show()
        self.picker.raise_()
        self.picker.activateWindow()

    def on_picker_color(self, color: QColor) -> None:
        if self.syncing or self.picker_zone is None:
            return
        rgb = (color.red(), color.green(), color.blue())
        targets = list(self.swatches) if self.link.isChecked() else [self.picker_zone]
        for zone in targets:
            self.show_color(zone, rgb)
            self.pending_colors[zone] = rgb
        self.write_timer.start()

    def on_slider(self, value: int) -> None:
        self.level.setText(str(value))
        if not self.syncing:
            self.pending_brightness = value
            self.write_timer.start()

    def on_power(self, on: bool) -> None:
        self.slider.setEnabled(on)
        if self.syncing or self.session is None:
            return
        self.flush()
        self.perform(lambda: self.session.set_power(on))
        if on:
            # Nothing saved means "on" chose a level, so show the one it chose.
            self.syncing = True
            self.slider.setValue(self.session.saved_brightness)
            self.syncing = False

    def on_link(self, linked: bool) -> None:
        if not self.syncing and self.session is not None:
            self.perform(lambda: self.session.set_link_zones(linked))

    def flush(self) -> None:
        self.write_timer.stop()
        colors, self.pending_colors = self.pending_colors, {}
        brightness, self.pending_brightness = self.pending_brightness, None
        if self.session is None or (not colors and brightness is None):
            return

        def write() -> None:
            for zone, rgb in colors.items():
                self.session.set_color(zone, rgb)
            if brightness is not None:
                self.session.set_brightness(brightness)

        self.perform(write)

    def flush_pending_discard(self) -> None:
        self.write_timer.stop()
        self.pending_colors = {}
        self.pending_brightness = None

    def perform(self, action: Callable[[], None]) -> None:
        try:
            action()
        except ClevoKbdError as error:
            self.show_error(str(error))
        else:
            self.clear_error()
            self.save_timer.start()

    def save(self) -> None:
        if self.session is None:
            return
        try:
            self.session.save()
        except OSError as error:
            self.show_error(f"Could not save the settings: {error}")

    def show_error(self, text: str) -> None:
        self.banner.setText(text)
        self.banner.setVisible(True)

    def clear_error(self) -> None:
        self.banner.setVisible(False)

    def closeEvent(self, event) -> None:
        self.flush()
        self.save_timer.stop()
        self.save()
        self.picker.close()
        super().closeEvent(event)


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("clevo-kbd")
    app.setDesktopFileName("clevo-kbd")
    window = MainWindow()
    window.show()
    return app.exec()
