import os
import unittest
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QTextBrowser

from ballontranslator.ui.update_dialog import (
    RELEASE_WINDOW_WIDTH,
    UpdateReleaseDialog,
    format_release_markdown,
    select_release_note_section,
    simplified_release_date,
    strip_release_images,
)


def get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class UpdateReleaseDialogTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def test_strips_images_without_removing_release_markdown(self):
        markdown = strip_release_images(
            '<img src="https://example.invalid/demo.gif" />\n\n- Fixed UI\n\n![Demo](demo.png)'
        )

        self.assertEqual(markdown, '- Fixed UI')

    def test_formats_unordered_list_spacing(self):
        self.assertEqual(format_release_markdown('* Fixed UI'), '* \xa0Fixed UI')

    def test_selects_localized_section_and_removes_headings(self):
        markdown = (
            '## Changelog\n'
            '### Fixes\n'
            '- Fixed UI\n'
            '## 更新说明\n'
            '### 修复\n'
            '- 修复界面'
        )

        self.assertEqual(
            select_release_note_section(markdown, 'en_US'),
            '- Fixed UI',
        )
        self.assertEqual(
            select_release_note_section(markdown, 'zh_CN'),
            '- 修复界面',
        )
        self.assertEqual(
            select_release_note_section(markdown, 'zh-CN'),
            '- 修复界面',
        )

    def test_release_section_fallbacks_handle_missing_or_empty_content(self):
        self.assertEqual(
            select_release_note_section('## 更新说明\n- 修复界面', 'en_US'),
            '',
        )
        self.assertEqual(
            select_release_note_section('# Notes\n- Fixed UI', 'en_US'),
            '- Fixed UI',
        )
        self.assertEqual(select_release_note_section('## Changelog', 'en_US'), '')
        self.assertEqual(select_release_note_section('', 'zh_CN'), '')

    def test_localized_sections_are_boundaries_at_different_heading_levels(self):
        markdown = '# Changelog\n- Fixed UI\n### 更新说明\n- 修复界面'

        self.assertEqual(
            select_release_note_section(markdown, 'en_US'),
            '- Fixed UI',
        )
        self.assertEqual(
            select_release_note_section(markdown, 'zh_CN'),
            '- 修复界面',
        )

    def test_preview_dialog_has_only_a_safe_close_action(self):
        release_info = SimpleNamespace(
            tag_name='v1.5.6',
            name='v1.5.6',
            html_url='https://example.invalid/v1.5.6',
            body='',
            published_at='',
        )
        result = SimpleNamespace(
            current_version='1.5.6',
            latest_version='1.5.6',
            release_info=release_info,
        )

        dialog = UpdateReleaseDialog(result, allow_update=False)

        self.assertIsNotNone(dialog.findChild(QPushButton, 'UpdateDialogPrimaryButton'))
        self.assertIsNone(dialog.findChild(QPushButton, 'UpdateDialogCancelButton'))
        dialog.close()

    def test_release_source_link_targets_the_vibe_fork(self):
        release_info = SimpleNamespace(
            tag_name='v1.5.6',
            name='v1.5.6',
            html_url='',
            body='',
            published_at='',
        )
        result = SimpleNamespace(
            current_version='1.5.5',
            latest_version='1.5.6',
            release_info=release_info,
        )
        dialog = UpdateReleaseDialog(result, display_language='zh_CN')
        message = dialog.findChild(QLabel, 'UpdateReleaseSourceMessage')

        self.assertIsNotNone(message)
        self.assertIn(
            'https://github.com/CoSciBlog/BallonsTranslator-vibe/releases',
            message.text(),
        )
        self.assertNotIn('dmMaze', message.text())
        self.assertNotIn('patreon', message.text())
        self.assertNotIn('afdian', message.text())
        dialog.close()


if __name__ == '__main__':
    unittest.main()
