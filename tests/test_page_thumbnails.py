import json
import os
import time
import gc
import weakref
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from threading import Event
from typing import Iterator

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PIL import Image
from qtpy.QtCore import QCoreApplication, QEvent, QThread
from qtpy.QtTest import QSignalSpy, QTest
from qtpy.QtWidgets import QApplication

from ballontranslator.ui.mainwindow import MainWindow, PageListView
from ballontranslator.ui.configpanel import ConfigPanel
from ballontranslator.ui.io_thread import PageThumbnailLoader
from ballontranslator.utils import shared
from ballontranslator.utils.config import ProgramConfig, json_dump_program_config, pcfg
from ballontranslator.utils.proj_imgtrans import ProjImgTrans


@pytest.fixture(scope='module')
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def thumbnail_config(monkeypatch) -> None:
    monkeypatch.setattr(pcfg, 'show_page_thumbnails', True)


@pytest.fixture
def view(app) -> Iterator[PageListView]:
    view = PageListView()
    yield view
    view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert PageThumbnailLoader.thread_pool().waitForDone(5000)
    app.processEvents()


def wait_for_preview(view: PageListView, row: int, color: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        image = view.item(row).icon().pixmap(view.iconSize()).toImage()
        if not image.isNull() and image.pixelColor(image.width() // 2, image.height() // 2).name() == color:
            return
        QTest.qWait(5)
    pytest.fail(f'Page {row} did not receive its thumbnail.')


def test_more_than_100_pages_keep_thumbnails(app, tmp_path: Path) -> None:
    source = tmp_path / '000.png'
    Image.new('RGB', (180, 300), '#e02040').save(source)
    image_bytes = source.read_bytes()
    for index in range(1, 101):
        (tmp_path / f'{index:03}.png').write_bytes(image_bytes)
    project = ProjImgTrans(str(tmp_path))
    view = PageListView()
    owner = SimpleNamespace(imgtrans_proj=project, pageList=view, llmContextEditor=Mock())
    try:
        MainWindow.updatePageList(owner)
        assert view.count() == 101
        wait_for_preview(view, 100, '#e02040')
    finally:
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        project.close_project_glossary()


def test_thumbnail_preference_defaults_and_round_trip() -> None:
    assert ProgramConfig().show_page_thumbnails is True
    config = ProgramConfig(show_page_thumbnails=False)
    loaded = ProgramConfig(**json.loads(json_dump_program_config(config)))
    assert loaded.show_page_thumbnails is False


@pytest.mark.parametrize('invalid', [None, 'false', 1, {}, []])
def test_invalid_thumbnail_preference_falls_back_without_losing_other_settings(invalid, caplog) -> None:
    config = ProgramConfig(show_page_thumbnails=invalid, show_page_list=True)
    assert config.show_page_thumbnails is True
    assert config.show_page_list is True
    assert 'show_page_thumbnails' in caplog.text


def test_checkbox_applies_immediately_without_changing_selected_or_ignored_page(view, tmp_path, app) -> None:
    Image.new('RGB', (600, 150), '#e02040').save(tmp_path / '001.png')
    Image.new('RGB', (150, 600), '#2040e0').save(tmp_path / '002.png')
    view.addItems(['001.png', '002.png'])
    view.setCurrentRow(1)
    view.setItemIgnored(view.item(0), True)
    view.loadThumbnails(str(tmp_path))
    wait_for_preview(view, 0, '#e02040')
    wait_for_preview(view, 1, '#2040e0')
    current = view.currentItem()
    selection_changes = QSignalSpy(view.currentItemChanged)
    panel = ConfigPanel()
    try:
        panel.setupConfig()
        panel.page_thumbnails_changed.connect(view.setThumbnailsVisible)
        changes = QSignalSpy(panel.page_thumbnails_changed)
        saves = QSignalSpy(panel.save_config)
        assert panel.page_thumbnails_checker.isChecked()
        panel.page_thumbnails_checker.click()
        assert pcfg.show_page_thumbnails is False
        assert all(view.item(row).icon().isNull() for row in range(view.count()))
        panel.page_thumbnails_checker.click()
        wait_for_preview(view, 1, '#2040e0')
        assert pcfg.show_page_thumbnails is True
        assert len(changes) == len(saves) == 2
        assert len(selection_changes) == 0
        assert view.currentItem() is current
        assert view.item(0).font().strikeOut()
    finally:
        panel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_disabled_previews_do_not_read_images_and_ignore_queued_results(view, tmp_path, app) -> None:
    Image.new('RGB', (30, 60), '#e02040').save(tmp_path / '001.png')
    view.addItem('001.png')
    view.setThumbnailsVisible(False)
    with patch.object(PageThumbnailLoader.thread_pool(), 'start') as start:
        view.loadThumbnails(str(tmp_path))
        start.assert_not_called()
    view.setThumbnailsVisible(True)
    # Leave emitted thumbnails queued until after the setting changes again.
    assert PageThumbnailLoader.thread_pool().waitForDone(5000)
    view.setThumbnailsVisible(False)
    app.processEvents()
    assert view.item(0).icon().isNull()


def test_project_switch_discards_old_result_for_same_page_name(view, tmp_path, app) -> None:
    Image.new('RGB', (30, 60), '#e02040').save(tmp_path / '001.png')
    view.addItem('001.png')
    view.loadThumbnails(str(tmp_path))
    assert PageThumbnailLoader.thread_pool().waitForDone(5000)
    view.clear()
    other = tmp_path / 'other'
    other.mkdir()
    (other / '001.png').write_bytes(b'corrupt image')
    view.addItem('001.png')
    view.loadThumbnails(str(other))
    assert PageThumbnailLoader.thread_pool().waitForDone(5000)
    app.processEvents()
    image = view.item(0).icon().pixmap(view.iconSize()).toImage()
    assert image.pixelColor(image.width() // 2, image.height() // 2).alpha() == 0


def test_decoding_runs_off_main_thread_and_survives_view_deletion(app, tmp_path) -> None:
    Image.new('RGB', (30, 60), '#e02040').save(tmp_path / '001.png')
    view = PageListView()
    view_ref = weakref.ref(view)
    view.addItem('001.png')
    started = Event()
    release = Event()
    cancelled = []
    threads = []
    run = PageThumbnailLoader.run

    def delayed_read(loader):
        threads.append(QThread.currentThread() is app.thread())
        started.set()
        if release.wait(5):
            cancelled.append(loader.cancelled.is_set())
            run(loader)

    with patch.object(PageThumbnailLoader, 'run', delayed_read):
        view.loadThumbnails(str(tmp_path))
        try:
            assert started.wait(5)
            view.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            del view
            gc.collect()
            assert view_ref() is None
        finally:
            release.set()
            assert PageThumbnailLoader.thread_pool().waitForDone(5000)
    app.processEvents()
    assert threads == [False]
    assert cancelled == [True]


def test_headless_mode_does_not_start_thumbnail_io(view, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(shared, 'HEADLESS', True)
    view.addItem('001.png')
    with patch.object(PageThumbnailLoader.thread_pool(), 'start') as start:
        view.loadThumbnails(str(tmp_path))
    start.assert_not_called()
    assert view.item(0).icon().isNull()


def test_corrupt_preview_does_not_prevent_other_previews(view, tmp_path) -> None:
    (tmp_path / '001.png').write_bytes(b'corrupt image')
    Image.new('RGB', (30, 60), '#2040e0').save(tmp_path / '002.png')
    view.addItems(['001.png', '002.png'])
    view.loadThumbnails(str(tmp_path))
    wait_for_preview(view, 1, '#2040e0')
    assert view.item(0).text() == '001.png'
