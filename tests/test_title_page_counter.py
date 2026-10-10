import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtWidgets import QApplication, QMainWindow

from ballontranslator.ui.mainwindowbars import TitleBar


def test_page_counter_uses_at_least_three_digits():
    assert TitleBar.pageCounterText(29, 53) == '029/053'
    assert TitleBar.pageCounterText(7, 1200) == '0007/1200'
    assert TitleBar.pageCounterText(0, 53) == ''


def test_title_includes_current_and_total_page_count():
    app = QApplication.instance() or QApplication([])
    window = QMainWindow()
    title_bar = TitleBar(window)

    title_bar.setTitleContent(
        proj_name='Sayu Runaway Diary',
        page_name='029_upscaled_2x.jpg',
        current_page=29,
        total_pages=53,
    )

    assert title_bar.titleLabel.text() == (
        'Sayu Runaway Diary - 029_upscaled_2x.jpg 029/053 pages'
    )
    title_bar.deleteLater()
    window.deleteLater()
    app.processEvents()
