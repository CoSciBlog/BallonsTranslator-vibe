import json
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtCore import QRect
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import QApplication, QMainWindow

from ballontranslator.ui.mainwindow import (
    capture_main_window_placement,
    restore_main_window_placement,
)
from ballontranslator.utils.config import ProgramConfig, json_dump_program_config


class MainWindowPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_normal_window_geometry_and_state_round_trip(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        width = min(720, max(320, screen.width() - 80))
        height = min(540, max(240, screen.height() - 80))
        expected = QRect(
            screen.left() + 30,
            screen.top() + 30,
            width,
            height,
        )
        config = ProgramConfig()
        source = QMainWindow()
        source.setGeometry(expected)

        capture_main_window_placement(source, config)

        self.assertEqual(config.main_window_geometry, [
            expected.x(), expected.y(), expected.width(), expected.height(),
        ])
        self.assertFalse(config.main_window_maximized)
        restored_config = ProgramConfig(**json.loads(
            json_dump_program_config(config)
        ))
        target = QMainWindow()
        should_maximize = restore_main_window_placement(target, restored_config)
        self.assertFalse(should_maximize)
        self.assertEqual(target.geometry(), expected)

    def test_maximized_window_preserves_its_normal_geometry(self) -> None:
        config = ProgramConfig()
        window = QMainWindow()
        window.setGeometry(40, 50, 640, 480)
        window.showMaximized()
        self.app.processEvents()

        capture_main_window_placement(window, config)

        self.assertTrue(config.main_window_maximized)
        self.assertGreater(config.main_window_geometry[2], 0)
        self.assertGreater(config.main_window_geometry[3], 0)
        window.close()

    def test_missing_monitor_position_is_moved_onto_available_screen(self) -> None:
        config = ProgramConfig(
            main_window_geometry=[100000, 100000, 640, 480],
            main_window_maximized=False,
        )
        window = QMainWindow()

        restore_main_window_placement(window, config)

        self.assertTrue(any(
            screen.availableGeometry().intersects(window.geometry())
            for screen in QGuiApplication.screens()
        ))

    def test_invalid_saved_placement_uses_legacy_maximized_default(self) -> None:
        config = ProgramConfig(
            main_window_geometry=[10, 20, -1, 500],
            main_window_maximized='yes',
        )
        self.assertEqual(config.main_window_geometry, [])
        self.assertTrue(config.main_window_maximized)


if __name__ == '__main__':
    unittest.main()
