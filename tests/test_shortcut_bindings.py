import ast
import unittest
from collections import Counter
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]


def _named_key_sequences(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    sequences = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "QKeySequence":
            continue
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
            continue
        if isinstance(node.args[0].value, str):
            sequences.append(node.args[0].value)
    return sequences


class ShortcutBindingsTest(unittest.TestCase):
    def test_custom_mainwindow_shortcuts_are_not_registered_twice(self):
        sequences = []
        for relative_path in ("ui/mainwindow.py", "ui/mainwindowbars.py"):
            sequences.extend(_named_key_sequences(APP_ROOT / relative_path))

        duplicates = {
            key: count for key, count in Counter(sequences).items() if count > 1
        }
        self.assertEqual(duplicates, {})

    def test_tools_actions_are_connected_to_mainwindow_handlers(self):
        source = (APP_ROOT / "ui/mainwindow.py").read_text(encoding="utf-8")
        expected_connections = (
            "self.titleBar.merge_tool_trigger.connect(self.on_open_merge_tool)",
            "self.titleBar.reinpaint_current_page_trigger.connect(self.run_reinpaint_current_page)",
            "self.titleBar.optimize_inpaint_current_page_trigger.connect(self.run_inpaint_optimize_current_page)",
            "self.titleBar.remove_current_page_masks_trigger.connect(self.remove_current_page_masks)",
        )

        for connection in expected_connections:
            with self.subTest(connection=connection):
                self.assertIn(connection, source)

    def test_tools_menu_owns_documented_shortcuts(self):
        source = (APP_ROOT / "ui/mainwindowbars.py").read_text(encoding="utf-8")
        expected_shortcuts = (
            "mergeToolAction.setShortcut(QKeySequence('Ctrl+Shift+M'))",
            "reinpaintAction.setShortcut(QKeySequence('Ctrl+Shift+I'))",
            "optimizeInpaintCurrentAction.setShortcut(QKeySequence('Ctrl+Alt+I'))",
            "removeMasksAction.setShortcut(QKeySequence('Ctrl+Shift+Backspace'))",
        )

        for shortcut in expected_shortcuts:
            with self.subTest(shortcut=shortcut):
                self.assertIn(shortcut, source)

    def test_page_list_shortcut_is_bound_to_toggle_handler(self):
        source = (APP_ROOT / "ui/mainwindow.py").read_text(encoding="utf-8")

        self.assertIn('shortcutPageList = QShortcut(QKeySequence("Ctrl+Shift+P"), self)', source)
        self.assertIn("shortcutPageList.activated.connect(self.shortcutPageList)", source)


if __name__ == "__main__":
    unittest.main()
