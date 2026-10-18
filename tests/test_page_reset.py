import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
import pytest
from qtpy.QtCore import QCoreApplication, QEvent, QThread
from qtpy.QtGui import QContextMenuEvent, QImage, QPainter, QUndoCommand
from qtpy.QtWidgets import QApplication, QMessageBox, QWidget

from ballontranslator.ui import shared_widget as SW
from ballontranslator.ui.canvas import Canvas
from ballontranslator.ui.mainwindow import MainWindow, PageListView
from ballontranslator.ui.text_engine.editing.manager import SceneTextManager, TextPanel
from ballontranslator.utils import config as C, shared
from ballontranslator.utils.config import RunStatus
from ballontranslator.utils.fontformat import FontFormat
from ballontranslator.utils.io_utils import imwrite
from ballontranslator.utils.proj_imgtrans import ProjImgTrans, ImgnameNotInProjectException
from ballontranslator.utils.textblock import TextBlock


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def project(tmp_path):
    original = np.full((160, 240, 3), 230, dtype=np.uint8)
    for name in ('001.png', '002.png'):
        imwrite(str(tmp_path / name), original, ext='.png')
    project = ProjImgTrans(str(tmp_path))
    for name in project.pages:
        project.pages[name] = [TextBlock(
            [10, 10, 200, 100], _bounding_rect=[10, 10, 190, 90],
            text=['source'], translation='translation',
        )]
        project.set_page_progress(name, RunStatus.FIN_ALL)
        project.mark_translation_finished(name, 'English')
        project.set_llm_visual_summary_text(name, 'A scene.')
        project.save_mask(name, np.full((160, 240), 255, dtype=np.uint8))
        project.save_inpainted(name, np.zeros_like(original))
        Path(project.result_dir()).mkdir(exist_ok=True)
        imwrite(project.get_result_path(name), original, ext='.png')
    project.set_page_ignored('001.png', True)
    project.set_current_img('001.png')
    project.save()
    yield project
    project.close_project_glossary()


@pytest.mark.parametrize('page_name', ['001.png', '002.png'])
def test_reset_is_page_specific_and_survives_reload(project, page_name):
    root = Path(project.directory)
    original_bytes = (root / page_name).read_bytes()
    other = '002.png' if page_name == '001.png' else '001.png'
    other_files = {path: Path(path).read_bytes() for path in project._generated_page_outputs(other)}
    other_blocks = project.pages[other][:]
    target_blocks = project.pages[page_name]
    # Previous output formats must not become visible again after reset.
    alternate = Path(project.inpainted_dir()) / (Path(page_name).stem + '.webp')
    alternate.write_bytes(b'older generated output')
    note = Path(project.inpainted_dir()) / (Path(page_name).stem + '.txt')
    note.write_text('user note')

    backup = Path(project.reset_page_data(page_name))

    assert project.pages[page_name] is target_blocks
    assert target_blocks == []
    assert project.pages[other] == other_blocks
    assert all(Path(path).read_bytes() == data for path, data in other_files.items())
    assert (root / page_name).read_bytes() == original_bytes
    assert note.read_text() == 'user note'
    assert not list(project._generated_page_outputs(page_name))
    assert (backup / 'inpainted' / alternate.name).read_bytes() == b'older generated output'
    snapshot = json.loads((backup / Path(project.proj_path).name).read_text(encoding='utf-8'))
    assert snapshot['pages'][page_name][0]['translation'] == 'translation'
    assert project._image_info[page_name]['finish_code'] == 0
    assert project.get_llm_visual_summary(page_name) is None
    assert 'translation_target' not in project._image_info[page_name]
    assert project.is_page_ignored('001.png')
    if page_name == project.current_img:
        assert not project.mask_array.any()
        np.testing.assert_array_equal(project.inpainted_array, project.img_array)

    with patch.object(shared, 'FUZZY_MATCH_IMAGE_NAME', True):
        project.load_from_json(project.proj_path)
        project.set_current_img(page_name)
    assert project.pages[page_name] == []
    assert not project.mask_array.any()
    np.testing.assert_array_equal(project.inpainted_array, project.img_array)


@pytest.mark.parametrize('failure', ['save', 'move'])
def test_reset_failure_restores_metadata_files_and_current_pixels(project, failure):
    old_json = Path(project.proj_path).read_bytes()
    blocks = project.pages['001.png'][:]
    metadata = project._image_info['001.png'].copy()
    files = {path: Path(path).read_bytes() for path in project._generated_page_outputs('001.png')}
    mask = project.mask_array.copy()
    inpainted = project.inpainted_array.copy()
    real_replace = os.replace

    def replace(source, target):
        if str(source) == project.get_inpainted_path('001.png'):
            raise PermissionError('locked image')
        real_replace(source, target)

    failing = patch.object(project, 'save', side_effect=OSError('disk full')) if failure == 'save' else patch(
        'ballontranslator.utils.proj_imgtrans.os.replace', side_effect=replace,
    )
    with failing, pytest.raises(OSError):
        project.reset_page_data('001.png')

    assert project.pages['001.png'] == blocks
    assert project._image_info['001.png'] == metadata
    assert Path(project.proj_path).read_bytes() == old_json
    assert all(Path(path).read_bytes() == data for path, data in files.items())
    np.testing.assert_array_equal(project.mask_array, mask)
    np.testing.assert_array_equal(project.inpainted_array, inpainted)


def test_failed_file_restore_keeps_recoverable_backup_and_restores_other_files(project):
    real_replace = os.replace
    mask = Path(project.get_mask_path('001.png'))

    def replace(source, target):
        if str(target) == str(mask):
            raise PermissionError('locked restore target')
        real_replace(source, target)

    with patch.object(project, 'save', side_effect=OSError('disk full')), patch(
        'ballontranslator.utils.proj_imgtrans.os.replace', side_effect=replace,
    ), pytest.raises(RuntimeError, match='Backup:'):
        project.reset_page_data('001.png')
    backup = next(Path(project.directory).glob('.page_reset_backup_*'))
    assert (backup / 'mask' / mask.name).exists()
    assert Path(project.get_inpainted_path('001.png')).exists()
    assert Path(project.get_result_path('001.png')).exists()
    assert project.pages['001.png']


@pytest.mark.parametrize('invalid', [None, 1, 'yes', {}])
def test_loading_invalid_reset_marker_discards_only_marker(project, invalid):
    project._image_info['001.png']['inpainted_reset'] = invalid
    # Round-trip through the production serializer, retaining a pre-load copy.
    project.save()
    before = Path(project.proj_path).read_bytes()
    project.load_from_json(project.proj_path)
    assert 'inpainted_reset' not in project._image_info['001.png']
    assert project.pages['001.png'][0].translation == 'translation'
    assert Path(project.proj_path).read_bytes() == before


def test_unknown_page_does_not_create_backup(project):
    with pytest.raises(ImgnameNotInProjectException):
        project.reset_page_data('missing.png')
    assert not list(Path(project.directory).glob('.page_reset_backup_*'))


def test_reset_refuses_shared_output_names(project):
    project.pages['001.jpg'] = []
    with pytest.raises(ValueError, match='same base filename'):
        project.reset_page_data('001.png')
    assert project.pages['001.png']
    assert Path(project.get_mask_path('001.png')).exists()
    assert not list(Path(project.directory).glob('.page_reset_backup_*'))


def test_context_menu_resets_clicked_page(app):
    pages = PageListView()
    pages.addItems(['001.png', '002.png'])
    pages.setCurrentRow(0)
    pages.show()
    app.processEvents()
    requested = []
    pages.reset_page_requested.connect(requested.append)

    def choose_reset(menu, position):
        return next(action for action in menu.actions() if action.text() == 'Reset page data...')

    point = pages.visualItemRect(pages.item(1)).center()
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, pages.mapToGlobal(point))
    with patch('ballontranslator.ui.mainwindow.QMenu.exec_', choose_reset):
        pages.contextMenuEvent(event)
    assert requested == ['002.png']
    assert pages.currentItem().text() == '001.png'
    pages.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class _ResetWindow(QWidget):
    on_reset_page_data = MainWindow.on_reset_page_data


@pytest.fixture
def window(app, project, monkeypatch):
    host = _ResetWindow()
    host.imgtrans_proj = project
    host.canvas = Canvas(host)
    host.canvas.editor_index = 1
    host.canvas.imgtrans_proj = project
    monkeypatch.setattr(SW, 'canvas', host.canvas)
    monkeypatch.setattr(shared, 'register_view_widget', Mock(), raising=False)
    monkeypatch.setattr(C, 'active_format', C.active_format)
    panel = TextPanel(app, host)
    panel.formatpanel.global_format = FontFormat()
    host.st_manager = SceneTextManager(app, host, host.canvas, panel, parent=host)
    host.canvas.updateCanvas()
    host.st_manager.populateSceneTextitems()
    host.module_manager = Mock(pipelineBusy=Mock(return_value=False))
    host.imsave_thread = Mock(isRunning=Mock(return_value=False), im_save_list=[])
    for name in ('project_upscale_thread', 'auto_tate_chu_yoko_thread', 'import_doc_thread', 'export_doc_thread'):
        setattr(host, name, Mock(isRunning=Mock(return_value=False)))
    host.global_search_widget = Mock(replace_thread=Mock(isRunning=Mock(return_value=False)))
    host.llmContextEditor = Mock()
    host.drawingPanel = Mock()
    host._batch_options = host._pending_reinpaint_request = host._pending_project_upscale = None
    host._llm_context_dirty = False
    host.page_changing = False
    yield host
    host.canvas.clear_undostack(update_saved_step=True)
    host.st_manager.clearSceneTextitems()
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.mark.parametrize('page_name', ['001.png', '002.png'])
def test_ui_reset_clears_only_target_and_runs_io_off_main_thread(window, project, page_name):
    canvas = window.canvas
    canvas.push_undo_command(QUndoCommand('prior edit'))
    drawing = QImage(20, 20, QImage.Format.Format_ARGB32)
    drawing.fill(0xFFFF0000)
    canvas.drawingLayer.addQImage(0, 0, drawing, QPainter.CompositionMode.CompositionMode_SourceOver, 'manual')
    assert canvas.drawingLayer.drawed()
    old_items = window.st_manager.textblk_item_list[:]
    old_mask = project.mask_array.copy()
    executed_on = []
    reset = project.reset_page_data

    def record_thread(page):
        executed_on.append(QThread.currentThread() is window.thread())
        return reset(page)

    with patch.object(project, 'reset_page_data', side_effect=record_thread), patch(
        'ballontranslator.ui.mainwindow.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes,
    ), patch('ballontranslator.ui.mainwindow.create_info_dialog'):
        window.on_reset_page_data(page_name)

    assert executed_on == [False]
    assert project.pages[page_name] == []
    if page_name == project.current_img:
        assert not window.st_manager.textblk_item_list
        assert not window.st_manager.pairwidget_list
        assert not canvas.text_undo_stack.canUndo()
        assert not canvas.projstate_unsaved
        assert not canvas.text_change_unsaved()
        assert not canvas.drawingLayer.drawed()
        np.testing.assert_array_equal(project.inpainted_array, project.img_array)
    else:
        assert window.st_manager.textblk_item_list == old_items
        assert canvas.text_undo_stack.canUndo()
        assert canvas.drawingLayer.drawed()
        np.testing.assert_array_equal(project.mask_array, old_mask)


@pytest.mark.parametrize('blocked', ['cancel', 'pipeline', 'saving'])
def test_ui_cancel_and_busy_keep_page_data(window, project, blocked):
    window.module_manager.pipelineBusy.return_value = blocked == 'pipeline'
    window.imsave_thread.isRunning.return_value = blocked == 'saving'
    answer = QMessageBox.StandardButton.No if blocked == 'cancel' else QMessageBox.StandardButton.Yes
    before = Path(project.proj_path).read_bytes()
    with patch('ballontranslator.ui.mainwindow.QMessageBox.question', return_value=answer), patch(
        'ballontranslator.ui.mainwindow.create_info_dialog',
    ):
        window.on_reset_page_data('001.png')
    assert project.pages['001.png']
    assert Path(project.proj_path).read_bytes() == before
    assert not list(Path(project.directory).glob('.page_reset_backup_*'))


def test_ui_failure_reports_error_and_keeps_scene_and_history(window, project):
    old_items = window.st_manager.textblk_item_list[:]
    window.canvas.push_undo_command(QUndoCommand('prior edit'))
    with patch.object(project, 'save', side_effect=OSError('disk full')), patch(
        'ballontranslator.ui.mainwindow.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes,
    ), patch('ballontranslator.ui.mainwindow.create_error_dialog') as report, patch(
        'ballontranslator.ui.mainwindow.create_info_dialog',
    ) as success:
        window.on_reset_page_data('001.png')
    report.assert_called_once()
    success.assert_not_called()
    assert window.st_manager.textblk_item_list == old_items
    assert window.canvas.text_undo_stack.canUndo()
    assert project.pages['001.png']
