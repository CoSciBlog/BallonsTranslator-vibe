import os.path as osp
import json
import os, re, shutil, traceback, sys
import numpy as np
from typing import List, Union
from pathlib import Path
import subprocess
from functools import partial
from copy import deepcopy
import time
import cv2

from tqdm import tqdm
from qtpy.QtWidgets import QAction, QFileDialog, QMenu, QHBoxLayout, QVBoxLayout, QApplication, QStackedWidget, QSplitter, QListWidget, QShortcut, QListWidgetItem, QMessageBox, QTextEdit, QPlainTextEdit, QDialog
from qtpy.QtCore import Qt, QPoint, QSize, QEvent, Signal, QThread, QTimer, QUrl
from qtpy.QtGui import QContextMenuEvent, QTextCursor, QGuiApplication, QIcon, QCloseEvent, QKeySequence, QKeyEvent, QPainter, QClipboard, QImage, QColor, QBrush

from utils.logger import logger as LOGGER
from utils.text_processing import is_cjk, full_len, half_len
from utils.imgproc_utils import enlarge_window
from utils.textblock import TextBlock, TextAlignment
from utils import shared
from utils.message import create_error_dialog, create_info_dialog
from utils.glossary_replacement import (
    apply_glossary_replacements_to_text,
    build_glossary_replacements,
)
from utils.glossary_template import (
    build_glossary_from_project_text,
    collect_project_translation_pairs,
    merge_glossary_entry_text,
)
from modules.translators.trans_chatgpt import GPTTranslator
from modules.translators.trans_llm_api import LLM_API_Translator
from modules.translators import TRANSLATORS, lang_display_label, lang_display_to_key
from modules import GET_VALID_TEXTDETECTORS, GET_VALID_INPAINTERS, GET_VALID_TRANSLATORS, GET_VALID_OCR
from .misc import parse_stylesheet, set_html_family, QKEY
from utils.config import ProgramConfig, pcfg, save_config, text_styles, save_text_styles, load_textstyle_from, FontFormat
from utils.reinpaint import combine_inpaint_masks, mask_bounding_rect
from utils.proj_imgtrans import ProjImgTrans
from utils.archive_import import (
    ARCHIVE_EXT,
    IMPORT_METADATA,
    ArchiveImportError,
    collect_importable_sources,
    has_importable_sources,
    import_archive_to_project,
    import_sources_to_project,
    is_archive_path,
)
from utils.archive_export import archive_export_filter, default_export_path, export_project
from utils.io_utils import IMG_EXT, find_all_imgs
from utils.batch_processing import collect_batch_project_dirs
from utils.upscale import filename_has_upscale_marker
from .canvas import Canvas
from .configpanel import ConfigPanel
from .module_manager import ModuleManager
from .textedit_area import SourceTextEdit, SelectTextMiniMenu, TransTextEdit
from .drawingpanel import DrawingPanel
from .scenetext_manager import SceneTextManager, TextPanel, PasteSrcItemsCommand
from .mainwindowbars import TitleBar, LeftBar, BottomBar
from .io_thread import (
    BatchProjectUpscaleThread,
    ExportDocThread,
    ImgSaveThread,
    ImportDocThread,
    ProjectUpscaleThread,
)
from .custom_widget import Widget, ViewWidget
from .global_search_widget import GlobalSearchWidget
from .glossary_widget import GlossaryWindow
from .translation_benchmark import TranslationBenchmarkWindow
from .model_downloads import ModelDownloadWindow
from .batch_processing_dialog import BatchProcessingDialog, BatchProcessingOptions
from .input_wheel_guard import InputWheelGuard
from .textedit_commands import GlobalRepalceAllCommand
from .framelesswindow import FramelessWindow, FramelessMoveResize
from .drawing_commands import RunBlkTransCommand, RemoveAllMasksCommand
from .keywordsubwidget import KeywordSubWidget
from . import shared_widget as SW
from .custom_widget import MessageBox, FrameLessMessageBox, ImgtransProgressMessageBox

class PageListView(QListWidget):

    reveal_file = Signal(str)
    toggle_ignore_page = Signal(str)
    delete_page_data = Signal(str)
    PAGE_NAME_ROLE = Qt.ItemDataRole.UserRole
    PAGE_IGNORED_ROLE = Qt.ItemDataRole.UserRole + 1
    PAGE_GROUP_ROLE = Qt.ItemDataRole.UserRole + 2
    PAGE_SOURCE_TYPE_ROLE = Qt.ItemDataRole.UserRole + 3

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setIconSize(QSize(shared.PAGELIST_THUMBNAIL_SIZE, shared.PAGELIST_THUMBNAIL_SIZE))
        self.setSpacing(4)

    def contextMenuEvent(self, e: QContextMenuEvent):
        item = self.itemAt(e.pos())
        if item is None:
            return super().contextMenuEvent(e)
        self.setCurrentItem(item)
        page_name = item.data(self.PAGE_NAME_ROLE) or item.text()
        ignored = bool(item.data(self.PAGE_IGNORED_ROLE))
        menu = QMenu()
        reveal_act = menu.addAction(self.tr('Reveal in File Explorer'))
        
        ignore_label = self.tr('Include Page in Pipeline') if ignored else self.tr('Ignore Page in Pipeline')
        ignore_act = menu.addAction(ignore_label)
        ignore_act.setToolTip(self.tr('Skip this page during text detection, OCR, translation, and inpainting pipeline runs.'))
        
        delete_data_act = menu.addAction(self.tr('Delete Page Data'))
        delete_data_act.setToolTip(self.tr('Delete textboxes, masks, and inpainting for this page.'))
        
        rst = menu.exec_(e.globalPos())

        if rst == reveal_act:
            self.reveal_file.emit(page_name)
        elif rst == ignore_act:
            self.toggle_ignore_page.emit(page_name)
        elif rst == delete_data_act:
            self.delete_page_data.emit(page_name)

mainwindow_cls = Widget if (shared.HEADLESS or shared.HEADLESS_CONTINUOUS) else FramelessWindow
class MainWindow(mainwindow_cls):

    imgtrans_proj: ProjImgTrans = ProjImgTrans()
    save_on_page_changed = True
    opening_dir = False
    page_changing = False
    postprocess_mt_toggle = True

    translator = None

    restart_signal = Signal()
    create_errdialog = Signal(str, str, str)
    create_infodialog = Signal(dict)
    
    def __init__(self, app: QApplication, config: ProgramConfig, open_dir='', **exec_args) -> None:
        super().__init__()

        shared.create_errdialog_in_mainthread = self.create_errdialog.emit
        self.create_errdialog.connect(self.on_create_errdialog)
        shared.create_infodialog_in_mainthread = self.create_infodialog.emit
        self.create_infodialog.connect(self.on_create_infodialog)
        shared.register_view_widget = self.register_view_widget

        self.app = app
        self.input_wheel_guard = InputWheelGuard(self)
        self.app.installEventFilter(self.input_wheel_guard)
        self.backup_blkstyles = []
        self._run_imgtrans_wo_textstyle_update = False

        self.setupThread()
        self.setupUi()
        self.setupConfig()
        self.setupShortcuts()
        self.setupRegisterWidget()
        # self.showMaximized()
        FramelessMoveResize.toggleMaxState(self)
        self.setAcceptDrops(True)

        if open_dir != '' and osp.exists(open_dir):
            self.OpenProj(open_dir)
        elif pcfg.open_recent_on_startup:
            if len(self.leftBar.recent_proj_list) > 0:
                proj_dir = self.leftBar.recent_proj_list[0]
                if osp.exists(proj_dir):
                    self.OpenProj(proj_dir)

        if shared.HEADLESS or shared.HEADLESS_CONTINUOUS:
            self.run_batch(**exec_args)

        if shared.ON_MACOS:
            # https://bugreports.qt.io/browse/QTBUG-133215
            self.hideSystemTitleBar()
            self.showMaximized()

    def setStyleSheet(self, styleSheet: str) -> None:
        self.imgtrans_progress_msgbox.setStyleSheet(styleSheet)
        self.export_doc_thread.progress_bar.setStyleSheet(styleSheet)
        self.import_doc_thread.progress_bar.setStyleSheet(styleSheet)
        self.project_upscale_thread.progress_bar.setStyleSheet(styleSheet)
        return super().setStyleSheet(styleSheet)

    def setupThread(self):
        self.imsave_thread = ImgSaveThread()
        self.export_doc_thread = ExportDocThread()
        self.export_doc_thread.fin_io.connect(self.on_fin_export_doc)
        self.import_doc_thread = ImportDocThread(self)
        self.import_doc_thread.fin_io.connect(self.on_fin_import_doc)
        self.project_upscale_thread = ProjectUpscaleThread(self)
        self.project_upscale_thread.progress_changed.connect(self.on_project_upscale_progress)
        self.project_upscale_thread.upscale_finished.connect(self.on_project_upscale_finished)
        self.project_upscale_thread.progress_bar.stop_clicked.connect(self.on_project_upscale_stop)
        self.batch_project_upscale_thread = BatchProjectUpscaleThread(self)
        self.batch_project_upscale_thread.progress_changed.connect(self.on_batch_project_upscale_progress)
        self.batch_project_upscale_thread.upscale_finished.connect(self.on_batch_project_upscale_finished)

    def resetStyleSheet(self, reverse_icon: bool = False):
        theme = 'eva-dark' if pcfg.darkmode else 'eva-light'
        self.setStyleSheet(parse_stylesheet(theme, reverse_icon))

    def setupUi(self):
        screen_size = QGuiApplication.primaryScreen().geometry().size()
        self.setMinimumWidth(screen_size.width() // 2)
        self.configPanel = ConfigPanel(self)
        self.configPanel.trans_config_panel.show_pre_MT_keyword_window.connect(self.show_pre_MT_keyword_window)
        self.configPanel.trans_config_panel.show_MT_keyword_window.connect(self.show_MT_keyword_window)
        self.configPanel.trans_config_panel.show_OCR_keyword_window.connect(self.show_OCR_keyword_window)

        self.leftBar = LeftBar(self)
        self.leftBar.showPageListLabel.clicked.connect(self.pageLabelStateChanged)
        self.leftBar.imgTransChecked.connect(self.setupImgTransUI)
        self.leftBar.configChecked.connect(self.setupConfigUI)
        self.leftBar.globalSearchChecker.clicked.connect(self.on_set_gsearch_widget)
        self.leftBar.glossary_clicked.connect(self.show_project_glossary_window)
        self.leftBar.open_dir.connect(self.OpenProj)
        self.leftBar.open_paths.connect(self.OpenProj)
        self.leftBar.open_json_proj.connect(self.openJsonProj)
        self.leftBar.save_proj.connect(self.manual_save)
        self.leftBar.batch_processing_clicked.connect(self.show_batch_processing_dialog)
        self.leftBar.export_doc.connect(self.on_export_doc)
        self.leftBar.export_comic_clicked.connect(self.on_export_comic_archive)
        self.leftBar.import_doc.connect(self.on_import_doc)
        self.leftBar.export_src_txt.connect(lambda : self.on_export_txt(dump_target='source'))
        self.leftBar.export_trans_txt.connect(lambda : self.on_export_txt(dump_target='translation'))
        self.leftBar.export_src_md.connect(lambda : self.on_export_txt(dump_target='source', suffix='.md'))
        self.leftBar.export_trans_md.connect(lambda : self.on_export_txt(dump_target='translation', suffix='.md'))
        self.leftBar.import_trans_txt.connect(self.on_import_trans_txt)
        self._project_save_error_notified = False

        self.pageList = PageListView()
        self.pageList.reveal_file.connect(self.on_reveal_file)
        self.pageList.toggle_ignore_page.connect(self.on_toggle_page_ignore)
        self.pageList.delete_page_data.connect(self.on_delete_page_data)
        self.pageList.setHidden(True)
        self.pageList.currentItemChanged.connect(self.pageListCurrentItemChanged)

        self.leftStackWidget = QStackedWidget(self)
        self.leftStackWidget.setMinimumWidth(320)
        self.leftStackWidget.setMaximumWidth(360)
        self.leftStackWidget.addWidget(self.pageList)

        self.global_search_widget = GlobalSearchWidget(self.leftStackWidget)
        self.global_search_widget.req_update_pagetext.connect(self.on_req_update_pagetext)
        self.global_search_widget.req_move_page.connect(self.on_req_move_page)
        self.imsave_thread.img_writed.connect(self.global_search_widget.on_img_writed)
        self.global_search_widget.search_tree.result_item_clicked.connect(self.on_search_result_item_clicked)
        self.leftStackWidget.addWidget(self.global_search_widget)
        
        self.centralStackWidget = QStackedWidget(self)
        
        self.titleBar = TitleBar(self)
        self.titleBar.closebtn_clicked.connect(self.on_closebtn_clicked)
        self.titleBar.display_lang_changed.connect(self.on_display_lang_changed)
        self.bottomBar = BottomBar(self)
        self.bottomBar.textedit_checkchanged.connect(self.setTextEditMode)
        self.bottomBar.paintmode_checkchanged.connect(self.setPaintMode)
        self.bottomBar.textblock_checkchanged.connect(self.setTextBlockMode)

        mainHLayout = QHBoxLayout()
        mainHLayout.addWidget(self.leftBar)
        mainHLayout.addWidget(self.centralStackWidget)
        mainHLayout.setContentsMargins(0, 0, 0, 0)
        mainHLayout.setSpacing(0)

        # set up canvas
        SW.canvas = self.canvas = Canvas()
        self.canvas.imgtrans_proj = self.imgtrans_proj
        self.canvas.gv.hide_canvas.connect(self.onHideCanvas)
        self.canvas.proj_savestate_changed.connect(self.on_savestate_changed)
        self.canvas.textstack_changed.connect(self.on_textstack_changed)
        self.canvas.run_blktrans.connect(self.on_run_blktrans)
        self.canvas.drop_open_folder.connect(self.dropOpenDir)
        self.canvas.originallayer_trans_slider = self.bottomBar.originalSlider
        self.canvas.textlayer_trans_slider = self.bottomBar.textlayerSlider
        self.canvas.copy_src_signal.connect(self.on_copy_src)
        self.canvas.paste_src_signal.connect(self.on_paste_src)

        self.bottomBar.originalSlider.valueChanged.connect(self.canvas.setOriginalTransparencyBySlider)
        self.bottomBar.textlayerSlider.valueChanged.connect(self.canvas.setTextLayerTransparencyBySlider)
        
        self.drawingPanel = DrawingPanel(self.canvas, self.configPanel.inpaint_config_panel)
        self.textPanel = TextPanel(self.app)
        self.textPanel.formatpanel.foldTextBtn.checkStateChanged.connect(self.fold_textarea)
        self.textPanel.formatpanel.sourceBtn.checkStateChanged.connect(self.show_source_text)
        self.textPanel.formatpanel.transBtn.checkStateChanged.connect(self.show_trans_text)
        self.textPanel.formatpanel.textstyle_panel.export_style.connect(self.export_tstyles)
        self.textPanel.formatpanel.textstyle_panel.import_style.connect(self.import_tstyles)

        self.ocrSubWidget = KeywordSubWidget(self.tr("Keyword substitution for source text"))
        self.ocrSubWidget.setParent(self)
        self.ocrSubWidget.setWindowFlags(Qt.WindowType.Window)
        self.ocrSubWidget.hide()
        self.mtPreSubWidget = KeywordSubWidget(self.tr("Keyword substitution for machine translation source text"))
        self.mtPreSubWidget.setParent(self)
        self.mtPreSubWidget.setWindowFlags(Qt.WindowType.Window)
        self.mtPreSubWidget.hide()
        self.mtSubWidget = KeywordSubWidget(self.tr("Keyword substitution for machine translation"))
        self.mtSubWidget.setParent(self)
        self.mtSubWidget.setWindowFlags(Qt.WindowType.Window)
        self.mtSubWidget.hide()

        self.glossaryWindow = GlossaryWindow(self)
        self.glossaryWindow.saved.connect(self.on_project_glossary_saved)
        self.glossaryWindow.hide()
        self._gloss_scan_pending = False
        self._gloss_scan_stage_backup = None
        self._gloss_scan_pages = None
        self._gui_batch_options: BatchProcessingOptions = None
        self._gui_batch_queue = []
        self._gui_batch_first_project = ''
        self._gui_batch_active_project = ''
        self._gui_batch_total = 0
        self._gui_batch_completed = 0
        self._gui_batch_cancel_requested = False
        self._gui_batch_upscale_pending = False
        self._decensor_current_page_request = None
        self._reinpaint_current_page_request = None

        SW.st_manager = self.st_manager = SceneTextManager(self.app, self, self.canvas, self.textPanel)
        self.st_manager.new_textblk.connect(self.canvas.search_widget.on_new_textblk)
        self.canvas.search_widget.pairwidget_list = self.st_manager.pairwidget_list
        self.canvas.search_widget.textblk_item_list = self.st_manager.textblk_item_list
        self.canvas.search_widget.replace_one.connect(self.st_manager.on_page_replace_one)
        self.canvas.search_widget.replace_all.connect(self.st_manager.on_page_replace_all)

        # comic trans pannel
        self.rightComicTransStackPanel = QStackedWidget(self)
        self.rightComicTransStackPanel.addWidget(self.drawingPanel)
        self.rightComicTransStackPanel.addWidget(self.textPanel)
        self.rightComicTransStackPanel.currentChanged.connect(self.on_transpanel_changed)

        self.comicTransSplitter = QSplitter(Qt.Orientation.Horizontal)
        self.comicTransSplitter.addWidget(self.leftStackWidget)
        self.comicTransSplitter.addWidget(self.canvas.gv)
        self.comicTransSplitter.addWidget(self.rightComicTransStackPanel)

        self.centralStackWidget.addWidget(self.comicTransSplitter)
        self.centralStackWidget.addWidget(self.configPanel)

        self.selectext_minimenu = self.st_manager.selectext_minimenu = SelectTextMiniMenu(self.app, self)
        self.selectext_minimenu.block_current_editor.connect(self.st_manager.on_block_current_editor)
        self.selectext_minimenu.hide()

        mainVBoxLayout = QVBoxLayout(self)
        mainVBoxLayout.addWidget(self.titleBar)
        mainVBoxLayout.addLayout(mainHLayout)
        mainVBoxLayout.addWidget(self.bottomBar)
        margin = mainVBoxLayout.contentsMargins()
        self.main_margin = margin
        mainVBoxLayout.setContentsMargins(0, 0, 0, 0)
        mainVBoxLayout.setSpacing(0)

        self.mainvlayout = mainVBoxLayout
        self.comicTransSplitter.setStretchFactor(0, 1)
        self.comicTransSplitter.setStretchFactor(1, 10)
        self.comicTransSplitter.setStretchFactor(2, 1)
        self.imgtrans_progress_msgbox = ImgtransProgressMessageBox()
        self.resetStyleSheet()

    def on_finish_setdetector(self):
        module_manager = self.module_manager
        if module_manager.textdetector is not None:
            name = module_manager.textdetector.name
            pcfg.module.textdetector = name
            self.configPanel.detect_config_panel.setDetector(name)
            self.bottomBar.textdet_selector.setSelectedValue(name)
            LOGGER.info('Text detector set to {}'.format(name))

    def on_finish_setocr(self):
        module_manager = self.module_manager
        if module_manager.ocr is not None:
            name = module_manager.ocr.name
            pcfg.module.ocr = name
            self.configPanel.ocr_config_panel.setOCR(name)
            self.bottomBar.ocr_selector.setSelectedValue(name)
            LOGGER.info('OCR set to {}'.format(name))

    def on_finish_setinpainter(self):
        module_manager = self.module_manager
        if module_manager.inpainter is not None:
            name = module_manager.inpainter.name
            pcfg.module.inpainter = name
            self.configPanel.inpaint_config_panel.setInpainter(name)
            self.bottomBar.inpaint_selector.setSelectedValue(name)
            LOGGER.info('Inpainter set to {}'.format(name))

    def on_finish_settranslator(self):
        module_manager = self.module_manager
        translator = module_manager.translator
        if translator is not None:
            name = translator.name
            pcfg.module.translator = name
            self.bottomBar.trans_selector.finishSetTranslator(translator)
            self.configPanel.trans_config_panel.finishSetTranslator(translator)
            self.sync_project_glossary_to_translator(translator)
            LOGGER.info('Translator set to {}'.format(name))
        else:
            LOGGER.error('invalid translator')
        
    def on_enable_module(self, idx, checked):
        if idx == 0:
            pcfg.module.enable_detect = checked
            self.bottomBar.textdet_selector.setVisible(checked)
        elif idx == 1:
            pcfg.module.enable_ocr = checked
            self.bottomBar.ocr_selector.setVisible(checked)
        elif idx == 2:
            pcfg.module.enable_translate = checked
            self.bottomBar.trans_selector.setVisible(checked)
        elif idx == 3:
            pcfg.module.enable_inpaint = checked
            self.bottomBar.inpaint_selector.setVisible(checked)
        elif idx == 4:
            pcfg.module.enable_inpaint_optimization = checked
        pcfg.module.update_finish_code()

    def setupConfig(self):

        self.bottomBar.originalSlider.setValue(int(pcfg.original_transparency * 100))
        self.bottomBar.trans_selector.selector.addItems(GET_VALID_TRANSLATORS())
        self.bottomBar.ocr_selector.selector.addItems(GET_VALID_OCR())
        self.bottomBar.textdet_selector.selector.addItems(GET_VALID_TEXTDETECTORS())
        self.bottomBar.textdet_selector.selector.currentTextChanged.connect(self.on_textdet_changed)
        self.bottomBar.inpaint_selector.selector.addItems(GET_VALID_INPAINTERS())
        self.bottomBar.inpaint_selector.selector.currentTextChanged.connect(self.on_inpaint_changed)
        self.bottomBar.trans_selector.cfg_clicked.connect(self.to_trans_config)
        self.bottomBar.trans_selector.selector.currentTextChanged.connect(self.on_trans_changed)
        self.bottomBar.trans_selector.tgt_selector.currentTextChanged.connect(self.on_trans_tgt_changed)
        self.bottomBar.trans_selector.src_selector.currentTextChanged.connect(self.on_trans_src_changed)
        self.bottomBar.textdet_selector.cfg_clicked.connect(self.to_detect_config)
        self.bottomBar.inpaint_selector.cfg_clicked.connect(self.to_inpaint_config)
        self.bottomBar.ocr_selector.cfg_clicked.connect(self.to_ocr_config)
        self.bottomBar.ocr_selector.selector.currentTextChanged.connect(self.on_ocr_changed)
        self.bottomBar.textdet_selector.setVisible(pcfg.module.enable_detect)
        self.bottomBar.ocr_selector.setVisible(pcfg.module.enable_ocr)
        self.bottomBar.trans_selector.setVisible(pcfg.module.enable_translate)
        self.bottomBar.inpaint_selector.setVisible(pcfg.module.enable_inpaint)

        self.configPanel.trans_config_panel.target_combobox.currentTextChanged.connect(self.on_trans_tgt_changed)
        self.configPanel.trans_config_panel.source_combobox.currentTextChanged.connect(self.on_trans_src_changed)

        self.drawingPanel.maskTransperancySlider.setValue(int(pcfg.mask_transparency * 100))
        self.leftBar.initRecentProjMenu(pcfg.recent_proj_list)
        self.leftBar.showPageListLabel.setChecked(pcfg.show_page_list)
        self.updatePageList()
        self.leftBar.save_config.connect(self.save_config)
        self.leftBar.imgTransChecker.setChecked(True)
        self.st_manager.formatpanel.global_format = pcfg.global_fontformat
        self.st_manager.formatpanel.set_active_format(pcfg.global_fontformat)
        
        self.rightComicTransStackPanel.setHidden(True)
        self.st_manager.setTextEditMode(False)
        self.st_manager.formatpanel.foldTextBtn.setChecked(pcfg.fold_textarea)
        self.st_manager.formatpanel.transBtn.setCheckState(pcfg.show_trans_text)
        self.st_manager.formatpanel.sourceBtn.setCheckState(pcfg.show_source_text)
        self.fold_textarea(pcfg.fold_textarea)
        self.show_trans_text(pcfg.show_trans_text)
        self.show_source_text(pcfg.show_source_text)

        self.module_manager = module_manager = ModuleManager(self.imgtrans_proj)
        module_manager.finish_translate_page.connect(self.finishTranslatePage)
        module_manager.imgtrans_pipeline_finished.connect(self.on_imgtrans_pipeline_finished)
        module_manager.page_trans_finished.connect(self.on_pagtrans_finished)
        module_manager.page_decensor_finished.connect(self.on_page_decensor_finished)
        module_manager.canvas_inpaint_finished.connect(self.on_reinpaint_current_page_finished)
        module_manager.setupThread(self.configPanel, self.imgtrans_progress_msgbox, self.ocr_postprocess, self.translate_preprocess, self.translate_postprocess)
        module_manager.progress_msgbox.showed.connect(self.on_imgtrans_progressbox_showed)
        module_manager.progress_msgbox.stop_clicked.connect(self.on_batch_project_upscale_stop)
        module_manager.progress_msgbox.force_stop_clicked.connect(self.on_batch_project_upscale_stop)
        module_manager.progress_msgbox.stop_all_clicked.connect(self.stop_all_gui_batch_processing)
        module_manager.blktrans_pipeline_finished.connect(self.on_blktrans_finished)
        module_manager.imgtrans_thread.post_process_mask = self.drawingPanel.rectPanel.post_process_mask
        module_manager.inpaint_thread.finish_set_module.connect(self.on_finish_setinpainter)
        module_manager.inpaint_thread.inpaint_failed.connect(self.on_reinpaint_current_page_failed)
        module_manager.translate_thread.finish_set_module.connect(self.on_finish_settranslator)
        module_manager.textdetect_thread.finish_set_module.connect(self.on_finish_setdetector)
        module_manager.ocr_thread.finish_set_module.connect(self.on_finish_setocr)
        module_manager.setTextDetector()
        module_manager.setOCR()
        module_manager.setTranslator()
        module_manager.setInpainter()

        self.leftBar.run_imgtrans_clicked.connect(self.run_imgtrans)
        self.leftBar.run_gloss_scan_clicked.connect(self.run_gloss_scan_current_manga)
        self.leftBar.run_region_merge_clicked.connect(self.run_merge_current_page_using_settings)
        self.leftBar.run_decensor_clicked.connect(self.run_decensor_current_page)
        self.leftBar.run_reinpaint_clicked.connect(self.run_reinpaint_current_page)
        self.leftBar.run_inpaint_optimize_clicked.connect(self.run_inpaint_optimize_current_page)
        self.leftBar.run_upscale_2x_clicked.connect(self.run_project_upscale_2x)
        self.leftBar.run_translate_clicked.connect(self.run_translate_only)

        self.titleBar.darkModeAction.setChecked(pcfg.darkmode)

        self.drawingPanel.set_config(pcfg.drawpanel)
        self.drawingPanel.initDLModule(module_manager)
        self.drawingPanel.reinpaint_current_page_clicked.connect(self.run_reinpaint_current_page)

        self.global_search_widget.imgtrans_proj = self.imgtrans_proj
        self.global_search_widget.setupReplaceThread(self.st_manager.pairwidget_list, self.st_manager.textblk_item_list)
        self.global_search_widget.replace_thread.finished.connect(self.on_global_replace_finished)

        self.configPanel.setupConfig()
        self.configPanel.save_config.connect(self.save_config)
        self.configPanel.settings_imported.connect(self.on_settings_imported)
        self.configPanel.reload_textstyle.connect(self.load_textstyle_from_proj_dir)
        self.configPanel.show_only_custom_font.connect(self.on_show_only_custom_font)
        if pcfg.let_show_only_custom_fonts_flag:
            self.on_show_only_custom_font(True)

        textblock_mode = pcfg.imgtrans_textblock
        if pcfg.imgtrans_textedit:
            if textblock_mode:
                self.bottomBar.textblockChecker.setChecked(True)
            self.bottomBar.texteditChecker.click()
        elif pcfg.imgtrans_paintmode:
            self.bottomBar.paintChecker.click()

        self.textPanel.formatpanel.textstyle_panel.initStyles(text_styles)

        self.canvas.search_widget.whole_word_toggle.setChecked(pcfg.fsearch_whole_word)
        self.canvas.search_widget.case_sensitive_toggle.setChecked(pcfg.fsearch_case)
        self.canvas.search_widget.regex_toggle.setChecked(pcfg.fsearch_regex)
        self.canvas.search_widget.range_combobox.setCurrentIndex(pcfg.fsearch_range)
        self.global_search_widget.whole_word_toggle.setChecked(pcfg.gsearch_whole_word)
        self.global_search_widget.case_sensitive_toggle.setChecked(pcfg.gsearch_case)
        self.global_search_widget.regex_toggle.setChecked(pcfg.gsearch_regex)
        self.global_search_widget.range_combobox.setCurrentIndex(pcfg.gsearch_range)

        if self.rightComicTransStackPanel.isHidden():
            self.setPaintMode()

        try:
            self.ocrSubWidget.loadCfgSublist(pcfg.ocr_sublist)
        except Exception as e:
            LOGGER.error(traceback.format_exc())
            pcfg.ocr_sublist = []
            self.ocrSubWidget.loadCfgSublist(pcfg.ocr_sublist)

        try:
            self.mtPreSubWidget.loadCfgSublist(pcfg.pre_mt_sublist)
        except Exception as e:
            LOGGER.error(traceback.format_exc())
            pcfg.pre_mt_sublist = []
            self.mtPreSubWidget.loadCfgSublist(pcfg.pre_mt_sublist)

        try:
            self.mtSubWidget.loadCfgSublist(pcfg.mt_sublist)
        except Exception as e:
            LOGGER.error(traceback.format_exc())
            pcfg.mt_sublist = []
            self.mtSubWidget.loadCfgSublist(pcfg.mt_sublist)

    def setupImgTransUI(self):
        self.centralStackWidget.setCurrentIndex(0)
        if self.leftBar.needleftStackWidget():
            self.leftStackWidget.show()
        else:
            self.leftStackWidget.hide()

    def setupConfigUI(self):
        self.centralStackWidget.setCurrentIndex(1)

    def set_display_lang(self, lang: str):
        self.retranslateUI()

    def _project_json_path_for_dir(self, directory: str) -> str:
        return osp.join(directory, osp.basename(osp.normpath(directory)) + '.json')

    def _looks_like_existing_project_dir(self, directory: str) -> bool:
        return (
            osp.exists(self._project_json_path_for_dir(directory))
            or osp.exists(osp.join(directory, IMPORT_METADATA))
        )

    def _should_import_dropped_directory(self, directory: str) -> bool:
        if not osp.isdir(directory) or self._looks_like_existing_project_dir(directory):
            return False
        sources = collect_importable_sources([directory], include_images=True)
        if not sources:
            return False

        for source in sources:
            ext = Path(source).suffix.lower()
            if ext in ARCHIVE_EXT:
                return True
            if ext in IMG_EXT and osp.dirname(source) != osp.abspath(directory):
                return True
        return False

    def OpenProj(self, proj_path):
        if isinstance(proj_path, (list, tuple)):
            paths = [str(path) for path in proj_path if osp.exists(str(path))]
            if not paths:
                return
            try:
                proj_path = import_sources_to_project(paths, include_images=True)
                self.leftBar.updateRecentProjList(proj_path)
            except Exception as e:
                create_error_dialog(e, self.tr('Failed to import selected sources'))
                return

        if osp.isfile(proj_path) and is_archive_path(proj_path):
            try:
                proj_path = import_archive_to_project(proj_path)
            except Exception as e:
                create_error_dialog(e, self.tr('Failed to import archive ') + proj_path)
                return
        elif osp.isfile(proj_path) and Path(proj_path).suffix.lower() in IMG_EXT:
            try:
                proj_path = import_sources_to_project([proj_path], include_images=True)
            except Exception as e:
                create_error_dialog(e, self.tr('Failed to import image ') + proj_path)
                return
        elif osp.isdir(proj_path) and self._should_import_dropped_directory(proj_path):
            try:
                proj_path = import_sources_to_project([proj_path], include_images=True)
                self.leftBar.updateRecentProjList(proj_path)
            except Exception as e:
                create_error_dialog(e, self.tr('Failed to import folder ') + proj_path)
                return
        if osp.isdir(proj_path):
            self.openDir(proj_path)
        else:
            self.openJsonProj(proj_path)
        
        if pcfg.let_textstyle_indep_flag and not (shared.HEADLESS or shared.HEADLESS_CONTINUOUS):
            self.load_textstyle_from_proj_dir(from_proj=True)

    def show_batch_processing_dialog(self):
        if self.module_manager.anyPipelineThreadRunning():
            create_info_dialog(self.tr('Another pipeline is already running. Please wait until it finishes.'))
            return
        dialog = BatchProcessingDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        self.start_gui_batch_processing(dialog.options())

    def start_gui_batch_processing(self, options: BatchProcessingOptions):
        project_dirs = options.project_dirs or collect_batch_project_dirs(options.root_dir)
        if not project_dirs:
            create_info_dialog(self.tr('No project folders with images found. Generated folders are ignored.'))
            return
        if self.canvas.text_change_unsaved():
            self.saveCurrentPage(update_scene_text=True, save_proj=True, restore_interface=True)

        self._gui_batch_options = options
        self._gui_batch_options.project_dirs = project_dirs
        self._gui_batch_queue = list(project_dirs)
        self._gui_batch_first_project = project_dirs[0]
        self._gui_batch_active_project = ''
        self._gui_batch_total = len(project_dirs)
        self._gui_batch_completed = 0
        self._gui_batch_cancel_requested = False
        self._gui_batch_upscale_pending = False
        self._apply_gui_batch_options(options)
        self.imgtrans_progress_msgbox.set_batch_mode(True)
        self._update_gui_batch_progress()
        if options.upscale_enabled and self._start_gui_batch_upscale(options):
            return
        self.run_next_gui_batch_project()

    def _apply_gui_batch_options(self, options: BatchProcessingOptions):
        pcfg.module.textdetector = options.textdetector
        pcfg.module.ocr = options.ocr
        pcfg.module.inpainter = options.inpainter
        pcfg.module.translator = options.translator
        pcfg.module.translate_source = options.source_language
        pcfg.module.translate_target = options.target_language

        self.bottomBar.textdet_selector.setSelectedValue(options.textdetector)
        self.bottomBar.ocr_selector.setSelectedValue(options.ocr)
        self.bottomBar.inpaint_selector.setSelectedValue(options.inpainter)
        self.bottomBar.trans_selector.selector.setCurrentText(options.translator)

        self.module_manager.setTextDetector(options.textdetector)
        self.module_manager.setOCR(options.ocr)
        self.module_manager.setOCRFallback(
            options.ocr_fallback if options.ocr_fallback_enabled and options.ocr_fallback != options.ocr else ''
        )
        self.module_manager.setInpainter(options.inpainter)
        self.module_manager.setTranslator(options.translator)
        self._set_pipeline_stage_state(
            options.enable_detect,
            options.enable_ocr,
            options.enable_translate,
            options.enable_inpaint,
        )

    def _update_gui_batch_progress(self):
        if self._gui_batch_total:
            value = int(self._gui_batch_completed / self._gui_batch_total * 100)
            active = osp.basename(self._gui_batch_active_project) if self._gui_batch_active_project else ''
            detail = f' {self._gui_batch_completed}/{self._gui_batch_total}'
            if active:
                detail += f' - {active}'
            self.imgtrans_progress_msgbox.updateBatchProgress(value, detail)

    def _start_gui_batch_upscale(self, options: BatchProcessingOptions) -> bool:
        jobs = []
        for directory in options.project_dirs:
            pages = find_all_imgs(directory, abs_path=False, sort=True)
            if pages:
                jobs.append((directory, pages))
        if not jobs:
            return False
        started = self.batch_project_upscale_thread.runUpscale(
            jobs,
            options.upscale_factor,
            options.upscale_max_long_edge,
            options.upscale_skip_if_long_edge_above,
            options.upscale_quality,
        )
        if started:
            self._gui_batch_upscale_pending = True
            self._batch_project_upscale_dirs = {osp.normcase(osp.abspath(directory)) for directory, _ in jobs}
            progress_box = self.imgtrans_progress_msgbox
            progress_box.hide_all_bars()
            progress_box.detect_bar.description = self.tr('Batch Upscaling: ')
            progress_box.detect_bar.show()
            progress_box.zero_progress()
            progress_box.show()
        return started

    def run_next_gui_batch_project(self):
        if not self._gui_batch_options:
            return
        if self._gui_batch_cancel_requested:
            self.finish_gui_batch_processing(stopped=True)
            return
        if not self._gui_batch_queue:
            self.finish_gui_batch_processing()
            return

        project_dir = self._gui_batch_queue.pop(0)
        self._gui_batch_active_project = project_dir
        LOGGER.info(f'Batch processing project {project_dir}')
        self.OpenProj(project_dir)
        if self.imgtrans_proj.is_empty:
            LOGGER.warning(f'Batch project has no pages: {project_dir}')
            self._gui_batch_completed += 1
            self._update_gui_batch_progress()
            self.run_next_gui_batch_project()
            return
        started = self.on_run_imgtrans(continue_mode=(
            self._gui_batch_options.skip_translated_pages or self._gui_batch_options.skip_finished_projects
        ))
        if not started:
            LOGGER.info(f'Skipping batch project with no pending pages: {project_dir}')
            self._gui_batch_completed += 1
            self._update_gui_batch_progress()
            self.run_next_gui_batch_project()

    def finish_current_gui_batch_project(self):
        options = self._gui_batch_options
        if not options:
            return
        try:
            if self.canvas.text_change_unsaved():
                self.st_manager.updateTextBlkList()
            self.saveCurrentPage(update_scene_text=False, save_proj=True, restore_interface=True)
            self._wait_for_image_saves()
            if options.export_enabled:
                output_path = default_export_path(self.imgtrans_proj.directory, options.export_ext)
                exported_path = export_project(self.imgtrans_proj, output_path)
                LOGGER.info(f'Batch export written to {exported_path}')
        except Exception as e:
            create_error_dialog(e, self.tr('Failed to finish batch project ') + self._gui_batch_active_project)

    def finish_gui_batch_processing(self, stopped: bool = False):
        options = self._gui_batch_options
        first_project = self._gui_batch_first_project
        self._gui_batch_options = None
        self._gui_batch_queue = []
        self._gui_batch_first_project = ''
        self._gui_batch_active_project = ''
        self._gui_batch_total = 0
        self._gui_batch_completed = 0
        self._gui_batch_cancel_requested = False
        self._gui_batch_upscale_pending = False
        self.module_manager.setOCRFallback('')
        self.imgtrans_progress_msgbox.set_batch_mode(False)

        if options and options.quit_when_finished and not stopped:
            self.close()
            return
        if first_project and osp.isdir(first_project):
            self.OpenProj(first_project)
        create_info_dialog(self.tr('Batch processing stopped.') if stopped else self.tr('Batch processing finished.'))

    def stop_all_gui_batch_processing(self):
        if not self._gui_batch_options:
            return
        self._gui_batch_cancel_requested = True
        self._gui_batch_queue = []
        if self.batch_project_upscale_thread.isRunning():
            self.batch_project_upscale_thread.requestStop()
            return
        self.module_manager.stopImgtransPipeline()

    def load_textstyle_from_proj_dir(self, from_proj=False):
        if from_proj:
            text_style_path = osp.join(self.imgtrans_proj.directory, 'textstyles.json')
        else:
            text_style_path = 'config/textstyles/default.json'
        if osp.exists(text_style_path):
            load_textstyle_from(text_style_path)
            self.textPanel.formatpanel.textstyle_panel.setStyles(text_styles)
        else:
            pcfg.text_styles_path = text_style_path
            save_text_styles()

    def on_show_only_custom_font(self, only_custom: bool):
        if only_custom:
            font_list = shared.CUSTOM_FONTS
        else:
            font_list = shared.FONT_FAMILIES
        self.textPanel.formatpanel.familybox.update_font_list(font_list)

    def openDir(self, directory: str):
        try:
            self.opening_dir = True
            # 在加载项目前检查并生成TIF文件的预览图
            self.generate_tif_thumbnails(directory)
            # 重新加载项目，此时应该只加载预览图
            self.imgtrans_proj.load(directory)
            self.canvas.reset_auto_fit_zoom()
            self.st_manager.clearSceneTextitems()
            self.titleBar.setTitleContent(osp.basename(directory))
            self.updatePageList()
            self.sync_project_glossary_to_ui()
            self.opening_dir = False
        except Exception as e:
            self.opening_dir = False
            create_error_dialog(e, self.tr('Failed to load project ') + directory)
            return

    def generate_tif_thumbnails(self, directory: str):
        """
        为目录中的TIF文件生成预览图，并确保只加载预览图
        """
        try:
            from utils.io_utils import create_thumbnail, find_tif_files
            # 查找目录中的所有TIF文件
            tif_files = find_tif_files(directory)
            
            # 为每个TIF文件生成预览图
            for tif_file in tif_files:
                tif_path = osp.join(directory, tif_file)
                # 检查是否已经存在对应的预览图
                base_path = Path(tif_path)
                thumb_path = base_path.parent / f"{base_path.stem}_thumb.jpg"
                
                # 如果预览图不存在，则生成预览图
                if not osp.exists(thumb_path):
                    create_thumbnail(tif_path, max_width=1000)
                    
        except Exception as e:
            LOGGER.error(f"Failed to generate TIF thumbnails: {e}")
        
    def dropOpenDir(self, directory):
        if isinstance(directory, (list, tuple)):
            paths = [str(path) for path in directory if osp.exists(str(path))]
            if paths:
                self.leftBar.updateRecentProjList(paths)
                self.OpenProj(paths)
            return
        if isinstance(directory, str) and osp.exists(directory):
            self.leftBar.updateRecentProjList(directory)
            if osp.isfile(directory) and has_importable_sources(directory, include_images=True):
                self.OpenProj([directory])
            elif osp.isdir(directory) and self._should_import_dropped_directory(directory):
                self.OpenProj([directory])
            else:
                self.OpenProj(directory)

    def openJsonProj(self, json_path: str):
        try:
            self.opening_dir = True
            self.imgtrans_proj.load_from_json(json_path)
            self.canvas.reset_auto_fit_zoom()
            self.st_manager.clearSceneTextitems()
            self.leftBar.updateRecentProjList(self.imgtrans_proj.proj_path)
            self.updatePageList()
            self.sync_project_glossary_to_ui()
            self.titleBar.setTitleContent(osp.basename(self.imgtrans_proj.proj_path))
            self.opening_dir = False
        except Exception as e:
            self.opening_dir = False
            create_error_dialog(e, self.tr('Failed to load project from') + json_path)
        
    def updatePageList(self):
        if self.pageList.count() != 0:
            self.pageList.clear()
        page_groups = self._load_page_import_groups()
        for imgname in self.imgtrans_proj.pages:
            img_path = osp.join(self.imgtrans_proj.directory, imgname)
            group_info = page_groups.get(imgname, {})
            display_name = self._page_display_name(imgname, group_info)
            lstitem = QListWidgetItem(QIcon(img_path), display_name)
            lstitem.setData(PageListView.PAGE_NAME_ROLE, imgname)
            lstitem.setData(PageListView.PAGE_GROUP_ROLE, group_info.get('name', ''))
            lstitem.setData(PageListView.PAGE_SOURCE_TYPE_ROLE, group_info.get('type', ''))
            self.apply_page_list_item_state(lstitem, imgname)
            self.pageList.addItem(lstitem)
            if imgname == self.imgtrans_proj.current_img:
                self.pageList.setCurrentItem(lstitem)

    def _load_page_import_groups(self) -> dict:
        project_dir = getattr(self.imgtrans_proj, 'directory', '')
        if not project_dir:
            return {}
        metadata_path = osp.join(project_dir, IMPORT_METADATA)
        if not osp.exists(metadata_path):
            return {}
        try:
            with open(metadata_path, 'r', encoding='utf8') as f:
                metadata = json.load(f)
        except Exception as e:
            LOGGER.warning(f'Failed to read import metadata {metadata_path}: {e}')
            return {}

        page_groups = {}
        for group in metadata.get('image_groups', []) or []:
            if not isinstance(group, dict):
                continue
            group_name = group.get('name', '')
            group_type = group.get('type', '')
            source = group.get('source', '')
            for image_name in group.get('images', []) or []:
                if isinstance(image_name, str):
                    page_groups[image_name] = {
                        'name': group_name,
                        'type': group_type,
                        'source': source,
                    }
        return page_groups

    def _page_display_name(self, imgname: str, group_info: dict) -> str:
        group = group_info.get('name') if group_info else ''
        if not group:
            return imgname
        return f'{group} / {Path(imgname).name}'

    def apply_page_list_item_state(self, item: QListWidgetItem, imgname: str):
        ignored = self.imgtrans_proj.is_page_ignored(imgname)
        group = item.data(PageListView.PAGE_GROUP_ROLE) or ''
        source_type = item.data(PageListView.PAGE_SOURCE_TYPE_ROLE) or ''
        item.setData(PageListView.PAGE_IGNORED_ROLE, ignored)
        font = item.font()
        font.setItalic(ignored)
        font.setBold(bool(group))
        item.setFont(font)
        tooltip = self.tr('Page preview')
        if group:
            source_label = source_type.upper() if source_type else self.tr('source')
            tooltip = self.tr('Imported from {source_type}: {group}\nPage: {page}').format(
                source_type=source_label,
                group=group,
                page=imgname,
            )
        if ignored:
            item.setBackground(QBrush(QColor(255, 214, 92, 72)))
            item.setToolTip(
                tooltip + '\n' +
                self.tr('Ignored in pipeline runs: text detection, OCR, translation, and inpainting are skipped for this page.')
            )
        else:
            item.setBackground(QBrush())
            item.setToolTip(tooltip)

    def refresh_page_list_item(self, imgname: str):
        for ii in range(self.pageList.count()):
            item = self.pageList.item(ii)
            if item.data(PageListView.PAGE_NAME_ROLE) == imgname:
                self.apply_page_list_item_state(item, imgname)
                break

    def pageLabelStateChanged(self):
        setup = self.leftBar.showPageListLabel.isChecked()
        if setup:
            if self.leftStackWidget.isHidden():
                self.leftStackWidget.show()
            if self.leftBar.globalSearchChecker.isChecked():
                self.leftBar.globalSearchChecker.setChecked(False)
            self.leftStackWidget.setCurrentWidget(self.pageList)
        else:
            self.leftStackWidget.hide()
        pcfg.show_page_list = setup
        save_config()

    def sync_project_glossary_to_ui(self):
        if hasattr(self, 'glossaryWindow') and self.imgtrans_proj is not None:
            self.glossaryWindow.load_glossary(self.imgtrans_proj.glossary)

    def sync_project_glossary_to_translator(self, translator=None):
        translator = translator or getattr(self.module_manager, 'translator', None)
        if translator is not None and hasattr(translator, 'set_project_glossary'):
            translator.set_project_glossary(self.imgtrans_proj.glossary)

    def sync_translator_glossary_to_project(self, translator=None, update_ui: bool = True):
        translator = translator or getattr(self.module_manager, 'translator', None)
        if translator is not None and hasattr(translator, 'get_project_glossary'):
            glossary = translator.get_project_glossary()
            if isinstance(glossary, dict):
                self.imgtrans_proj.glossary = self.imgtrans_proj.normalize_glossary(glossary)
                if update_ui and QThread.currentThread() == self.thread():
                    self.sync_project_glossary_to_ui()

    def _gloss_scan_llm_translator(self):
        translator = getattr(self.module_manager, 'translator', None)
        if isinstance(translator, LLM_API_Translator):
            return translator

        translator_name = pcfg.module.translator
        if translator_name not in {"LLM_API_Translator", "Two-Step Translator"}:
            return None
        try:
            translator_cls = TRANSLATORS.module_dict[translator_name]
            params = deepcopy(pcfg.module.translator_params.get(translator_name, {}))
            return translator_cls(
                pcfg.module.translate_source,
                pcfg.module.translate_target,
                raise_unsupported_lang=False,
                **params,
            )
        except Exception as e:
            LOGGER.warning(f'Failed to initialize Gloss Scan LLM translator {translator_name}: {e}')
            return None

    def _run_llm_gloss_scan(self, pages: List[str], old_glossary: dict) -> int:
        translator = self._gloss_scan_llm_translator()
        if translator is None or not hasattr(translator, '_update_glossary_from_batch'):
            LOGGER.info('Gloss Scan LLM extraction skipped: select LLM_API_Translator or Two-Step Translator in Settings.')
            return 0

        pairs = collect_project_translation_pairs(self.imgtrans_proj, pages=pages)
        if not pairs:
            return 0

        translator.set_project_glossary(old_glossary)
        src_list = [source for source, _target in pairs]
        draft_list = [target for _source, target in pairs]
        to_lang = getattr(translator, 'lang_map', {}).get(translator.lang_target, translator.lang_target)
        LOGGER.info(
            f'Gloss Scan LLM extraction using {translator.name or pcfg.module.translator} '
            f'with {len(src_list)} OCR/reference pair(s).'
        )
        added_count = translator._update_glossary_from_batch(
            src_list,
            draft_list,
            to_lang,
            force=True,
        )
        glossary = translator.get_project_glossary()
        if isinstance(glossary, dict):
            self.imgtrans_proj.glossary = self.imgtrans_proj.normalize_glossary(glossary)
        return added_count

    def show_project_glossary_window(self):
        if self.imgtrans_proj is None or self.imgtrans_proj.directory is None:
            create_info_dialog(self.tr('Open a project before editing the glossary.'))
            return
        self.sync_translator_glossary_to_project()
        self.sync_project_glossary_to_ui()
        self.glossaryWindow.show()
        self.glossaryWindow.raise_()
        self.glossaryWindow.activateWindow()

    def on_project_glossary_saved(self, glossary: dict):
        old_glossary = self.imgtrans_proj.normalize_glossary(self.imgtrans_proj.glossary)
        if self.canvas.text_change_unsaved():
            self.st_manager.updateTextBlkList()
        self.imgtrans_proj.glossary = self.imgtrans_proj.normalize_glossary(glossary)
        changed_pages, replacement_count = self.apply_project_glossary_changes(old_glossary, self.imgtrans_proj.glossary)
        self.sync_project_glossary_to_translator()
        if self.save_project_safely(self.tr('saving project glossary'), notify_user=True):
            if changed_pages:
                self.rerender_glossary_changed_pages(changed_pages)
                LOGGER.info(
                    f'Applied glossary changes to {replacement_count} translation occurrence(s) '
                    f'on {len(changed_pages)} page(s).'
                )
            self.canvas.setProjSaveState(False)

    def _set_pipeline_stage_state(self, detect: bool, ocr: bool, translate: bool, inpaint: bool):
        pcfg.module.enable_detect = detect
        pcfg.module.enable_ocr = ocr
        pcfg.module.enable_translate = translate
        pcfg.module.enable_inpaint = inpaint
        pcfg.module.update_finish_code()

        selectors = [
            self.bottomBar.textdet_selector,
            self.bottomBar.ocr_selector,
            self.bottomBar.trans_selector,
            self.bottomBar.inpaint_selector,
        ]
        values = [detect, ocr, translate, inpaint]
        for selector, value in zip(selectors, values):
            selector.setVisible(value)

        if hasattr(self.titleBar, 'stageActions'):
            for action, value in zip(self.titleBar.stageActions, values):
                action.blockSignals(True)
                action.setChecked(value)
                action.blockSignals(False)

    def _restore_gloss_scan_stage_state(self):
        if self._gloss_scan_stage_backup is None:
            return
        self._set_pipeline_stage_state(*self._gloss_scan_stage_backup)
        self._gloss_scan_stage_backup = None

    def run_gloss_scan_current_manga(self):
        if self.imgtrans_proj.is_empty:
            create_info_dialog(self.tr('Open a project before running Gloss Scan.'))
            return
        if self.module_manager.anyPipelineThreadRunning():
            create_info_dialog(self.tr('Another pipeline is already running. Please wait until it finishes.'))
            return

        page_names = self.imgtrans_proj.pipeline_pages(skip_ignored=True)
        if len(page_names) == 0:
            create_info_dialog(self.tr('No non-ignored pages are available for Gloss Scan.'))
            return

        if self.bottomBar.textblockChecker.isChecked():
            self.bottomBar.textblockChecker.click()
        if self.canvas.text_change_unsaved():
            self.st_manager.updateTextBlkList()

        self._gloss_scan_pending = True
        self._gloss_scan_pages = list(page_names)
        self._gloss_scan_stage_backup = (
            pcfg.module.enable_detect,
            pcfg.module.enable_ocr,
            pcfg.module.enable_translate,
            pcfg.module.enable_inpaint,
        )
        self._set_pipeline_stage_state(True, True, False, False)
        LOGGER.info(
            f'Running Gloss Scan on {len(page_names)} page(s): text detection and OCR only; '
            'translation and inpainting are disabled for this run.'
        )
        self.on_run_imgtrans()

    def finish_gloss_scan_current_manga(self):
        try:
            pages = self._gloss_scan_pages
            glossary = build_glossary_from_project_text(self.imgtrans_proj, pages=pages)
            generated_entries = glossary.get('entries', '')
            old_glossary = self.imgtrans_proj.normalize_glossary(self.imgtrans_proj.glossary)
            merged_entries = merge_glossary_entry_text(old_glossary.get('entries', ''), generated_entries)
            self.imgtrans_proj.glossary = self.imgtrans_proj.normalize_glossary({
                **old_glossary,
                'entries': merged_entries,
            })
            llm_added_count = self._run_llm_gloss_scan(pages, self.imgtrans_proj.glossary)
            generated_line_count = len([line for line in generated_entries.splitlines() if line.strip()])
            final_entries = self.imgtrans_proj.glossary.get('entries', '')
            old_entry_count = len([line for line in old_glossary.get('entries', '').splitlines() if line.strip()])
            final_entry_count = len([line for line in final_entries.splitlines() if line.strip()])
            added_or_merged_count = max(final_entry_count - old_entry_count, 0)

            if generated_line_count == 0 and llm_added_count == 0 and added_or_merged_count == 0:
                create_info_dialog(self.tr('Gloss Scan finished, but no glossary terms were found in the OCR text or by the selected LLM glossary scan.'))
                return

            self.sync_project_glossary_to_ui()
            self.sync_project_glossary_to_translator()
            if self.save_project_safely(self.tr('saving Gloss Scan glossary'), notify_user=True):
                self.canvas.setProjSaveState(False)
                LOGGER.info(
                    f'Gloss Scan added or refreshed {generated_line_count} heuristic '
                    f'and {llm_added_count} LLM glossary candidate(s).'
                )
                create_info_dialog(
                    self.tr('Gloss Scan finished. {count} glossary candidates were added to the project glossary.').format(
                        count=added_or_merged_count or generated_line_count + llm_added_count
                    )
                )
        finally:
            self._gloss_scan_pending = False
            self._gloss_scan_pages = None
            self._restore_gloss_scan_stage_state()

    def apply_project_glossary_changes(self, old_glossary: dict, new_glossary: dict):
        replacements = build_glossary_replacements(old_glossary, new_glossary)
        if not replacements:
            return [], 0

        changed_pages = []
        replacement_count = 0
        for page_name, blk_list in self.imgtrans_proj.pages.items():
            page_changed = False
            for blk in blk_list:
                for attr in ('translation', 'rich_text'):
                    text = getattr(blk, attr, '')
                    updated, count = apply_glossary_replacements_to_text(text, replacements)
                    if count:
                        setattr(blk, attr, updated)
                        replacement_count += count
                        page_changed = True
            if page_changed:
                changed_pages.append(page_name)

        if self.imgtrans_proj.current_img in changed_pages:
            self.st_manager.updateTranslation()
            self.canvas.setProjSaveState(True)
        return changed_pages, replacement_count

    def rerender_glossary_changed_pages(self, changed_pages: List[str]):
        if not changed_pages:
            return

        original_page = self.imgtrans_proj.current_img
        original_save_on_page_changed = self.save_on_page_changed
        self.save_on_page_changed = False
        try:
            for page_name in changed_pages:
                page_index = self.imgtrans_proj.pagename2idx(page_name)
                if page_index < 0:
                    continue
                if self.pageList.currentIndex().row() != page_index:
                    self.pageList.setCurrentRow(page_index)
                else:
                    self.imgtrans_proj.set_current_img(page_name)
                    self.canvas.updateCanvas()
                    self.st_manager.updateSceneTextitems()
                self.saveCurrentPage(update_scene_text=False, save_proj=False, save_rst_only=True)
        finally:
            if original_page in self.imgtrans_proj.pages:
                original_index = self.imgtrans_proj.pagename2idx(original_page)
                if original_index >= 0 and self.pageList.currentIndex().row() != original_index:
                    self.pageList.setCurrentRow(original_index)
            self.save_on_page_changed = original_save_on_page_changed

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.imgtrans_proj.is_empty:
            self.conditional_save(keep_exist_as_backup=True)
        while True:
            if not self.imsave_thread.isRunning():
                break
            time.sleep(0.1)
        self.st_manager.hovering_transwidget = None
        self.st_manager.blockSignals(True)
        self.canvas.prepareClose()
        self.save_config()
        return super().closeEvent(event)

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMaximized:
                if not shared.ON_MACOS:
                    self.titleBar.maxBtn.setChecked(True)
        elif event.type() == QEvent.Type.ActivationChange:
            self.canvas.on_activation_changed()

        super().changeEvent(event)
    
    def retranslateUI(self):
        # according to https://stackoverflow.com/questions/27635068/how-to-retranslate-dynamically-created-widgets
        # we got to do it manually ... I'd rather restart the program
        msg = QMessageBox()
        msg.setText(self.tr('Restart to apply changes? \n'))
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        ret = msg.exec_()
        if ret == QMessageBox.StandardButton.Yes:
            self.restart_signal.emit()

    def save_config(self):
        save_config()

    def on_settings_imported(self):
        self.leftBar.showPageListLabel.setChecked(pcfg.show_page_list)
        self.bottomBar.textdet_selector.setVisible(pcfg.module.enable_detect)
        self.bottomBar.ocr_selector.setVisible(pcfg.module.enable_ocr)
        self.bottomBar.trans_selector.setVisible(pcfg.module.enable_translate)
        self.bottomBar.inpaint_selector.setVisible(pcfg.module.enable_inpaint)
        self.bottomBar.textdet_selector.setSelectedValue(pcfg.module.textdetector)
        self.bottomBar.ocr_selector.setSelectedValue(pcfg.module.ocr)
        self.bottomBar.inpaint_selector.setSelectedValue(pcfg.module.inpainter)
        self.bottomBar.trans_selector.blockSignals(True)
        self.bottomBar.trans_selector.selector.setCurrentText(pcfg.module.translator)
        self.bottomBar.trans_selector.blockSignals(False)
        self.module_manager.setTextDetector(pcfg.module.textdetector)
        self.module_manager.setOCR(pcfg.module.ocr)
        self.module_manager.setTranslator(pcfg.module.translator)
        self.module_manager.setInpainter(pcfg.module.inpainter)
        if pcfg.darkmode != self.titleBar.darkModeAction.isChecked():
            self.titleBar.darkModeAction.setChecked(pcfg.darkmode)
            self.resetStyleSheet(reverse_icon=True)
        self.drawingPanel.set_config(pcfg.drawpanel)
        self.drawingPanel.maskTransperancySlider.setValue(int(pcfg.mask_transparency * 100))
        self.bottomBar.originalSlider.setValue(int(pcfg.original_transparency * 100))
        self.canvas.setOriginalTransparency(pcfg.original_transparency)
        self.on_show_only_custom_font(pcfg.let_show_only_custom_fonts_flag)

    def onHideCanvas(self):
        self.canvas.clearToolStates()

    def conditional_save(self, keep_exist_as_backup=False):
        if self.canvas.projstate_unsaved and not self.opening_dir:
            update_scene_text = save_proj = self.canvas.text_change_unsaved()
            save_rst_only = not self.canvas.draw_change_unsaved()
            if not save_rst_only:
                save_proj = True
            
            self.saveCurrentPage(update_scene_text, save_proj, restore_interface=True, save_rst_only=save_rst_only, keep_exist_as_backup=keep_exist_as_backup)

    def save_project_safely(self, reason: str = '', keep_exist_as_backup=False, notify_user: bool = False) -> bool:
        try:
            self.imgtrans_proj.save(keep_exist_as_backup=keep_exist_as_backup)
            self._project_save_error_notified = False
            return True
        except (PermissionError, OSError) as e:
            LOGGER.exception(f'Failed to save project file during {reason or "project save"}')
            self.canvas.setProjSaveState(True)
            tmp_path = getattr(self.imgtrans_proj, 'proj_path', '') + '.tmp'
            tmp_msg = ''
            if tmp_path and osp.exists(tmp_path):
                tmp_msg = self.tr('\nA temporary project file was kept at:\n{path}').format(path=tmp_path)
            msg = self.tr(
                'Project changes could not be saved right now. '
                'The project is still marked as unsaved; please try saving again.'
            ) + tmp_msg
            if notify_user and not self._project_save_error_notified:
                QMessageBox.warning(self, self.tr('Project Save Failed'), msg)
                self._project_save_error_notified = True
            else:
                LOGGER.warning(msg)
            return False
        except Exception as e:
            LOGGER.exception(f'Unexpected project save failure during {reason or "project save"}')
            self.canvas.setProjSaveState(True)
            if notify_user and not self._project_save_error_notified:
                QMessageBox.warning(
                    self,
                    self.tr('Project Save Failed'),
                    self.tr('Project changes could not be saved. The project remains unsaved.'),
                )
                self._project_save_error_notified = True
            return False

    def pageListCurrentItemChanged(self):
        item = self.pageList.currentItem()
        self.page_changing = True
        if item is not None:
            if self.save_on_page_changed:
                self.conditional_save()
            page_name = item.data(PageListView.PAGE_NAME_ROLE) or item.text()
            self.imgtrans_proj.set_current_img(page_name)
            self.canvas.clear_undostack(update_saved_step=True)
            self.canvas.updateCanvas()
            self.st_manager.updateSceneTextitems()
            self.titleBar.setTitleContent(
                page_name=self.imgtrans_proj.current_img,
                page_index=self.imgtrans_proj.current_idx + 1,
                page_count=self.imgtrans_proj.num_pages,
            )
            self.module_manager.handle_page_changed()
            self.drawingPanel.handle_page_changed()
            
        self.page_changing = False

    def setupShortcuts(self):
        self.titleBar.nextpage_trigger.connect(self.shortcutNext) 
        self.titleBar.prevpage_trigger.connect(self.shortcutBefore)
        self.titleBar.textedit_trigger.connect(self.shortcutTextedit)
        self.titleBar.drawboard_trigger.connect(self.shortcutDrawboard)
        self.titleBar.redo_trigger.connect(self.on_redo)
        self.titleBar.undo_trigger.connect(self.on_undo)
        self.titleBar.page_search_trigger.connect(self.on_page_search)
        self.titleBar.global_search_trigger.connect(self.on_global_search)
        self.titleBar.replacePreMTkeyword_trigger.connect(self.show_pre_MT_keyword_window)
        self.titleBar.replaceMTkeyword_trigger.connect(self.show_MT_keyword_window)
        self.titleBar.replaceOCRkeyword_trigger.connect(self.show_OCR_keyword_window)
        self.titleBar.run_trigger.connect(self.leftBar.runImgtransBtn.click)
        self.titleBar.run_woupdate_textstyle_trigger.connect(self.run_imgtrans_wo_textstyle_update)
        self.titleBar.translate_page_trigger.connect(self.on_transpagebtn_pressed)
        self.titleBar.gloss_scan_trigger.connect(self.run_gloss_scan_current_manga)
        self.titleBar.review_current_page_trigger.connect(self.run_review_current_page)
        self.titleBar.review_all_pages_trigger.connect(self.run_review_all_pages)
        self.titleBar.translation_benchmark_trigger.connect(self.show_translation_benchmark_window)
        self.titleBar.enable_module.connect(self.on_enable_module)
        self.titleBar.importtstyle_trigger.connect(self.import_tstyles)
        self.titleBar.exporttstyle_trigger.connect(self.export_tstyles)
        self.titleBar.darkmode_trigger.connect(self.on_darkmode_triggered)
        self.titleBar.merge_tool_trigger.connect(self.on_open_merge_tool)
        self.titleBar.reinpaint_current_page_trigger.connect(self.run_reinpaint_current_page)
        self.titleBar.optimize_inpaint_current_page_trigger.connect(self.run_inpaint_optimize_current_page)
        self.titleBar.optimize_inpaint_all_pages_trigger.connect(self.run_inpaint_optimize_all_pages)
        self.titleBar.upscale_project_2x_trigger.connect(self.run_project_upscale_2x)
        self.titleBar.upscale_project_settings_trigger.connect(self.run_project_upscale_using_settings)
        self.titleBar.batch_upscale_folders_trigger.connect(self.run_batch_project_upscale_using_settings)
        self.titleBar.remove_current_page_masks_trigger.connect(self.remove_current_page_masks)
        self.titleBar.model_downloads_trigger.connect(self.show_model_download_window)

        shortcutA = QShortcut(QKeySequence("A"), self)
        shortcutA.activated.connect(self.shortcutBefore)
        shortcutPageUp = QShortcut(QKeySequence(QKeySequence.StandardKey.MoveToPreviousPage), self)
        shortcutPageUp.activated.connect(self.shortcutBefore)

        shortcutD = QShortcut(QKeySequence("D"), self)
        shortcutD.activated.connect(self.shortcutNext)
        shortcutPageDown = QShortcut(QKeySequence(QKeySequence.StandardKey.MoveToNextPage), self)
        shortcutPageDown.activated.connect(self.shortcutNext)

        shortcutTextblock = QShortcut(QKeySequence("W"), self)
        shortcutTextblock.activated.connect(self.shortcutTextblock)
        shortcutPageList = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        shortcutPageList.activated.connect(self.shortcutPageList)
        shortcutZoomIn = QShortcut(QKeySequence.StandardKey.ZoomIn, self)
        shortcutZoomIn.activated.connect(self.canvas.gv.scale_up_signal)
        shortcutZoomOut = QShortcut(QKeySequence.StandardKey.ZoomOut, self)
        shortcutZoomOut.activated.connect(self.canvas.gv.scale_down_signal)
        shortcutCtrlD = QShortcut(QKeySequence("Ctrl+D"), self)
        shortcutCtrlD.activated.connect(self.shortcutCtrlD)
        shortcutSpace = QShortcut(QKeySequence("Space"), self)
        shortcutSpace.activated.connect(self.shortcutSpace)
        shortcutSelectAll = QShortcut(QKeySequence.StandardKey.SelectAll, self)
        shortcutSelectAll.activated.connect(self.shortcutSelectAll)

        shortcutEscape = QShortcut(QKeySequence("Escape"), self)
        shortcutEscape.activated.connect(self.shortcutEscape)

        shortcutBold = QShortcut(QKeySequence.StandardKey.Bold, self)
        shortcutBold.activated.connect(self.shortcutBold)
        shortcutItalic = QShortcut(QKeySequence.StandardKey.Italic, self)
        shortcutItalic.activated.connect(self.shortcutItalic)
        shortcutUnderline = QShortcut(QKeySequence.StandardKey.Underline, self)
        shortcutUnderline.activated.connect(self.shortcutUnderline)

        shortcutDelete = QShortcut(QKeySequence.StandardKey.Delete, self)
        shortcutDelete.activated.connect(self.shortcutDelete)

        drawpanel_shortcuts = {'hand': 'H', 'rect': 'R', 'inpaint': 'J', 'pen': 'B', 'reinpaint': 'I'}
        for tool_name, shortcut_key in drawpanel_shortcuts.items():
            shortcut = QShortcut(QKeySequence(shortcut_key), self)
            shortcut.activated.connect(partial(self.drawingPanel.shortcutSetCurrentToolByName, tool_name))
            self.drawingPanel.setShortcutTip(tool_name, shortcut_key)

        shortcutReInpaint = QShortcut(QKeySequence("Ctrl+Shift+I"), self)
        shortcutReInpaint.activated.connect(self.run_reinpaint_current_page)

        shortcutRemoveMasks = QShortcut(QKeySequence("Ctrl+Shift+Backspace"), self)
        shortcutRemoveMasks.activated.connect(self.remove_current_page_masks)

    def shortcutNext(self):
        sender: QShortcut = self.sender()
        if isinstance(sender, QShortcut):
            if sender.key() == QKEY.Key_D:
                if self.canvas.editing_textblkitem is not None:
                    return
        if self.centralStackWidget.currentIndex() == 0:
            focus_widget = self.app.focusWidget()
            if self.st_manager.is_editting():
                self.st_manager.on_switch_textitem(1)
            elif isinstance(focus_widget, (SourceTextEdit, TransTextEdit)):
                self.st_manager.on_switch_textitem(1, current_editing_widget=focus_widget)
            else:
                index = self.pageList.currentIndex()
                page_count = self.pageList.count()
                if index.isValid():
                    row = index.row()
                    row = (row + 1) % page_count
                    self.pageList.setCurrentRow(row)

    def shortcutBefore(self):
        sender: QShortcut = self.sender()
        if isinstance(sender, QShortcut):
            if sender.key() == QKEY.Key_A:
                if self.canvas.editing_textblkitem is not None:
                    return
        if self.centralStackWidget.currentIndex() == 0:
            focus_widget = self.app.focusWidget()
            if self.st_manager.is_editting():
                self.st_manager.on_switch_textitem(-1)
            elif isinstance(focus_widget, (SourceTextEdit, TransTextEdit)):
                self.st_manager.on_switch_textitem(-1, current_editing_widget=focus_widget)
            else:
                index = self.pageList.currentIndex()
                page_count = self.pageList.count()
                if index.isValid():
                    row = index.row()
                    row = (row - 1 + page_count) % page_count
                    self.pageList.setCurrentRow(row)

    def shortcutTextedit(self):
        if self.centralStackWidget.currentIndex() == 0:
            self.bottomBar.texteditChecker.click()

    def shortcutTextblock(self):
        if self.centralStackWidget.currentIndex() == 0:
            if self.bottomBar.texteditChecker.isChecked():
                self.bottomBar.textblockChecker.click()

    def shortcutPageList(self):
        if self.centralStackWidget.currentIndex() == 0:
            self.leftBar.showPageListLabel.click()

    def shortcutDrawboard(self):
        if self.centralStackWidget.currentIndex() == 0:
            self.bottomBar.paintChecker.click()

    def shortcutCtrlD(self):
        if self.centralStackWidget.currentIndex() == 0:
            if self.drawingPanel.isVisible():
                if self.drawingPanel.currentTool == self.drawingPanel.rectTool:
                    self.drawingPanel.rectPanel.delete_btn.click()
            elif self.canvas.textEditMode():
                self.canvas.delete_textblks.emit(0)

    def shortcutSelectAll(self):
        if self.centralStackWidget.currentIndex() == 0:
            if self.textPanel.isVisible():
                self.st_manager.set_blkitems_selection(True)

    def shortcutSpace(self):
        if self.centralStackWidget.currentIndex() == 0:
            if self.drawingPanel.isVisible():
                if self.drawingPanel.currentTool == self.drawingPanel.rectTool:
                    self.drawingPanel.rectPanel.inpaint_btn.click()

    def shortcutBold(self):
        if self.textPanel.formatpanel.isVisible():
            self.textPanel.formatpanel.formatBtnGroup.boldBtn.click()

    def shortcutDelete(self):
        if self.canvas.gv.isVisible():
            self.canvas.delete_textblks.emit(1)

    def shortcutItalic(self):
        if self.textPanel.formatpanel.isVisible():
            self.textPanel.formatpanel.formatBtnGroup.italicBtn.click()

    def shortcutUnderline(self):
        if self.textPanel.formatpanel.isVisible():
            self.textPanel.formatpanel.formatBtnGroup.underlineBtn.click()

    def on_redo(self):
        self.canvas.redo()

    def on_undo(self):
        self.canvas.undo()

    def on_page_search(self):
        if self.canvas.gv.isVisible():
            fo = self.app.focusObject()
            sel_text = ''
            tgt_edit = None
            blkitem = self.canvas.editing_textblkitem
            if fo == self.canvas.gv and blkitem is not None:
                sel_text = blkitem.textCursor().selectedText()
                tgt_edit = self.st_manager.pairwidget_list[blkitem.idx].e_trans
            elif isinstance(fo, QTextEdit) or isinstance(fo, QPlainTextEdit):
                sel_text = fo.textCursor().selectedText()
                if isinstance(fo, SourceTextEdit):
                    tgt_edit = fo
            se = self.canvas.search_widget.search_editor
            se.setFocus()
            if sel_text != '':
                se.setPlainText(sel_text)
                cursor = se.textCursor()
                cursor.select(QTextCursor.SelectionType.Document)
                se.setTextCursor(cursor)

            if self.canvas.search_widget.isHidden():
                self.canvas.search_widget.show()
            self.canvas.search_widget.setCurrentEditor(tgt_edit)

    def on_global_search(self):
        if self.canvas.gv.isVisible():
            if not self.leftBar.globalSearchChecker.isChecked():
                self.leftBar.globalSearchChecker.click()
            fo = self.app.focusObject()
            sel_text = ''
            blkitem = self.canvas.editing_textblkitem
            if fo == self.canvas.gv and blkitem is not None:
                sel_text = blkitem.textCursor().selectedText()
            elif isinstance(fo, QTextEdit) or isinstance(fo, QPlainTextEdit):
                sel_text = fo.textCursor().selectedText()
            se = self.global_search_widget.search_editor
            se.setFocus()
            if sel_text != '':
                se.setPlainText(sel_text)
                cursor = se.textCursor()
                cursor.select(QTextCursor.SelectionType.Document)
                se.setTextCursor(cursor)
                
                self.global_search_widget.commit_search()

    def show_pre_MT_keyword_window(self):
        self.mtPreSubWidget.show()

    def show_MT_keyword_window(self):
        self.mtSubWidget.show()


    def show_OCR_keyword_window(self):
        self.ocrSubWidget.show()

    def on_open_merge_tool(self):
        if not hasattr(self, 'merge_dialog') or self.merge_dialog is None:
            from .merge_dialog import MergeDialog
            from qtpy.QtCore import QThread
            from qtpy.QtWidgets import QProgressDialog
            from utils import merger
            
            self.merge_dialog = MergeDialog(self)
            self.merge_dialog.run_current_clicked.connect(lambda: self.run_merge_task(on_current=True))
            self.merge_dialog.run_all_clicked.connect(lambda: self.run_merge_task(on_current=False))
        
        if self.merge_dialog.isVisible():
            self.merge_dialog.raise_()
            self.merge_dialog.activateWindow()
        else:
            self.merge_dialog.show()

    def run_merge_current_page_using_settings(self):
        self.run_merge_task(
            on_current=True,
            config=self.module_manager.post_merge_config_from_settings(),
        )

    def run_merge_task(self, on_current=False, config=None):
        from utils import merger
        from qtpy.QtWidgets import QMessageBox
        
        if self.imgtrans_proj.is_empty:
            QMessageBox.warning(self, self.tr("Warning"), self.tr("Please open a project first."))
            return
        
        if config is None:
            config = self.merge_dialog.get_config()
        
        if on_current:
            from utils.textblock import TextBlock
            
            current_img = self.imgtrans_proj.current_img
            if not current_img:
                QMessageBox.warning(self, self.tr("Warning"), self.tr("No current file."))
                return
            
            if current_img not in self.imgtrans_proj.pages:
                QMessageBox.warning(self, self.tr("Warning"), self.tr("Current page data does not exist."))
                return
            
            textblocks = self.imgtrans_proj.pages[current_img]
            if not textblocks:
                QMessageBox.warning(self, self.tr("Notice"), self.tr("The current page has no text boxes."))
                return
            
            initial_shapes = [blk.to_dict() for blk in textblocks]
            
            initial_count = len(initial_shapes)
            mode = config.get("MERGE_MODE", "NONE")
            total_merged = 0
            
            if mode == "VERTICAL":
                final_shapes, count = merger.perform_merge(initial_shapes, "VERTICAL", config)
                total_merged += count
            elif mode == "HORIZONTAL":
                final_shapes, count = merger.perform_merge(initial_shapes, "HORIZONTAL", config)
                total_merged += count
            elif mode == "VERTICAL_THEN_HORIZONTAL":
                temp, count1 = merger.perform_merge(initial_shapes, "VERTICAL", config)
                final_shapes, count2 = merger.perform_merge(temp, "HORIZONTAL", config)
                total_merged += (count1 + count2)
            elif mode == "HORIZONTAL_THEN_VERTICAL":
                temp, count1 = merger.perform_merge(initial_shapes, "HORIZONTAL", config)
                final_shapes, count2 = merger.perform_merge(temp, "VERTICAL", config)
                total_merged += (count1 + count2)
            else:
                final_shapes = initial_shapes
            
            if total_merged > 0:
                self.imgtrans_proj.pages[current_img] = [TextBlock(**blk_dict) for blk_dict in final_shapes]
                self.canvas.updateCanvas()
                self.st_manager.updateSceneTextitems()
                final_count = len(final_shapes)
                QMessageBox.information(
                    self,
                    self.tr("Success"),
                    self.tr("Merge complete: box count {initial} -> {final} ({reduced} fewer)").format(
                        initial=initial_count,
                        final=final_count,
                        reduced=initial_count - final_count,
                    )
                )
            else:
                labels = set(s.get('label', '') for s in initial_shapes)
                detail_msg = self.tr(
                    "No merge was performed.\n"
                    "There are {count} text boxes.\n"
                    "Label types: {labels}\n\n"
                    "Suggestions:\n"
                    "1. Try increasing the maximum gap value (for example 100-200).\n"
                    "2. Lower the minimum overlap ratio (for example 50-70%).\n"
                    "3. Disable 'Enable labels excluded from merging'.\n"
                    "4. Check whether the labels are blacklisted."
                ).format(count=initial_count, labels=', '.join(labels) or self.tr('none'))
                QMessageBox.warning(self, self.tr("Notice"), detail_msg)
        else:
            img_list = list(self.imgtrans_proj.pages.keys())
            if not img_list:
                QMessageBox.warning(self, self.tr("Warning"), self.tr("The project has no images."))
                return
            
            json_path = self.imgtrans_proj.proj_path
            if not json_path or not osp.exists(json_path):
                QMessageBox.warning(self, self.tr("Warning"), self.tr("Project JSON file not found: {path}").format(path=json_path))
                return
            
            self.run_merge_all_async(json_path, img_list, config)
    
    def run_merge_all_async(self, json_path, img_list, config):
        from .io_thread import MergeThread
        
        if not hasattr(self, 'merge_thread'):
            self.merge_thread = MergeThread()
            self.merge_thread.progress_changed.connect(self.on_merge_progress)
            self.merge_thread.merge_finished.connect(self.on_merge_finished)
            self.merge_thread.progress_bar.stop_clicked.connect(self.on_merge_stop)
        
        if self.merge_thread.runMerge(json_path, img_list, config):
            self.merge_thread.progress_bar.zero_progress()
            self.merge_thread.progress_bar.show()
    
    def on_merge_progress(self, current, total):
        progress = int(current / total * 100)
        self.merge_thread.progress_bar.updateTaskProgress(progress, f' {current}/{total}')
    
    def on_merge_stop(self):
        if hasattr(self, 'merge_thread'):
            self.merge_thread.requestStop()
            self.merge_thread.progress_bar.hide()
    
    def on_merge_finished(self, success_count, fail_count):
        self.merge_thread.progress_bar.hide()
        
        try:
            json_path = self.imgtrans_proj.proj_path
            current_img = self.imgtrans_proj.current_img
            self.imgtrans_proj.load_from_json(json_path)
            if current_img and current_img in self.imgtrans_proj.pages:
                self.imgtrans_proj.set_current_img(current_img)
                self.canvas.updateCanvas()
                self.st_manager.updateSceneTextitems()
        except:
            pass
        
        total = success_count + fail_count
        QMessageBox.information(
            self,
            self.tr("Complete"),
            self.tr("Region merge complete\nSucceeded: {success}/{total}\nFailed: {failed}/{total}").format(
                success=success_count,
                failed=fail_count,
                total=total,
            )
        )

    def on_req_update_pagetext(self):
        if self.canvas.text_change_unsaved():
            self.st_manager.updateTextBlkList()

    # 20260418 全部替换并重新渲染 会导致图片切换不保存图片的bug
    def on_req_move_page(self, page_name: str, force_save=False):
        ori_save = self.save_on_page_changed
        self.save_on_page_changed = False
        current_img = self.imgtrans_proj.current_img

        if current_img == page_name and not force_save:
            # 修复 Bug：提前返回时必须恢复自动保存的开关状态
            self.save_on_page_changed = ori_save 
            return

        if current_img not in self.global_search_widget.page_set:
            if self.canvas.projstate_unsaved: 
                self.saveCurrentPage()
        else:
            self.saveCurrentPage(save_rst_only=True)

        self.pageList.setCurrentRow(self.imgtrans_proj.pagename2idx(page_name))
        self.save_on_page_changed = ori_save
    # 20260418 全部替换并重新渲染 会导致图片切换不保存图片的bug end

    def on_search_result_item_clicked(self, pagename: str, blk_idx: int, is_src: bool, start: int, end: int):
        idx = self.imgtrans_proj.pagename2idx(pagename)
        self.pageList.setCurrentRow(idx)
        pw = self.st_manager.pairwidget_list[blk_idx]
        edit = pw.e_source if is_src else pw.e_trans
        edit.setFocus()
        edit.ensure_scene_visible.emit()
        cursor = QTextCursor(edit.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        edit.setTextCursor(cursor)

    def shortcutEscape(self):
        if self.canvas.search_widget.isVisible():
            self.canvas.search_widget.hide()
        elif self.canvas.editing_textblkitem is not None and self.canvas.editing_textblkitem.isEditing():
            self.canvas.editing_textblkitem.endEdit()

    def setPaintMode(self):
        if self.bottomBar.paintChecker.isChecked():
            if self.rightComicTransStackPanel.isHidden():
                self.rightComicTransStackPanel.show()
            self.rightComicTransStackPanel.setCurrentIndex(0)
            self.canvas.setPaintMode(True)
            self.bottomBar.originalSlider.show()
            self.bottomBar.textlayerSlider.show()
            self.bottomBar.textblockChecker.hide()
        else:
            self.canvas.setPaintMode(False)
            self.rightComicTransStackPanel.setHidden(True)
        self.st_manager.setTextEditMode(False)

    def setTextEditMode(self):
        if self.bottomBar.texteditChecker.isChecked():
            if self.rightComicTransStackPanel.isHidden():
                self.rightComicTransStackPanel.show()
            self.bottomBar.textblockChecker.show()
            self.rightComicTransStackPanel.setCurrentIndex(1)
            self.st_manager.setTextEditMode(True)
            self.setTextBlockMode()
        else:
            self.bottomBar.textblockChecker.hide()
            self.rightComicTransStackPanel.setHidden(True)
            self.st_manager.setTextEditMode(False)
        self.canvas.setPaintMode(False)

    def setTextBlockMode(self):
        mode = self.bottomBar.textblockChecker.isChecked()
        self.canvas.setTextBlockMode(mode)
        pcfg.imgtrans_textblock = mode
        self.st_manager.showTextblkItemRect(mode)

    def manual_save(self):
        if self.leftBar.imgTransChecker.isChecked()\
            and self.imgtrans_proj.directory is not None:
            LOGGER.debug('Manually saving...')
            self.saveCurrentPage(update_scene_text=True, save_proj=True, restore_interface=True, save_rst_only=False)

    def saveCurrentPage(self, update_scene_text=True, save_proj=True, restore_interface=False, save_rst_only=False, keep_exist_as_backup=False):
        
        if not self.imgtrans_proj.img_valid:
            return
        
        if restore_interface:
            set_canvas_focus = self.canvas.hasFocus()
            sel_textitem = self.canvas.selected_text_items()
            n_sel_textitems = len(sel_textitem)
            editing_textitem = None
            if n_sel_textitems == 1 and sel_textitem[0].isEditing():
                editing_textitem = sel_textitem[0]
        
        if update_scene_text:
            self.st_manager.updateTextBlkList()
        
        if self.rightComicTransStackPanel.isHidden():
            self.bottomBar.texteditChecker.click()

        restore_textblock_mode = False
        if pcfg.imgtrans_textblock:
            restore_textblock_mode = True
            self.bottomBar.textblockChecker.click()

        hide_tsc = False
        if self.st_manager.txtblkShapeControl.isVisible():
            hide_tsc = True
            self.st_manager.txtblkShapeControl.hide()

        if not osp.exists(self.imgtrans_proj.result_dir()):
            os.makedirs(self.imgtrans_proj.result_dir())

        project_saved = True
        if save_proj:
            project_saved = self.save_project_safely(
                self.tr('saving current page'),
                keep_exist_as_backup=keep_exist_as_backup,
                notify_user=True,
            )
            if project_saved:
                if not save_rst_only:
                    mask_path = self.imgtrans_proj.get_mask_path()
                    mask_array = self.imgtrans_proj.mask_array
                    if mask_array is not None:
                        self.imsave_thread.saveImg(mask_path, mask_array, save_params={'ext': pcfg.intermediate_imgsave_ext, 'quality': pcfg.intermediate_imgsave_quality})
                    inpainted_path = self.imgtrans_proj.get_inpainted_path()
                    if self.canvas.drawingLayer.drawed():
                        inpainted = self.canvas.base_pixmap.copy()
                        painter = QPainter(inpainted)
                        painter.drawPixmap(0, 0, self.canvas.drawingLayer.get_drawed_pixmap())
                        painter.end()
                    else:
                        inpainted = self.imgtrans_proj.inpainted_array
                    if inpainted is not None:
                        self.imsave_thread.saveImg(inpainted_path, inpainted, save_params={'ext': pcfg.intermediate_imgsave_ext, 'quality': pcfg.intermediate_imgsave_quality}, keep_alpha=self.imgtrans_proj.current_has_alpha())

        # Render the final result image properly
        try:
            img = self.canvas.render_result_img()
            imsave_path = self.imgtrans_proj.get_result_path(self.imgtrans_proj.current_img)
            self.imsave_thread.saveImg(imsave_path, img, self.imgtrans_proj.current_img, save_params={'ext': pcfg.imgsave_ext, 'quality': pcfg.imgsave_quality}, keep_alpha=self.imgtrans_proj.current_has_alpha())
            if project_saved and save_proj:
                self.canvas.setProjSaveState(False)
                self.canvas.update_saved_undostep()
        
        except Exception as e:
            LOGGER.error(f"Failed to render and save result image: {e}")

        if restore_interface:
            if restore_textblock_mode:
                self.bottomBar.textblockChecker.click()
            if hide_tsc:
                self.st_manager.txtblkShapeControl.show()
            if set_canvas_focus:
                self.canvas.setFocus()
            if n_sel_textitems > 0:
                self.canvas.block_selection_signal = True
                for blk in sel_textitem:
                    blk.setSelected(True)
                self.st_manager.on_incanvas_selection_changed()
                self.canvas.block_selection_signal = False
            if editing_textitem is not None:
                editing_textitem.startEdit()
        
    def to_trans_config(self):
        self.leftBar.configChecker.setChecked(True)
        self.configPanel.focusOnTranslator()

    def to_inpaint_config(self):
        self.leftBar.configChecker.setChecked(True)
        self.configPanel.focusOnInpaint()

    def to_ocr_config(self):
        self.leftBar.configChecker.setChecked(True)
        self.configPanel.focusOnOCR()

    def to_detect_config(self):
        self.leftBar.configChecker.setChecked(True)
        self.configPanel.focusOnDetect()

    def on_textdet_changed(self):
        module = self.bottomBar.textdet_selector.selector.currentText()
        tgt_selector = self.configPanel.detect_config_panel.module_combobox
        if tgt_selector.currentText() != module and module in GET_VALID_TEXTDETECTORS():
            tgt_selector.setCurrentText(module)

    def on_ocr_changed(self):
        module = self.bottomBar.ocr_selector.selector.currentText()
        tgt_selector = self.configPanel.ocr_config_panel.module_combobox
        if tgt_selector.currentText() != module and module in GET_VALID_OCR():
            tgt_selector.setCurrentText(module)

    def on_trans_changed(self):
        module = self.bottomBar.trans_selector.selector.currentText()
        tgt_selector = self.configPanel.trans_config_panel.module_combobox
        if tgt_selector.currentText() != module and module in GET_VALID_TRANSLATORS():
            tgt_selector.setCurrentText(module)

    def on_trans_src_changed(self):
        sender = self.sender()
        text = sender.currentData()
        if text is None:
            text = lang_display_to_key(sender.currentText())
        translator = self.module_manager.translator
        if translator is not None:
            translator.set_source(text)
        pcfg.module.translate_source = text
        combobox = self.configPanel.trans_config_panel.source_combobox
        if sender != combobox:
            combobox.blockSignals(True)
            combobox.setCurrentText(lang_display_label(text))
            combobox.blockSignals(False)
        combobox = self.bottomBar.trans_selector.src_selector
        if sender != combobox:
            combobox.blockSignals(True)
            combobox.setCurrentText(lang_display_label(text))
            combobox.blockSignals(False)

    def on_trans_tgt_changed(self):
        sender = self.sender()
        text = sender.currentData()
        if text is None:
            text = lang_display_to_key(sender.currentText())
        translator = self.module_manager.translator
        if translator is not None:
            translator.set_target(text)
        pcfg.module.translate_target = text
        combobox = self.configPanel.trans_config_panel.target_combobox
        if sender != combobox:
            combobox.blockSignals(True)
            combobox.setCurrentText(lang_display_label(text))
            combobox.blockSignals(False)
        combobox = self.bottomBar.trans_selector.tgt_selector
        if sender != combobox:
            combobox.blockSignals(True)
            combobox.setCurrentText(lang_display_label(text))
            combobox.blockSignals(False)

    def on_inpaint_changed(self):
        module = self.bottomBar.inpaint_selector.selector.currentText()
        tgt_selector = self.configPanel.inpaint_config_panel.module_combobox
        if tgt_selector.currentText() != module and module in GET_VALID_INPAINTERS():
            tgt_selector.setCurrentText(module)

    def on_transpagebtn_pressed(self, run_target: bool):
        page_key = self.imgtrans_proj.current_img
        if page_key is None:
            return

        blkitem_list = self.st_manager.textblk_item_list

        if len(blkitem_list) < 1:
            return
        
        self.translateBlkitemList(blkitem_list, -1)

    def current_page_source_texts(self) -> List[str]:
        blkitem_list = self.st_manager.textblk_item_list
        if len(blkitem_list) > 0:
            blkitem_list = sorted(blkitem_list, key=lambda item: item.idx)
            texts = []
            for blkitem in blkitem_list:
                texts.append(self.st_manager.pairwidget_list[blkitem.idx].e_source.toPlainText())
            return texts

        page_key = self.imgtrans_proj.current_img
        if page_key is None or page_key not in self.imgtrans_proj.pages:
            return []
        return [blk.get_text() for blk in self.imgtrans_proj.pages[page_key]]

    def show_translation_benchmark_window(self, checked: bool = False):
        page_key = self.imgtrans_proj.current_img
        if page_key is None:
            create_info_dialog(self.tr('Open a project page before running a translation benchmark.'))
            return

        source_texts = self.current_page_source_texts()
        if len(source_texts) == 0 or not any(text.strip() for text in source_texts):
            create_info_dialog(self.tr('The current page has no source text to benchmark.'))
            return

        self.translation_benchmark_window = TranslationBenchmarkWindow(
            source_texts,
            pcfg.module.translator,
            self.imgtrans_proj,
            page_key,
            self,
        )
        self.translation_benchmark_window.show()
        self.translation_benchmark_window.raise_()
        self.translation_benchmark_window.activateWindow()

    def show_model_download_window(self, checked: bool = False):
        self.model_download_window = ModelDownloadWindow(self)
        self.model_download_window.show()
        self.model_download_window.raise_()
        self.model_download_window.activateWindow()

    def translateBlkitemList(self, blkitem_list: List, mode: int) -> bool:

        tgt_img = self.imgtrans_proj.img_array
        if tgt_img is None:
            return False
        tgt_mask = self.imgtrans_proj.mask_array
        
        if len(blkitem_list) < 1:
            return False
        
        self.global_search_widget.set_document_edited()
        
        im_h, im_w = tgt_img.shape[:2]

        blk_list, blk_ids = [], []
        for blkitem in blkitem_list:
            blk: TextBlock = blkitem.blk
            blk._bounding_rect = blkitem.absBoundingRect()
            blk.text = self.st_manager.pairwidget_list[blkitem.idx].e_source.toPlainText()
            blk_ids.append(blkitem.idx)
            blk.set_lines_by_xywh(blk._bounding_rect, angle=-blk.angle, x_range=[0, im_w-1], y_range=[0, im_h-1], adjust_bbox=True)
            blk_list.append(blk)

        self.module_manager.runBlktransPipeline(blk_list, tgt_img, mode, blk_ids, tgt_mask = tgt_mask)
        return True


    def finishTranslatePage(self, page_key):
        if page_key == self.imgtrans_proj.current_img:
            self.st_manager.updateTranslation()

    def on_imgtrans_pipeline_finished(self):
        self.backup_blkstyles.clear()
        self._run_imgtrans_wo_textstyle_update = False
        self.postprocess_mt_toggle = True
        if self._gloss_scan_pending:
            self.finish_gloss_scan_current_manga()
        else:
            self.sync_translator_glossary_to_project(update_ui=True)
        if pcfg.module.empty_runcache and not (shared.HEADLESS or shared.HEADLESS_CONTINUOUS):
            self.module_manager.unload_all_models()
        if shared.args.export_translation_txt:
            self.on_export_txt('translation')
        if shared.args.export_source_txt:
            self.on_export_txt('source')
        if self._gui_batch_options is not None:
            if self._gui_batch_cancel_requested:
                self.finish_gui_batch_processing(stopped=True)
                return
            self.finish_current_gui_batch_project()
            self._gui_batch_completed += 1
            self._update_gui_batch_progress()
            self.run_next_gui_batch_project()
            return
        if shared.HEADLESS or shared.HEADLESS_CONTINUOUS:
            self.run_next_dir()

    def postprocess_translations(self, blk_list: List[TextBlock]) -> None:
        src_is_cjk = is_cjk(pcfg.module.translate_source)
        tgt_is_cjk = is_cjk(pcfg.module.translate_target)
        if tgt_is_cjk:
            for blk in blk_list:
                if src_is_cjk:
                    blk.translation = full_len(blk.translation)
                else:
                    blk.translation = half_len(blk.translation)
                    blk.translation = re.sub(r'([?.!"])\s+', r'\1', blk.translation)    # remove spaces following punctuations
        else:
            for blk in blk_list:
                if blk.vertical:
                    blk.alignment = TextAlignment.Center
                blk.translation = half_len(blk.translation)
                blk.vertical = False

        for blk in blk_list:
            blk.translation = self.mtSubWidget.sub_text(blk.translation)
            if pcfg.let_uppercase_flag:
                blk.translation = blk.translation.upper()

    def on_pagtrans_finished(self, page_index: int):
        blk_list = self.imgtrans_proj.get_blklist_byidx(page_index)
        ffmt_list = None
        if len(self.backup_blkstyles) == self.imgtrans_proj.num_pages and len(self.backup_blkstyles[page_index]) == len(blk_list):
            ffmt_list: List[FontFormat] = self.backup_blkstyles[page_index]

        self.postprocess_translations(blk_list)
                
        # override font format if necessary
        override_fnt_size = pcfg.let_fntsize_flag == 1
        override_fnt_stroke = pcfg.let_fntstroke_flag == 1
        override_fnt_color = pcfg.let_fntcolor_flag == 1
        override_fnt_scolor = pcfg.let_fnt_scolor_flag == 1
        override_alignment = pcfg.let_alignment_flag == 1
        override_effect = pcfg.let_fnteffect_flag == 1
        override_writing_mode = pcfg.let_writing_mode_flag == 1
        override_font_family = pcfg.let_family_flag == 1
        gf = self.textPanel.formatpanel.global_format

        inpaint_only = pcfg.module.enable_inpaint
        inpaint_only = inpaint_only and not (pcfg.module.enable_detect or pcfg.module.enable_ocr or pcfg.module.enable_translate)
        
        if not inpaint_only:
            for ii, blk in enumerate(blk_list):
                if self._run_imgtrans_wo_textstyle_update and ffmt_list is not None:
                    blk.fontformat.merge(ffmt_list[ii])
                else:
                    if override_fnt_size or \
                        blk.font_size < 0:  # fall back to global font size if font size is not valid, it will be set to -1 for detected blocks
                        blk.font_size = gf.font_size
                    elif blk._detected_font_size > 0 and not pcfg.module.enable_detect:
                        blk.font_size = blk._detected_font_size
                    if override_fnt_stroke:
                        blk.stroke_width = gf.stroke_width
                    elif pcfg.module.enable_ocr:
                        blk.recalulate_stroke_width()
                    if override_fnt_color:
                        blk.set_font_colors(fg_colors=gf.frgb)
                    if override_fnt_scolor:
                        blk.set_font_colors(bg_colors=gf.srgb)
                    if override_alignment:
                        blk.alignment = gf.alignment
                    elif pcfg.module.enable_detect and not blk.src_is_vertical:
                        blk.recalulate_alignment()
                    if override_effect:
                        blk.opacity = gf.opacity
                        blk.shadow_color = gf.shadow_color
                        blk.shadow_radius = gf.shadow_radius
                        blk.shadow_strength = gf.shadow_strength
                        blk.shadow_offset = gf.shadow_offset
                    if override_writing_mode:
                        blk.vertical = gf.vertical
                    if override_font_family or blk.font_family is None:
                        blk.font_family = gf.font_family
                        if blk.rich_text:
                            blk.rich_text = set_html_family(blk.rich_text, gf.font_family)
                    
                    blk.line_spacing = gf.line_spacing
                    blk.letter_spacing = gf.letter_spacing
                    blk.italic = gf.italic
                    blk.bold = gf.bold
                    blk.underline = gf.underline
                    sw = blk.stroke_width
                    if sw > 0 and pcfg.module.enable_ocr and pcfg.module.enable_detect and not override_fnt_size:
                        blk.font_size = blk.font_size / (1 + sw)

            self.st_manager.auto_textlayout_flag = pcfg.let_autolayout_flag and \
                (pcfg.module.enable_detect or pcfg.module.enable_translate)
        
        if page_index != self.pageList.currentIndex().row():
            self.pageList.setCurrentRow(page_index)
        else:
            self.imgtrans_proj.set_current_img_byidx(page_index)
            self.canvas.updateCanvas()
            self.st_manager.updateSceneTextitems()

        if not pcfg.module.enable_detect and pcfg.module.enable_translate:
            for blkitem in self.st_manager.textblk_item_list:
                blkitem.squeezeBoundingRect()

        if page_index + 1 == self.imgtrans_proj.num_pages:
            self.st_manager.auto_textlayout_flag = False

        # save proj file on page trans finished
        self.save_project_safely(self.tr('page translation finish'), notify_user=False)

        self.saveCurrentPage(False, False)

    def on_page_decensor_finished(self, page_index: int):
        if page_index < 0 or page_index >= self.imgtrans_proj.num_pages:
            return
        page_name = self.imgtrans_proj.idx2pagename(page_index)
        if page_index == self.pageList.currentIndex().row():
            self.imgtrans_proj.set_current_img_byidx(page_index)
            self.canvas.updateCanvas()
        self.save_project_safely(self.tr('page decensor finish'), notify_user=False)
        if page_index == self.pageList.currentIndex().row():
            self.saveCurrentPage(False, False)
        if self._decensor_current_page_request == page_name:
            self._decensor_current_page_request = None
            try:
                mask = self.imgtrans_proj.load_decensor_mask_by_imgname(page_name)
                if mask is None or not (mask > 0).any():
                    create_info_dialog(self.tr(
                        'No censor mask was detected. You can draw/select a repair mask manually and run Censor Restoration again. '
                        'No censor mask found. Try debug masks or adjust gray/banded censor detection settings. '
                        'The text inpaint mask will not be used automatically.'
                    ))
                else:
                    create_info_dialog(self.tr('Censor Restoration finished for the current page.'))
            except Exception as e:
                LOGGER.warning(f'Could not inspect Censor Restoration mask for {page_name}: {e}')

    def on_savestate_changed(self, unsaved: bool):
        save_state = self.tr('unsaved') if unsaved else self.tr('saved')
        self.titleBar.setTitleContent(save_state=save_state)

    def on_textstack_changed(self):
        if not self.page_changing:
            self.global_search_widget.set_document_edited()

    def on_run_blktrans(self, mode: int):
        blkitem_list = self.canvas.selected_text_items()
        self.translateBlkitemList(blkitem_list, mode)

    def on_blktrans_finished(self, mode: int, blk_ids: List[int]):

        if len(blk_ids) < 1:
            return
        
        blkitem_list = [self.st_manager.textblk_item_list[idx] for idx in blk_ids]

        pairw_list = []
        for blk in blkitem_list:
            pairw_list.append(self.st_manager.pairwidget_list[blk.idx])
        self.canvas.push_undo_command(RunBlkTransCommand(self.canvas, blkitem_list, pairw_list, mode))

    def on_imgtrans_progressbox_showed(self):
        msg_size = self.module_manager.progress_msgbox.size()
        size = self.size()
        p = self.mapToGlobal(QPoint(size.width() - msg_size.width(),
                                    size.height() - msg_size.height()))
        self.module_manager.progress_msgbox.move(p)

    def on_closebtn_clicked(self):
        if self.imsave_thread.isRunning():
            self.imsave_thread.finished.connect(self.close)
            mb = FrameLessMessageBox()
            mb.setText(self.tr('Saving image...'))
            self.imsave_thread.finished.connect(mb.close)
            mb.exec()
            return
        self.close()

    def on_display_lang_changed(self, lang: str):
        if lang != pcfg.display_lang:
            pcfg.display_lang = lang
            self.set_display_lang(lang)
    
    def run_imgtrans(self):
        if not self.imgtrans_proj.is_all_pages_no_text and not pcfg.module.keep_exist_textlines:
            # 创建自定义消息框，添加"继续运行"选项
            msgBox = QMessageBox(self)
            msgBox.setIcon(QMessageBox.Question)
            msgBox.setWindowTitle(self.tr('Confirmation'))
            msgBox.setText(self.tr('\"Run\" will clear previous results, \"Continue\" will try to run from previous progress'))
            
            # 添加三个按钮（直接使用中文）
            restart_btn = msgBox.addButton(self.tr('Run'), QMessageBox.YesRole)
            continue_btn = msgBox.addButton(self.tr('Continue'), QMessageBox.AcceptRole)
            cancel_btn = msgBox.addButton(self.tr('Cancel'), QMessageBox.RejectRole)
            
            msgBox.setDefaultButton(continue_btn)
            msgBox.exec_()
            
            clicked_button = msgBox.clickedButton()
            if clicked_button == cancel_btn:
                return  # 取消，不执行任何操作
            elif clicked_button == continue_btn:
                # 继续运行：只处理没有文本的页面
                self.on_run_imgtrans(continue_mode=True)
                return
            # 如果是 restart_btn，继续执行下面的代码（重新运行）
        self.on_run_imgtrans()

    def run_imgtrans_wo_textstyle_update(self):
        self._run_imgtrans_wo_textstyle_update = True
        self.run_imgtrans()

    def run_translate_only(self):
        if self.imgtrans_proj.is_empty:
            return
        self.backup_blkstyles.clear()
        if self.bottomBar.textblockChecker.isChecked():
            self.bottomBar.textblockChecker.click()
        self.postprocess_mt_toggle = False
        self.st_manager.updateTextBlkList()

        page_names = self.imgtrans_proj.pipeline_pages(skip_ignored=True)
        if len(page_names) == 0:
            return
        self.backup_blkstyles = [[] for _ in range(self.imgtrans_proj.num_pages)]
        for page_name in page_names:
            blklist = self.imgtrans_proj.pages[page_name]
            self.imgtrans_proj.set_page_progress(page_name, 0)
            ffmt_list = []
            self.backup_blkstyles[self.imgtrans_proj.pagename2idx(page_name)] = ffmt_list
            for textblk in blklist:
                ffmt_list.append(textblk.fontformat.deepcopy())
                textblk.rich_text = ''
                textblk.vertical = textblk.src_is_vertical

        self.module_manager.runTranslateOnlyPipeline()

    def _translator_supports_review(self) -> bool:
        translator = self.module_manager.translator
        return (
            translator is not None
            and hasattr(translator, 'supports_translation_review')
            and translator.supports_translation_review()
        )

    def _prepare_review_run(self) -> bool:
        if self.imgtrans_proj.is_empty:
            return False
        if not self._translator_supports_review():
            create_info_dialog(self.tr('Select ChatGPT, LLM_API_Translator, or Two-Step Translator before running translation review.'))
            return False
        if self.bottomBar.textblockChecker.isChecked():
            self.bottomBar.textblockChecker.click()
        self.postprocess_mt_toggle = False
        self.st_manager.updateTextBlkList()
        return True

    def run_review_current_page(self):
        if not self._prepare_review_run():
            return
        page_name = self.imgtrans_proj.current_img
        if not page_name or page_name not in self.imgtrans_proj.pages:
            create_info_dialog(self.tr('Open a project page before running translation review.'))
            return
        self.module_manager.runReviewPipeline(pages_to_process=[page_name])

    def run_review_all_pages(self):
        if not self._prepare_review_run():
            return
        page_names = self.imgtrans_proj.pipeline_pages(skip_ignored=True)
        if len(page_names) == 0:
            create_info_dialog(self.tr('No non-ignored pages are available for translation review.'))
            return
        self.module_manager.runReviewPipeline()

    def run_decensor_current_page(self):
        if self.imgtrans_proj.is_empty or not self.imgtrans_proj.current_img:
            create_info_dialog(self.tr('Open a project page before running Censor Restoration.'))
            return

        page_name = self.imgtrans_proj.current_img
        if page_name not in self.imgtrans_proj.pages:
            create_info_dialog(self.tr('The current page is not available in the project.'))
            return

        if self.module_manager.inpainter is None:
            create_info_dialog(self.tr('Select an inpainter before running Censor Restoration.'))
            return

        if self.bottomBar.textblockChecker.isChecked():
            self.bottomBar.textblockChecker.click()
        self._decensor_current_page_request = page_name
        self.module_manager.runDecensorPipeline([page_name])

    def _show_reinpaint_progress(self, message: str):
        try:
            progress_box = self.module_manager.progress_msgbox
            progress_box.hide_all_bars()
            progress_box.inpaint_bar.show()
            progress_box.zero_progress()
            progress_box.updateInpaintProgress(0, message)
            progress_box.show()
        except Exception:
            LOGGER.debug('Could not show Re-Inpaint progress box.', exc_info=True)

    def _current_page_reinpaint_mask(self, page_name: str):
        img = self.imgtrans_proj.img_array
        if img is None:
            return None
        masks = []
        if page_name == self.imgtrans_proj.current_img and self.imgtrans_proj.mask_array is not None:
            stored_mask = self.imgtrans_proj.mask_array
        else:
            try:
                stored_mask = self.imgtrans_proj.load_mask_by_imgname(page_name)
            except Exception:
                LOGGER.warning(f'Could not load stored inpaint mask for {page_name}.', exc_info=True)
                stored_mask = None
        masks.append(stored_mask)

        try:
            decensor_mask = self.imgtrans_proj.load_decensor_mask_by_imgname(page_name)
        except Exception:
            LOGGER.warning(f'Could not load stored decensor mask for {page_name}.', exc_info=True)
            decensor_mask = None
        masks.append(decensor_mask)

        return combine_inpaint_masks(
            masks,
            img.shape[:2],
            dilate=pcfg.drawpanel.reinpaint_dilate_ksize,
        )

    def run_reinpaint_current_page(self):
        if self.imgtrans_proj.is_empty or not self.imgtrans_proj.current_img:
            create_info_dialog(self.tr('Open a project page before re-running inpainting.'))
            return

        page_name = self.imgtrans_proj.current_img
        if page_name not in self.imgtrans_proj.pages:
            create_info_dialog(self.tr('The current page is not available in the project.'))
            return

        if self.module_manager.inpainterBusy():
            create_info_dialog(self.tr('Inpainting is already running. Please wait until it finishes.'))
            return

        if self.module_manager.inpainter is None:
            fallback = 'lama_large_512px'
            if fallback in GET_VALID_INPAINTERS():
                LOGGER.info(f'No active inpainter; loading fallback {fallback} for Re-Inpaint.')
                self.module_manager.setInpainter(fallback)
                create_info_dialog(self.tr('Loading fallback inpainter. Run Re-Inpaint again after it is ready.'))
            else:
                create_info_dialog(self.tr('Select an inpainter before re-running inpainting.'))
            return

        mask = self._current_page_reinpaint_mask(page_name)
        if mask is None or not np.any(mask > 0):
            create_info_dialog(self.tr('No inpaint masks found for the current page.'))
            return

        bbox = mask_bounding_rect(mask)
        if bbox is None:
            create_info_dialog(self.tr('No inpaint masks found for the current page.'))
            return

        img = self.imgtrans_proj.img_array
        x1, y1, x2, y2 = enlarge_window(list(bbox), img.shape[1], img.shape[0])
        inpaint_dict = {
            'img': np.copy(img[y1:y2, x1:x2]),
            'mask': mask[y1:y2, x1:x2],
            'inpaint_rect': [x1, y1, x2, y2],
            'operation': 'reinpaint_current_page',
            'page_name': page_name,
        }
        self._reinpaint_current_page_request = page_name
        LOGGER.info(
            f'Re-running inpainting on current page {page_name}; '
            f'dilate={pcfg.drawpanel.reinpaint_dilate_ksize}; rect={[x1, y1, x2, y2]}.'
        )
        self._show_reinpaint_progress(self.tr('Re-running inpainting on current page...'))
        self.module_manager.canvas_inpaint(inpaint_dict)

    def _can_run_inpaint_optimization(self) -> bool:
        if self.imgtrans_proj.is_empty:
            create_info_dialog(self.tr('Open a project before optimizing inpainting.'))
            return False
        if self.module_manager.anyPipelineThreadRunning():
            create_info_dialog(self.tr('Another pipeline is already running. Please wait until it finishes.'))
            return False
        if self.module_manager.textdetector is None:
            create_info_dialog(self.tr('Select a text detector before optimizing inpainting.'))
            return False
        if self.module_manager.inpainter is None:
            create_info_dialog(self.tr('Select an inpainter before optimizing inpainting.'))
            return False
        if self.bottomBar.textblockChecker.isChecked():
            self.bottomBar.textblockChecker.click()
        return True

    def run_inpaint_optimize_current_page(self):
        if not self._can_run_inpaint_optimization():
            return
        page_name = self.imgtrans_proj.current_img
        if not page_name or page_name not in self.imgtrans_proj.pages:
            create_info_dialog(self.tr('Open a project page before optimizing inpainting.'))
            return
        self.module_manager.runInpaintOptimizationPipeline([page_name])

    def run_inpaint_optimize_all_pages(self):
        if not self._can_run_inpaint_optimization():
            return
        page_names = self.imgtrans_proj.pipeline_pages(skip_ignored=True)
        if len(page_names) == 0:
            create_info_dialog(self.tr('No non-ignored pages are available for inpaint optimization.'))
            return
        self.module_manager.runInpaintOptimizationPipeline()

    def run_project_upscale_2x(self):
        self.run_project_upscale(2.0)

    def run_project_upscale_using_settings(self):
        self.configPanel.on_upscale_numeric_changed()
        self.configPanel.on_upscale_quality_changed()
        self.run_project_upscale(float(pcfg.upscale_factor))

    def run_project_upscale(self, factor: float):
        if self.imgtrans_proj.is_empty:
            create_info_dialog(self.tr('Open a project before upscaling project images.'))
            return
        if self.module_manager.anyPipelineThreadRunning() or self.project_upscale_thread.isRunning():
            create_info_dialog(self.tr('Another pipeline or upscaling task is already running. Please wait until it finishes.'))
            return
        if self.canvas.text_change_unsaved():
            self.saveCurrentPage(update_scene_text=True, save_proj=True, restore_interface=True)

        page_names = list(self.imgtrans_proj.pages.keys())
        marked_pages = [page for page in page_names if filename_has_upscale_marker(page)]
        if marked_pages:
            msg = self.tr(
                '{count} project page(s) already contain "upscaled" in the filename.\n\n'
                'Choose Yes to upscale them again, No to skip them, or Cancel to stop.'
            ).format(count=len(marked_pages))
            answer = QMessageBox.question(
                self,
                self.tr('Already Upscaled Images Found'),
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.No:
                page_names = [page for page in page_names if page not in marked_pages]
        if not page_names:
            create_info_dialog(self.tr('No project pages remain to upscale.'))
            return

        self.configPanel.on_upscale_numeric_changed()
        self.configPanel.on_upscale_quality_changed()
        started = self.project_upscale_thread.runUpscale(
            self.imgtrans_proj.directory,
            page_names,
            factor,
            pcfg.upscale_max_long_edge,
            pcfg.upscale_skip_if_long_edge_above,
            pcfg.upscale_quality,
        )
        if started:
            self.project_upscale_thread.progress_bar.setTaskName(
                self.tr('Upscaling project images ({factor}x): ').format(factor=f'{factor:g}')
            )
            self.project_upscale_thread.progress_bar.zero_progress()
            self.project_upscale_thread.progress_bar.show()

    def on_project_upscale_progress(self, current: int, total: int):
        progress = int(current / max(total, 1) * 100)
        self.project_upscale_thread.progress_bar.updateTaskProgress(progress, f' {current}/{total}')

    def on_project_upscale_stop(self):
        self.project_upscale_thread.requestStop()
        self.project_upscale_thread.progress_bar.hide()

    def on_project_upscale_finished(self, replacements, skipped, failures, stopped, staging_dir):
        self.project_upscale_thread.progress_bar.hide()
        if stopped:
            create_info_dialog(self.tr('Project image upscaling was stopped. No source images were replaced.'))
            return
        if failures:
            details = '\n'.join(f'- {name}: {reason}' for name, reason in failures[:8])
            create_error_dialog(
                RuntimeError(details),
                self.tr('Project image upscaling failed. No source images were replaced.'),
            )
            return
        if not replacements:
            if staging_dir:
                shutil.rmtree(staging_dir, ignore_errors=True)
            create_info_dialog(self.tr('No project pages met the configured upscaling size limits.'))
            return
        try:
            project_path = self.imgtrans_proj.proj_path
            self.imgtrans_proj.replace_pages_with_upscaled_files(replacements)
            self.openJsonProj(project_path)
            msg = self.tr('Upscaled and replaced {count} project page(s).').format(count=len(replacements))
            if skipped:
                msg += self.tr('\nSkipped {count} page(s) because of configured size limits.').format(count=len(skipped))
            create_info_dialog(msg)
        except Exception as e:
            create_error_dialog(e, self.tr('Failed to activate upscaled project images.'))
        finally:
            if staging_dir:
                shutil.rmtree(staging_dir, ignore_errors=True)

    def run_batch_project_upscale_using_settings(self):
        if self.module_manager.anyPipelineThreadRunning() or self.batch_project_upscale_thread.isRunning():
            create_info_dialog(self.tr('Another pipeline or batch upscaling task is already running. Please wait until it finishes.'))
            return
        if self.project_upscale_thread.isRunning():
            create_info_dialog(self.tr('Project image upscaling is already running. Please wait until it finishes.'))
            return

        start_dir = getattr(self.imgtrans_proj, 'directory', '') or ''
        root_dir = QFileDialog.getExistingDirectory(
            self,
            self.tr('Select Parent Folder for Batch Upscaling'),
            start_dir,
        )
        if not root_dir:
            return

        project_dirs = collect_batch_project_dirs(root_dir)
        if not project_dirs:
            create_info_dialog(self.tr('No source-image subfolders found. Generated output folders are ignored.'))
            return

        jobs = []
        marked_count = 0
        for directory in project_dirs:
            page_names = find_all_imgs(directory, abs_path=False, sort=True)
            marked_count += sum(1 for page in page_names if filename_has_upscale_marker(page))
            jobs.append((directory, page_names))
        if marked_count:
            answer = QMessageBox.question(
                self,
                self.tr('Already Upscaled Images Found'),
                self.tr(
                    '{count} image(s) in the selected source folders already contain "upscaled" in the filename.\n\n'
                    'Choose Yes to upscale them again, No to skip them, or Cancel to stop.'
                ).format(count=marked_count),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.No:
                jobs = [
                    (directory, [page for page in page_names if not filename_has_upscale_marker(page)])
                    for directory, page_names in jobs
                ]
                jobs = [(directory, page_names) for directory, page_names in jobs if page_names]
        if not jobs:
            create_info_dialog(self.tr('No source images remain to upscale.'))
            return

        if self.canvas.text_change_unsaved():
            self.saveCurrentPage(update_scene_text=True, save_proj=True, restore_interface=True)
        self.configPanel.on_upscale_numeric_changed()
        self.configPanel.on_upscale_quality_changed()
        started = self.batch_project_upscale_thread.runUpscale(
            jobs,
            float(pcfg.upscale_factor),
            pcfg.upscale_max_long_edge,
            pcfg.upscale_skip_if_long_edge_above,
            pcfg.upscale_quality,
        )
        if not started:
            return

        self._batch_project_upscale_dirs = {osp.normcase(osp.abspath(directory)) for directory, _ in jobs}
        progress_box = self.imgtrans_progress_msgbox
        progress_box.hide_all_bars()
        progress_box.detect_bar.description = self.tr('Batch Upscaling: ')
        progress_box.detect_bar.show()
        progress_box.zero_progress()
        progress_box.show()

    def on_batch_project_upscale_progress(self, current: int, total: int, folder_name: str):
        progress = int(current / max(total, 1) * 100)
        self.imgtrans_progress_msgbox.updateDetectProgress(progress, f' {current}/{total} - {folder_name}')

    def on_batch_project_upscale_stop(self):
        if self.batch_project_upscale_thread.isRunning():
            self.batch_project_upscale_thread.requestStop()

    def _restore_batch_project_upscale_progress(self):
        self.imgtrans_progress_msgbox.hide()
        self.imgtrans_progress_msgbox.detect_bar.description = self.tr('Detecting: ')
        self.imgtrans_progress_msgbox.zero_progress()

    def on_batch_project_upscale_finished(self, replaced_count, skipped_count, failures, stopped):
        self._restore_batch_project_upscale_progress()
        active_dir = osp.normcase(osp.abspath(getattr(self.imgtrans_proj, 'directory', '') or ''))
        if active_dir and active_dir in getattr(self, '_batch_project_upscale_dirs', set()):
            self.openJsonProj(self.imgtrans_proj.proj_path)
        self._batch_project_upscale_dirs = set()

        if self._gui_batch_upscale_pending:
            self._gui_batch_upscale_pending = False
            if stopped or self._gui_batch_cancel_requested:
                self.finish_gui_batch_processing(stopped=True)
                return
            if failures:
                details = '\n'.join(f'- {name}: {reason}' for name, reason in failures[:8])
                create_error_dialog(
                    RuntimeError(details),
                    self.tr('Batch upscaling failed before translation. Batch processing was stopped.'),
                )
                self.finish_gui_batch_processing(stopped=True)
                return
            self.imgtrans_progress_msgbox.show_all_bars()
            self.imgtrans_progress_msgbox.set_batch_mode(True)
            self._update_gui_batch_progress()
            self.run_next_gui_batch_project()
            return

        if stopped:
            create_info_dialog(
                self.tr('Batch upscaling stopped. Replaced {replaced} image(s) before stopping.').format(
                    replaced=replaced_count,
                )
            )
            return
        if failures:
            details = '\n'.join(f'- {name}: {reason}' for name, reason in failures[:8])
            create_error_dialog(
                RuntimeError(details),
                self.tr(
                    'Batch upscaling completed with errors after replacing {replaced} image(s).'
                ).format(replaced=replaced_count),
            )
            return
        msg = self.tr('Batch upscaling replaced {count} image(s).').format(count=replaced_count)
        if skipped_count:
            msg += self.tr('\nSkipped {count} image(s) because of configured size limits.').format(count=skipped_count)
        create_info_dialog(msg)

    def remove_current_page_masks(self):
        if self.imgtrans_proj.is_empty or not self.imgtrans_proj.current_img:
            create_info_dialog(self.tr('Open a project page before removing masks.'))
            return
        if self.imgtrans_proj.mask_array is None or self.imgtrans_proj.inpainted_array is None:
            create_info_dialog(self.tr('No inpaint masks found for the current page.'))
            return
        if not np.any(self.imgtrans_proj.mask_array > 0):
            create_info_dialog(self.tr('No inpaint masks found for the current page.'))
            return

        self.canvas.push_draw_command(RemoveAllMasksCommand(self.canvas))
        self.save_project_safely(self.tr('remove current page masks'), notify_user=False)
        self.saveCurrentPage(update_scene_text=False, save_proj=True)
        create_info_dialog(self.tr('All masks and related inpainting were removed from the current page.'))

    def on_reinpaint_current_page_finished(self, inpaint_dict: dict):
        if inpaint_dict.get('operation') != 'reinpaint_current_page':
            return
        page_name = inpaint_dict.get('page_name')
        if self._reinpaint_current_page_request != page_name:
            return
        self._reinpaint_current_page_request = None
        QTimer.singleShot(0, self._finalize_reinpaint_current_page)

    def _finalize_reinpaint_current_page(self):
        try:
            self.module_manager.progress_msgbox.updateInpaintProgress(100)
            self.module_manager.progress_msgbox.hide()
        except Exception:
            LOGGER.debug('Could not hide Re-Inpaint progress box.', exc_info=True)
        self.canvas.updateCanvas()
        self.pageList.viewport().update()
        self.save_project_safely(self.tr('current page re-inpaint'), notify_user=False)
        self.saveCurrentPage(update_scene_text=False, save_proj=True)
        create_info_dialog(self.tr('Inpainting re-run completed for current page.'))

    def on_reinpaint_current_page_failed(self):
        if self._reinpaint_current_page_request is None:
            return
        page_name = self._reinpaint_current_page_request
        self._reinpaint_current_page_request = None
        try:
            self.module_manager.progress_msgbox.hide()
        except Exception:
            LOGGER.debug('Could not hide Re-Inpaint progress box after failure.', exc_info=True)
        LOGGER.error(f'Re-Inpaint failed for current page {page_name}.')
        create_info_dialog(self.tr('Re-running inpainting failed for the current page. Check the log for details.'))

    def on_run_imgtrans(self, continue_mode=False):
        self.backup_blkstyles.clear()

        if self.bottomBar.textblockChecker.isChecked():
            self.bottomBar.textblockChecker.click()
        self.postprocess_mt_toggle = False

        all_disabled = pcfg.module.all_stages_disabled()
        
        pages_to_process = []
        processable_pages = self.imgtrans_proj.pipeline_pages(skip_ignored=True)
        if len(processable_pages) == 0:
            create_info_dialog(self.tr('All pages are ignored for pipeline runs.'))
            return False
        
        # 继续模式：先检查哪些页面需要处理
        if continue_mode:
            for page_name in processable_pages:
                if not self.imgtrans_proj.get_page_progress(page_name):
                    pages_to_process.append(page_name)
            if len(pages_to_process) == 0:
                return False
        else:
            for page_name in processable_pages:
                self.imgtrans_proj.set_page_progress(page_name, 0)
        
        if pcfg.module.enable_detect:
            for page in processable_pages:
                if not pcfg.module.keep_exist_textlines:
                    if not pages_to_process:
                        # 没有指定pages_to_process，清空所有页面
                        self.imgtrans_proj.pages[page].clear()
        else:
            self.st_manager.updateTextBlkList()
            textblk: TextBlock = None
            self.backup_blkstyles = [[] for _ in range(self.imgtrans_proj.num_pages)]
            for page_name in processable_pages:
                blklist = self.imgtrans_proj.pages[page_name]
                # 如果指定了pages_to_process，跳过不需要处理的页面
                if pages_to_process and page_name not in pages_to_process:
                    continue
                    
                ffmt_list = []
                self.backup_blkstyles[self.imgtrans_proj.pagename2idx(page_name)] = ffmt_list
                for textblk in blklist:
                    if not pcfg.module.enable_detect:
                        ffmt_list.append(textblk.fontformat.deepcopy())
                    # 继续模式且没有指定pages_to_process时：跳过已有文本的文本块
                    if continue_mode and not pages_to_process and textblk.text and len(textblk.text) > 0:
                        continue
                    if pcfg.module.enable_ocr:
                        textblk.text = []
                        textblk.set_font_colors((0, 0, 0), (0, 0, 0))
                    if pcfg.module.enable_translate or (all_disabled and not self._run_imgtrans_wo_textstyle_update) or pcfg.module.enable_ocr:
                        textblk.rich_text = ''
                    textblk.vertical = textblk.src_is_vertical
        
        # 如果有指定pages_to_process或者是continue_mode，则传递页面列表
        self.module_manager.runImgtransPipeline(pages_to_process if (pages_to_process or continue_mode) else None)
        return True

    def on_transpanel_changed(self):
        self.canvas.editor_index = self.rightComicTransStackPanel.currentIndex()
        if not self.canvas.textEditMode() and self.canvas.search_widget.isVisible():
            self.canvas.search_widget.hide()
        self.canvas.updateLayers()

    def import_tstyles(self):
        ddir = osp.dirname(pcfg.text_styles_path)
        p = QFileDialog.getOpenFileName(self, self.tr("Import Text Styles"), ddir, None, "(.json)")
        if not isinstance(p, str):
            p = p[0]
        if p == '':
            return
        try:
            load_textstyle_from(p, raise_exception=True)
            save_config()
            self.textPanel.formatpanel.textstyle_panel.setStyles(text_styles)
        except Exception as e:
            create_error_dialog(e, self.tr(f'Failed to load from {p}'))

    def export_tstyles(self):
        ddir = osp.dirname(pcfg.text_styles_path)
        savep = QFileDialog.getSaveFileName(self, self.tr("Save Text Styles"), ddir, None, "(.json)")
        if not isinstance(savep, str):
            savep = savep[0]
        if savep == '':
            return
        suffix = Path(savep).suffix
        if suffix != '.json':
            if suffix == '':
                savep = savep + '.json'
            else:
                savep = savep.replace(suffix, '.json')
        oldp = pcfg.text_styles_path
        try:
            pcfg.text_styles_path = savep
            save_text_styles(raise_exception=True)
            save_config()
        except Exception as e:
            create_error_dialog(e, self.tr(f'Failed save to {savep}'))
            pcfg.text_styles_path = oldp

    def fold_textarea(self, fold: bool):
        pcfg.fold_textarea = fold
        self.textPanel.textEditList.setFoldTextarea(fold)

    def show_source_text(self, show: bool):
        pcfg.show_source_text = show
        self.textPanel.textEditList.setSourceVisible(show)

    def show_trans_text(self, show: bool):
        pcfg.show_trans_text = show
        self.textPanel.textEditList.setTransVisible(show)

    def on_export_doc(self):
        if self.canvas.text_change_unsaved():
            self.st_manager.updateTextBlkList()
        self.export_doc_thread.exportAsDoc(self.imgtrans_proj)

    def _wait_for_image_saves(self):
        while self.imsave_thread.isRunning():
            self.app.processEvents()
            time.sleep(0.05)

    def on_export_comic_archive(self):
        try:
            if self.imgtrans_proj.is_empty:
                create_info_dialog(self.tr('Open a project before exporting a comic archive.'))
                return
            if self.canvas.text_change_unsaved():
                self.st_manager.updateTextBlkList()
            self.saveCurrentPage(update_scene_text=False, save_proj=True, restore_interface=True)
            self._wait_for_image_saves()

            dialog = QFileDialog()
            default_path = default_export_path(self.imgtrans_proj.directory, '.cbz')
            selected_file = str(dialog.getSaveFileUrl(
                self.parent(),
                self.tr('Export Comic Archive/PDF'),
                QUrl.fromLocalFile(default_path),
                filter=archive_export_filter(),
            )[0].toLocalFile())
            if selected_file == '':
                return
            if Path(selected_file).suffix == '':
                selected_file += '.cbz'

            exported_path = export_project(self.imgtrans_proj, selected_file)
            create_info_dialog(self.tr('Comic export written to ') + exported_path)
        except Exception as e:
            create_error_dialog(e, self.tr('Failed to export comic archive/PDF'))

    def on_import_doc(self):
        self.import_doc_thread.importDoc(self.imgtrans_proj)

    def on_export_txt(self, dump_target, suffix='.txt'):
        try:
            self.imgtrans_proj.dump_txt(dump_target=dump_target, suffix=suffix)
            create_info_dialog(self.tr('Text file exported to ') + self.imgtrans_proj.dump_txt_path(dump_target, suffix))
        except Exception as e:
            create_error_dialog(e, self.tr('Failed to export as TEXT file'))

    def on_import_trans_txt(self):
        try:
            selected_file = ''
            dialog = QFileDialog()
            selected_file = str(dialog.getOpenFileUrl(self.parent(), self.tr('Import *.md/*.txt'), filter="*.txt *.md *.TXT *.MD")[0].toLocalFile())
            if not osp.exists(selected_file):
                return

            all_matched, match_rst = self.imgtrans_proj.load_translation_from_txt(selected_file)
            matched_pages = match_rst['matched_pages']

            if self.imgtrans_proj.current_img in matched_pages:
                self.canvas.clear_undostack(update_saved_step=True)
                self.st_manager.updateSceneTextitems()

            if all_matched:
                msg = self.tr('Translation imported and matched successfully.')
            else:
                msg = self.tr('Imported txt file not fully matched with current project, please make sure source txt file structured like results from \"export TXT/markdown\"')
                if len(match_rst['missing_pages']) > 0:
                    msg += '\n' + self.tr('Missing pages: ') + '\n'
                    msg += '\n'.join(match_rst['missing_pages'])
                if len(match_rst['unexpected_pages']) > 0:
                    msg += '\n' + self.tr('Unexpected pages: ') + '\n'
                    msg += '\n'.join(match_rst['unexpected_pages'])
                if len(match_rst['unmatched_pages']) > 0:
                    msg += '\n' + self.tr('Unmatched pages: ') + '\n'
                    msg += '\n'.join(match_rst['unmatched_pages'])
                msg = msg.strip()

            for pagename in matched_pages:
                for blk in self.imgtrans_proj.pages[pagename]:
                    blk.translation = self.mtSubWidget.sub_text(blk.translation)
            
            create_info_dialog(msg)

        except Exception as e:
            create_error_dialog(e, self.tr('Failed to import translation from ') + selected_file)

    def on_toggle_page_ignore(self, page_name: str):
        if not page_name or page_name not in self.imgtrans_proj.pages:
            return
        self.imgtrans_proj.toggle_page_ignored(page_name)
        self.refresh_page_list_item(page_name)
        if self.save_project_safely(self.tr('saving ignored page state'), notify_user=True):
            self.canvas.setProjSaveState(False)

    def on_delete_page_data(self, page_name: str):
        if not page_name or page_name not in self.imgtrans_proj.pages:
            return
            
        reply = QMessageBox.question(self, self.tr('Delete Page Data'),
                                     self.tr('Are you sure you want to delete textboxes, masks, and inpainting for this page?'),
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return

        self.imgtrans_proj.pages[page_name] = []

        def _del(path):
            if path and osp.exists(path):
                os.remove(path)
                
        _del(self.imgtrans_proj.get_mask_path(page_name, get_last_modified=True))
        _del(self.imgtrans_proj.get_inpainted_path(page_name, get_last_modified=True))
        _del(self.imgtrans_proj.get_upscaled_path(page_name, get_last_modified=True))
        _del(self.imgtrans_proj.get_decensor_mask_path(page_name, get_last_modified=True))
        _del(self.imgtrans_proj.get_decensored_path(page_name, get_last_modified=True))
        
        if self.imgtrans_proj.current_img == page_name:
            self.imgtrans_proj.mask_array = None
            self.imgtrans_proj.inpainted_array = None
            self.canvas.clear_undostack(update_saved_step=True)
            self.st_manager.updateSceneTextitems()
            self.canvas.updateCanvas()
            
        if self.save_project_safely(self.tr('saving deleted page data state'), notify_user=True):
            self.canvas.setProjSaveState(False)

    def on_reveal_file(self, page_name: str = None):
        if page_name and page_name in self.imgtrans_proj.pages:
            current_img_path = osp.join(self.imgtrans_proj.directory, page_name)
        else:
            current_img_path = self.imgtrans_proj.current_img_path()
        if current_img_path is None:
            return
        if sys.platform == 'win32':
            # qprocess seems to fuck up with "\""
            p = "\""+str(Path(current_img_path))+"\""
            subprocess.Popen("explorer.exe /select,"+p, shell=True)
        elif sys.platform == 'darwin':
            p = "\""+current_img_path+"\""
            subprocess.Popen("open -R "+p, shell=True)

    def on_set_gsearch_widget(self):
        setup = self.leftBar.globalSearchChecker.isChecked()
        if setup:
            if self.leftStackWidget.isHidden():
                self.leftStackWidget.show()
            self.leftBar.showPageListLabel.setChecked(False)
            self.leftStackWidget.setCurrentWidget(self.global_search_widget)
        else:
            self.leftStackWidget.hide()

    def on_fin_export_doc(self):
        msg = QMessageBox()
        msg.setText(self.tr('Export to ') + self.imgtrans_proj.doc_path())
        msg.exec_()

    def on_fin_import_doc(self):
        self.st_manager.updateSceneTextitems()

    def on_global_replace_finished(self):
        rt = self.global_search_widget.replace_thread
        self.canvas.push_text_command(
            GlobalRepalceAllCommand(rt.sceneitem_list, rt.background_list, rt.target_text, self.imgtrans_proj)
        )
        rt.sceneitem_list = None
        rt.background_list = None

    def on_darkmode_triggered(self):
        pcfg.darkmode = self.titleBar.darkModeAction.isChecked()
        self.resetStyleSheet(reverse_icon=True)
        self.save_config()

    def ocr_postprocess(self, textblocks: List[TextBlock], img, ocr_module=None, **kwargs):
        for blk in textblocks:
            text = blk.get_text()
            blk.text = self.ocrSubWidget.sub_text(text)

        # 字体检测：在 OCR 完成后按配置执行（按需导入以减少启动开销）
        try:
            if pcfg.module.ocr_font_detect:
                try:
                    from utils import font_detect
                    for blk in textblocks:
                        try:
                            name, conf = font_detect.detect_font_from_block(img, blk)
                            blk._detected_font_name = name
                            blk._detected_font_confidence = float(conf)
                        except Exception:
                            # don't break the pipeline on detector errors
                            blk._detected_font_name = ''
                            blk._detected_font_confidence = 0.0
                except Exception:
                    # failed to import or run detector
                    pass
        except Exception:
            pass

    def translate_preprocess(self, translations: List[str] = None, textblocks: List[TextBlock] = None, translator = None, source_text:list = []):
        self.sync_project_glossary_to_translator(translator)
        for i in range(len(source_text)):
            source_text[i] = self.mtPreSubWidget.sub_text(source_text[i])

    def translate_postprocess(self, translations: List[str] = None, textblocks: List[TextBlock] = None, translator = None):
        self.sync_translator_glossary_to_project(translator, update_ui=False)
        if not self.postprocess_mt_toggle:
            return
        
        for ii, tr in enumerate(translations):
            translations[ii] = self.mtSubWidget.sub_text(tr)

    def on_copy_src(self):
        blks = self.canvas.selected_text_items()
        if len(blks) == 0:
            return
        
        if isinstance(self.module_manager.translator, GPTTranslator):
            src_list = [self.st_manager.pairwidget_list[blk.idx].e_source.toPlainText() for blk in blks]
            src_txt = ''
            for (prompt, num_src) in self.module_manager.translator._assemble_prompts(src_list, max_tokens=4294967295):
                src_txt += prompt
            src_txt = src_txt.strip()
        else:
            src_list = [self.st_manager.pairwidget_list[blk.idx].e_source.toPlainText().strip().replace('\n', ' ') for blk in blks]
            src_txt = '\n'.join(src_list)

        self.st_manager.app_clipborad.setText(src_txt, QClipboard.Mode.Clipboard)

    def on_paste_src(self):
        blks = self.canvas.selected_text_items()
        if len(blks) == 0:
            return

        src_widget_list = [self.st_manager.pairwidget_list[blk.idx].e_source for blk in blks]
        text_list = self.st_manager.app_clipborad.text().split('\n')
        
        n_paragraph = min(len(src_widget_list), len(text_list))
        if n_paragraph < 1:
            return
        
        src_widget_list = src_widget_list[:n_paragraph]
        text_list = text_list[:n_paragraph]

        self.canvas.push_undo_command(PasteSrcItemsCommand(src_widget_list, text_list))
    
    def run_batch(self, exec_dirs: Union[List, str], **kwargs):
        if not isinstance(exec_dirs, List):
            exec_dirs = exec_dirs.split(',')
        valid_dirs = []
        for d in exec_dirs:
            if osp.exists(d):
                valid_dirs.append(d)
            else:
                LOGGER.warning(f'target directory {d} does not exist.')
        self.exec_dirs = valid_dirs
        self.run_next_dir()

    def run_next_dir(self):
        if len(self.exec_dirs) == 0:
            while self.imsave_thread.isRunning():
                time.sleep(0.1)
            if shared.HEADLESS_CONTINUOUS:
                LOGGER.info(f'finished translating all dirs, please enter next dirs to translate (separated by comma). enter "exit" to quit app.')
                new_exec_dirs = input()
                if new_exec_dirs.strip().lower() == 'exit':
                    LOGGER.info(f'exiting app...')
                    self.app.quit()
                    return  
                else:
                    self.run_batch(new_exec_dirs)
                    return;
            else:
                LOGGER.info(f'finished translating all dirs, quit app...')
                self.app.quit()
                return
        d = self.exec_dirs.pop(0)
        
        LOGGER.info(f'translating {d} ...')
        self.openDir(d)
        shared.pbar = {}
        npages = len(self.imgtrans_proj.pages)
        if npages > 0:
            if pcfg.module.enable_detect:
                shared.pbar['detect'] = tqdm(range(npages), desc="Text Detection")
            if pcfg.module.enable_ocr:
                shared.pbar['ocr'] = tqdm(range(npages), desc="OCR")
            if pcfg.module.enable_translate:
                shared.pbar['translate'] = tqdm(range(npages), desc="Translation")
            if pcfg.module.enable_inpaint:
                shared.pbar['inpaint'] = tqdm(range(npages), desc="Inpaint")
        self.on_run_imgtrans()

    def on_create_errdialog(self, error_msg: str, detail_traceback: str = '', exception_type: str = ''):
        try:
            if exception_type != '':
                shared.showed_exception.add(exception_type)
            err = QMessageBox()
            err.setText(error_msg)
            err.setDetailedText(detail_traceback)
            err.exec()
            if exception_type != '':
                shared.showed_exception.remove(exception_type)
        except:
            if exception_type in shared.showed_exception:
                shared.showed_exception.remove(exception_type)
            LOGGER.error('Failed to create error dialog')
            LOGGER.error(traceback.format_exc())

    def on_create_infodialog(self, info_dict: dict):
        QMessageBox.StandardButton.NoButton
        dialog = MessageBox(**info_dict)
        dialog.show()   # exec_ will block main thread

    def setupRegisterWidget(self):
        self.titleBar.viewMenu.addSeparator()
        for cfg_name in shared.config_name_to_view_widget:
            d = shared.config_name_to_view_widget[cfg_name]
            widget: ViewWidget = d['widget']
            action = QAction(widget.action_name, self.titleBar)
            action.setCheckable(True)
            visible = getattr(pcfg, cfg_name)
            action.setChecked(visible)
            action.triggered.connect(self.action_set_view_visible)
            self.titleBar.viewMenu.addAction(action)
            d['action'] = action
            shared.action_to_view_config_name[action] = cfg_name
            widget.set_expend_area(expend=getattr(pcfg, widget.config_expand_name), set_config=False)
            widget.view_hide_btn_clicked.connect(self.on_hide_view_widget)
            widget.setVisible(visible)

    def register_view_widget(self, widget: ViewWidget):
        assert widget.config_name not in shared.config_name_to_view_widget
        d = {'widget': widget}
        shared.config_name_to_view_widget[widget.config_name] = d

    def action_set_view_visible(self):
        action: QAction = self.sender()
        show = action.isChecked()
        cfg_name = shared.action_to_view_config_name[action]
        widget: ViewWidget = shared.config_name_to_view_widget[cfg_name]['widget']
        widget.setVisible(show)
        setattr(pcfg, cfg_name, show)

    def on_hide_view_widget(self, cfg_name: str):
        d = shared.config_name_to_view_widget[cfg_name]
        widget: ViewWidget = d['widget']
        widget.setVisible(False)
        action: QAction = d['action']
        action.setChecked(False)
        setattr(pcfg, cfg_name, False)
