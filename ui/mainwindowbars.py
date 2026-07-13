import os.path as osp
from utils.archive_import import archive_filter
from typing import List, Union

from qtpy.QtWidgets import QMainWindow, QHBoxLayout, QVBoxLayout, QFileDialog, QLabel, QSizePolicy, QToolBar, QMenu, QSpacerItem, QPushButton, QCheckBox, QToolButton
from qtpy.QtCore import Qt, Signal, QPoint, QEvent, QSize
from qtpy.QtGui import QMouseEvent, QKeySequence, QActionGroup, QIcon

from modules.translators import BaseTranslator, lang_display_label
from .custom_widget import Widget, PaintQSlider, SmallComboBox, ConfigClickableLabel
from utils.shared import TITLEBAR_HEIGHT, WINDOW_BORDER_WIDTH, BOTTOMBAR_HEIGHT, LEFTBAR_WIDTH, LEFTBTN_WIDTH
from .framelesswindow import FramelessMoveResize
from utils.config import pcfg
from utils import shared as C
if C.FLAG_QT6:
    from qtpy.QtGui import QAction
else:
    from qtpy.QtWidgets import QAction

class ShowPageListChecker(QCheckBox):
    ...


class OpenBtn(QToolButton):
    ...


class StatusButton(QPushButton):
    pass


class TitleBarToolBtn(QToolButton):
    pass


class StateChecker(QCheckBox):
    checked = Signal(str)
    unchecked = Signal(str)
    def __init__(self, checker_type: str, uncheckable: bool = False, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.checker_type = checker_type
        self.uncheckable = uncheckable

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.isChecked():
                self.setChecked(True)
            elif self.uncheckable:
                self.setChecked(False)
                
    def setChecked(self, check: bool) -> None:
        check_state = self.isChecked()
        super().setChecked(check)
        if check_state != check:
            if check:
                self.checked.emit(self.checker_type)
            else:
                self.unchecked.emit(self.checker_type)

class LeftBar(Widget):
    recent_proj_list = []
    imgTransChecked = Signal()
    configChecked = Signal()
    open_dir = Signal(str)
    open_paths = Signal(list)
    open_json_proj = Signal(str)
    save_proj = Signal()
    save_config = Signal()
    glossary_clicked = Signal()
    run_gloss_scan_clicked = Signal()
    run_region_merge_clicked = Signal()
    run_decensor_clicked = Signal()
    run_reinpaint_clicked = Signal()
    run_inpaint_optimize_clicked = Signal()
    run_upscale_2x_clicked = Signal()
    run_translate_clicked = Signal()
    pipeline_history_clicked = Signal()
    export_comic_clicked = Signal()
    batch_processing_clicked = Signal()
    def __init__(self, mainwindow, *args, **kwargs) -> None:
        super().__init__(mainwindow, *args, **kwargs)
        self.mainwindow: QMainWindow = mainwindow

        padding = (LEFTBAR_WIDTH - LEFTBTN_WIDTH) // 2
        self.setFixedWidth(LEFTBAR_WIDTH)
        self.showPageListLabel = ShowPageListChecker()
        self.showPageListLabel.setToolTip(self.tr('Pages: show or hide the project page list (Ctrl+Shift+P).'))

        self.globalSearchChecker = QCheckBox()
        self.globalSearchChecker.setObjectName('GlobalSearchChecker')
        self.globalSearchChecker.setToolTip(self.tr('Search/Replace: find and replace text across the project (Ctrl+G).'))

        self.imgTransChecker = StateChecker('imgtrans')
        self.imgTransChecker.setObjectName('ImgTransChecker')
        self.imgTransChecker.setToolTip(self.tr('Translation workspace: show the canvas, page list, and editing panels.'))
        self.imgTransChecker.checked.connect(self.stateCheckerChanged)
        
        self.configChecker = StateChecker('config', uncheckable=True)
        self.configChecker.setObjectName('ConfigChecker')
        self.configChecker.setToolTip(self.tr('Settings: configure OCR, translation, inpainting, text detection, and app options.'))
        self.configChecker.checked.connect(self.stateCheckerChanged)
        self.configChecker.unchecked.connect(self.stateCheckerChanged)

        actionOpenFolder = QAction(self.tr("Open Folder ..."), self)
        actionOpenFolder.triggered.connect(self.onOpenFolder)
        actionOpenFolder.setShortcut(QKeySequence.Open)

        actionOpenArchive = QAction(self.tr("Open Comic Archive/PDF ... *.cbz *.cbr *.zip *.pdf"), self)
        actionOpenArchive.triggered.connect(self.onOpenArchive)
        actionImportFolder = QAction(self.tr("Import Folder ... archives, PDFs, and images"), self)
        actionImportFolder.triggered.connect(self.onImportFolder)
        actionBatchProcessing = QAction(self.tr("Batch Processing ..."), self)
        actionBatchProcessing.setToolTip(self.tr('Process each image subfolder as a separate project with its own glossary.'))
        self.batch_processing_clicked = actionBatchProcessing.triggered

        actionOpenProj = QAction(self.tr("Open Project ... *.json"), self)
        actionOpenProj.triggered.connect(self.onOpenProj)

        actionSaveProj = QAction(self.tr("Save Project"), self)
        self.save_proj = actionSaveProj.triggered
        actionSaveProj.setShortcut(QKeySequence.StandardKey.Save)

        actionExportAsDoc = QAction(self.tr("Export as Doc"), self)
        self.export_doc = actionExportAsDoc.triggered
        actionExportComic = QAction(self.tr("Export as Comic Archive/PDF ... *.cbz *.cbr *.zip *.pdf"), self)
        self.export_comic_clicked = actionExportComic.triggered
        actionImportFromDoc = QAction(self.tr("Import from Doc"), self)
        self.import_doc = actionImportFromDoc.triggered

        actionExportSrcTxt = QAction(self.tr("Export source text as TXT"), self)
        self.export_src_txt = actionExportSrcTxt.triggered
        actionExportTranslationTxt = QAction(self.tr("Export translation as TXT"), self)
        self.export_trans_txt = actionExportTranslationTxt.triggered

        actionExportSrcMD = QAction(self.tr("Export source text as markdown"), self)
        self.export_src_md = actionExportSrcMD.triggered
        actionExportTranslationMD = QAction(self.tr("Export translation as markdown"), self)
        self.export_trans_md = actionExportTranslationMD.triggered

        actionImportTranslationTxt = QAction(self.tr("Import translation from TXT/markdown"), self)
        self.import_trans_txt = actionImportTranslationTxt.triggered

        self.recentMenu = QMenu(self.tr("Open Recent"), self)
        
        openMenu = QMenu(self)
        openMenu.addActions([actionOpenFolder, actionOpenArchive, actionImportFolder, actionBatchProcessing, actionOpenProj])
        openMenu.addMenu(self.recentMenu)
        openMenu.addSeparator()
        openMenu.addActions([
            actionSaveProj,
            actionExportAsDoc,
            actionExportComic,
            actionImportFromDoc,
            actionExportSrcTxt,
            actionExportTranslationTxt,
            actionExportSrcMD,
            actionExportTranslationMD,
            actionImportTranslationTxt,
        ])
        self.openBtn = OpenBtn()
        self.openBtn.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)
        self.openBtn.setToolTip(self.tr('Menu: open, save, import, and export projects.'))
        self.openBtn.setMenu(openMenu)
        self.openBtn.setPopupMode(QToolButton.InstantPopup)
    
        openBtnToolBar = QToolBar(self)
        openBtnToolBar.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)
        openBtnToolBar.addWidget(self.openBtn)
        
        self.runImgtransBtn = QPushButton()
        self.runImgtransBtn.setObjectName('RunButton')
        self.runImgtransBtn.setText(self.tr('Run'))
        font = self.runImgtransBtn.font()
        font.setPixelSize(10)
        self.runImgtransBtn.setFont(font)
        self.runImgtransBtn.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)
        self.runImgtransBtn.setToolTip(self.tr('Run: process the project with the enabled detection, OCR, translation, and inpainting stages.'))
        self.run_imgtrans_clicked = self.runImgtransBtn.clicked
        self.runImgtransBtn.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)

        self.runTranslateBtn = QPushButton()
        self.runTranslateBtn.setObjectName('RunButton')
        self.runTranslateBtn.setText(self.tr('Trans'))
        self.runTranslateBtn.setToolTip(self.tr('Translate only: run translation on existing text boxes without text detection, OCR, or inpainting.'))
        self.runTranslateBtn.setIcon(QIcon('icons/bottombar_translate.svg'))
        self.runTranslateBtn.setIconSize(QSize(17, 17))
        font = self.runTranslateBtn.font()
        font.setPixelSize(9)
        self.runTranslateBtn.setFont(font)
        self.runTranslateBtn.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)
        self.runTranslateBtn.clicked.connect(self.run_translate_clicked)

        utility_icon_size = QSize(23, 23)

        self.pipelineHistoryBtn = QPushButton()
        self.pipelineHistoryBtn.setObjectName('RunButton')
        self.pipelineHistoryBtn.setText(self.tr('Hist'))
        self.pipelineHistoryBtn.setAccessibleName(self.tr('Pipeline History'))
        self.pipelineHistoryBtn.setToolTip(self.tr('Pipeline History: show completed pipeline and process runs for this project.'))
        font = self.pipelineHistoryBtn.font()
        font.setPixelSize(9)
        self.pipelineHistoryBtn.setFont(font)
        self.pipelineHistoryBtn.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)
        self.pipelineHistoryBtn.clicked.connect(self.pipeline_history_clicked)

        self.glossaryBtn = QPushButton()
        self.glossaryBtn.setObjectName('RunButton')
        self.glossaryBtn.setAccessibleName(self.tr('Glossary'))
        self.glossaryBtn.setToolTip(self.tr('Glossary: open the current project glossary.'))
        self.glossaryBtn.setIcon(QIcon('icons/leftbar_glossary.svg'))
        self.glossaryBtn.setIconSize(utility_icon_size)
        self.glossaryBtn.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)
        self.glossaryBtn.clicked.connect(self.glossary_clicked)

        self.runRegionMergeBtn = QPushButton()
        self.runRegionMergeBtn.setObjectName('RunButton')
        self.runRegionMergeBtn.setAccessibleName(self.tr('Merge nearby text boxes'))
        self.runRegionMergeBtn.setToolTip(self.tr('Merge nearby text boxes on the current page using the configured Post-merge settings.'))
        self.runRegionMergeBtn.setIcon(QIcon('icons/leftbar_merge.svg'))
        self.runRegionMergeBtn.setIconSize(utility_icon_size)
        font = self.runRegionMergeBtn.font()
        font.setPixelSize(8)
        self.runRegionMergeBtn.setFont(font)
        self.runRegionMergeBtn.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)
        self.runRegionMergeBtn.clicked.connect(self.run_region_merge_clicked)

        self.runDecensorBtn = QPushButton()
        self.runDecensorBtn.setObjectName('RunButton')
        self.runDecensorBtn.setAccessibleName(self.tr('Censor Restoration'))
        self.runDecensorBtn.setToolTip(self.tr('Censor Restoration: detect censored regions on the current page and repair them with inpainting.'))
        self.runDecensorBtn.setIcon(QIcon('icons/leftbar_decensor.svg'))
        self.runDecensorBtn.setIconSize(utility_icon_size)
        font = self.runDecensorBtn.font()
        font.setPixelSize(10)
        self.runDecensorBtn.setFont(font)
        self.runDecensorBtn.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)
        self.runDecensorBtn.clicked.connect(self.run_decensor_clicked)

        self.runReInpaintBtn = QPushButton()
        self.runReInpaintBtn.setObjectName('RunButton')
        self.runReInpaintBtn.setAccessibleName(self.tr('Re-run Inpainting'))
        self.runReInpaintBtn.setToolTip(self.tr('Re-run Inpainting: apply all existing inpaint masks again on the current page.'))
        self.runReInpaintBtn.setIcon(QIcon('icons/leftbar_reinpaint.svg'))
        self.runReInpaintBtn.setIconSize(utility_icon_size)
        font = self.runReInpaintBtn.font()
        font.setPixelSize(10)
        self.runReInpaintBtn.setFont(font)
        self.runReInpaintBtn.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)
        self.runReInpaintBtn.clicked.connect(self.run_reinpaint_clicked)

        self.runInpaintOptimizeBtn = QPushButton()
        self.runInpaintOptimizeBtn.setObjectName('RunButton')
        self.runInpaintOptimizeBtn.setAccessibleName(self.tr('Optimize Inpainting'))
        self.runInpaintOptimizeBtn.setToolTip(self.tr('Optimize Inpainting: detect leftover text on the current inpainted page and repair it again.'))
        self.runInpaintOptimizeBtn.setIcon(QIcon('icons/leftbar_optimize.svg'))
        self.runInpaintOptimizeBtn.setIconSize(utility_icon_size)
        font = self.runInpaintOptimizeBtn.font()
        font.setPixelSize(10)
        self.runInpaintOptimizeBtn.setFont(font)
        self.runInpaintOptimizeBtn.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)
        self.runInpaintOptimizeBtn.clicked.connect(self.run_inpaint_optimize_clicked)

        self.runUpscale2xBtn = QPushButton()
        self.runUpscale2xBtn.setObjectName('RunButton')
        self.runUpscale2xBtn.setAccessibleName(self.tr('Upscale 2x'))
        self.runUpscale2xBtn.setToolTip(self.tr('Upscale 2x: replace project pages with 2x images using the configured Upscaling quality and size limits.'))
        self.runUpscale2xBtn.setIcon(QIcon('icons/leftbar_upscale.svg'))
        self.runUpscale2xBtn.setIconSize(utility_icon_size)
        font = self.runUpscale2xBtn.font()
        font.setPixelSize(10)
        self.runUpscale2xBtn.setFont(font)
        self.runUpscale2xBtn.setFixedSize(LEFTBTN_WIDTH, LEFTBTN_WIDTH)
        self.runUpscale2xBtn.clicked.connect(self.run_upscale_2x_clicked)

        vlayout = QVBoxLayout(self)
        vlayout.addWidget(openBtnToolBar)
        vlayout.addWidget(self.showPageListLabel)
        vlayout.addWidget(self.globalSearchChecker)
        vlayout.addWidget(self.glossaryBtn)
        vlayout.addWidget(self.pipelineHistoryBtn)
        vlayout.addWidget(self.runRegionMergeBtn)
        vlayout.addWidget(self.runDecensorBtn)
        vlayout.addWidget(self.runReInpaintBtn)
        vlayout.addWidget(self.runInpaintOptimizeBtn)
        vlayout.addWidget(self.runUpscale2xBtn)
        vlayout.addWidget(self.imgTransChecker)
        vlayout.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))
        vlayout.addWidget(self.configChecker)
        vlayout.addWidget(self.runImgtransBtn)
        vlayout.addWidget(self.runTranslateBtn)
        vlayout.setContentsMargins(padding, LEFTBTN_WIDTH // 2, padding, LEFTBTN_WIDTH // 2)
        vlayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vlayout.setSpacing(LEFTBTN_WIDTH // 2)
        self.setGeometry(0, 0, 300, 500)
        self.setMouseTracking(True)

    def initRecentProjMenu(self, proj_list: List[str]):
        self.recent_proj_list = proj_list
        for proj in proj_list:
            action = QAction(proj, self)
            self.recentMenu.addAction(action)
            action.triggered.connect(self.recentActionTriggered)

    def updateRecentProjList(self, proj_list: Union[str, List[str]]):
        if len(proj_list) == 0:
            return
        if isinstance(proj_list, str):
            proj_list = [proj_list]
        if self.recent_proj_list == proj_list:
            return

        actionlist = self.recentMenu.actions()
        if len(self.recent_proj_list) == 0:
            self.recent_proj_list.append(proj_list.pop())
            topAction = QAction(self.recent_proj_list[-1], self)
            topAction.triggered.connect(self.recentActionTriggered)
            self.recentMenu.addAction(topAction)
        else:
            topAction = actionlist[0]
        for proj in proj_list[::-1]:
            try:    # remove duplicated
                idx = self.recent_proj_list.index(proj)
                if idx == 0:
                    continue
                del self.recent_proj_list[idx]
                self.recentMenu.removeAction(self.recentMenu.actions()[idx])
                if len(self.recent_proj_list) == 0:
                    topAction = QAction(proj, self)
                    self.recentMenu.addAction(topAction)
                    topAction.triggered.connect(self.recentActionTriggered)
                    continue
            except ValueError:
                pass
            newTop = QAction(proj, self)
            self.recentMenu.insertAction(topAction, newTop)
            newTop.triggered.connect(self.recentActionTriggered)
            self.recent_proj_list.insert(0, proj)
            topAction = newTop

        MAXIUM_RECENT_PROJ_NUM = 14
        actionlist = self.recentMenu.actions()
        num_to_remove = len(actionlist) - MAXIUM_RECENT_PROJ_NUM
        if num_to_remove > 0:
            actions_to_remove = actionlist[-num_to_remove:]
            for action in actions_to_remove:
                self.recentMenu.removeAction(action)
                self.recent_proj_list.pop()

        self.save_config.emit()

    def recentActionTriggered(self):
        path = self.sender().text()
        if osp.exists(path):
            self.updateRecentProjList(path)
            self.open_dir.emit(path)
        else:
            self.recent_proj_list.remove(path)
            self.recentMenu.removeAction(self.sender())
        
    def onOpenFolder(self) -> None:
        
        d = None
        if len(self.recent_proj_list) > 0:
            for projp in self.recent_proj_list:
                if not osp.isdir(projp):
                    projp = osp.dirname(projp)
                if osp.exists(projp):
                    d = projp
                    break
        
        dialog = QFileDialog()
        folder_path = str(dialog.getExistingDirectory(self, self.tr("Select Directory"), d))
        if osp.exists(folder_path):
            self.updateRecentProjList(folder_path)
            self.open_dir.emit(folder_path)

    def onOpenProj(self):
        dialog = QFileDialog()
        json_path = str(dialog.getOpenFileUrl(self.parent(), self.tr('Import *.docx'), filter="*.json")[0].toLocalFile())
        if osp.exists(json_path):
            self.open_json_proj.emit(json_path)

    def onOpenArchive(self):
        dialog = QFileDialog()
        urls = dialog.getOpenFileUrls(
            self.parent(),
            self.tr('Open Comic Archive/PDF'),
            filter=archive_filter(),
        )[0]
        paths = [str(url.toLocalFile()) for url in urls if osp.exists(str(url.toLocalFile()))]
        if not paths:
            return
        self.updateRecentProjList(paths)
        if len(paths) == 1:
            self.open_dir.emit(paths[0])
        else:
            self.open_paths.emit(paths)

    def onImportFolder(self):
        d = None
        if len(self.recent_proj_list) > 0:
            for projp in self.recent_proj_list:
                if not osp.isdir(projp):
                    projp = osp.dirname(projp)
                if osp.exists(projp):
                    d = projp
                    break

        dialog = QFileDialog()
        folder_path = str(dialog.getExistingDirectory(self, self.tr("Import Folder"), d))
        if osp.exists(folder_path):
            self.updateRecentProjList(folder_path)
            self.open_paths.emit([folder_path])

    def stateCheckerChanged(self, checker_type: str):
        if checker_type == 'imgtrans':
            self.configChecker.setChecked(False)
            self.imgTransChecked.emit()
        elif checker_type == 'config':
            if self.configChecker.isChecked():
                self.configChecked.emit()
                self.configChecker.blockSignals(True)
                self.configChecker.setChecked(False)
                self.configChecker.blockSignals(False)
            else:
                self.imgTransChecker.setChecked(True)
                

    def needleftStackWidget(self) -> bool:
        return self.showPageListLabel.isChecked() or self.globalSearchChecker.isChecked()


class TitleBar(Widget):

    closebtn_clicked = Signal()
    display_lang_changed = Signal(str)
    enable_module = Signal(int, bool)

    RUN_PRESETS = {
        'full': (True, True, True, True, False),
        'text_detection': (True, False, False, False, False),
        'ocr': (False, True, False, False, False),
        'translation': (False, False, True, False, False),
        'inpainting': (False, False, False, True, False),
    }

    def __init__(self, parent, *args, **kwargs) -> None:
        super().__init__(parent, *args, **kwargs)
        self.mainwindow : QMainWindow = parent
        self.mainwindow.installEventFilter(self)
        self.mPos: QPoint = None
        self.normalsize = False
        self.proj_name = ''
        self.page_name = ''
        self.page_index = None
        self.page_count = 0
        self.save_state = ''
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self.setMouseTracking(True)

        self.editToolBtn = TitleBarToolBtn(self)
        self.editToolBtn.setText(self.tr('Edit'))
        self.editToolBtn.setToolTip(self.tr('Edit menu: undo, redo, search, and keyword substitution.'))

        undoAction = QAction(self.tr('Undo'), self)
        self.undo_trigger = undoAction.triggered
        undoAction.setShortcut(QKeySequence.StandardKey.Undo)
        redoAction = QAction(self.tr('Redo'), self)
        self.redo_trigger = redoAction.triggered
        redoAction.setShortcut(QKeySequence.StandardKey.Redo)
        pageSearchAction = QAction(self.tr('Search'), self)
        self.page_search_trigger = pageSearchAction.triggered
        pageSearchAction.setShortcut(QKeySequence('Ctrl+F'))
        globalSearchAction = QAction(self.tr('Global Search'), self)
        self.global_search_trigger = globalSearchAction.triggered
        globalSearchAction.setShortcut(QKeySequence('Ctrl+G'))

        replacePreMTkeyword = QAction(self.tr("Keyword substitution for machine translation source text"), self)
        self.replacePreMTkeyword_trigger = replacePreMTkeyword.triggered
        replaceMTkeyword = QAction(self.tr("Keyword substitution for machine translation"), self)
        self.replaceMTkeyword_trigger = replaceMTkeyword.triggered
        replaceOCRkeyword = QAction(self.tr("Keyword substitution for source text"), self)
        self.replaceOCRkeyword_trigger = replaceOCRkeyword.triggered

        editMenu = QMenu(self.editToolBtn)
        editMenu.addActions([undoAction, redoAction])
        editMenu.addSeparator()
        editMenu.addActions([pageSearchAction, globalSearchAction, replaceOCRkeyword, replacePreMTkeyword, replaceMTkeyword])
        self.editToolBtn.setMenu(editMenu)
        self.editToolBtn.setPopupMode(QToolButton.InstantPopup)

        self.viewToolBtn = TitleBarToolBtn(self)
        self.viewToolBtn.setText(self.tr('View'))
        self.viewToolBtn.setToolTip(self.tr('View menu: display language, panels, text styles, and theme.'))

        self.displayLanguageMenu = QMenu(self.tr("Display Language"), self)
        self.lang_ac_group = lang_ac_group = QActionGroup(self)
        lang_ac_group.setExclusive(True)
        lang_actions = []
        for lang, lang_code in C.DISPLAY_LANGUAGE_MAP.items():
            la = QAction(lang, self)
            if lang_code == pcfg.display_lang:
                la.setChecked(True)
            la.triggered.connect(self.on_displaylang_triggered)
            la.setCheckable(True)
            lang_ac_group.addAction(la)
            lang_actions.append(la)
        self.displayLanguageMenu.addActions(lang_actions)

        drawBoardAction = QAction(self.tr('Drawing Board'), self)
        drawBoardAction.setShortcut(QKeySequence('P'))
        texteditAction = QAction(self.tr('Text Editor'), self)
        texteditAction.setShortcut(QKeySequence('T'))
        importTextStyles = QAction(self.tr('Import Text Styles'), self)
        exportTextStyles = QAction(self.tr('Export Text Styles'), self)
        self.darkModeAction = darkModeAction = QAction(self.tr('Dark Mode'), self)
        darkModeAction.setCheckable(True)

        self.viewMenu = viewMenu = QMenu(self.viewToolBtn)
        viewMenu.addMenu(self.displayLanguageMenu)
        viewMenu.addActions([drawBoardAction, texteditAction])
        viewMenu.addSeparator()
        viewMenu.addAction(importTextStyles)
        viewMenu.addAction(exportTextStyles)
        viewMenu.addSeparator()
        viewMenu.addAction(darkModeAction)
        self.viewToolBtn.setMenu(viewMenu)
        self.viewToolBtn.setPopupMode(QToolButton.InstantPopup)
        self.textedit_trigger = texteditAction.triggered
        self.drawboard_trigger = drawBoardAction.triggered
        self.importtstyle_trigger = importTextStyles.triggered
        self.exporttstyle_trigger = exportTextStyles.triggered
        self.darkmode_trigger = darkModeAction.triggered

        self.goToolBtn = TitleBarToolBtn(self)
        self.goToolBtn.setText(self.tr('Go'))
        self.goToolBtn.setToolTip(self.tr('Go menu: move between project pages.'))
        prevPageAction = QAction(self.tr('Previous Page'), self)
        # prevPageAction.setShortcuts([QKeySequence.StandardKey.MoveToPreviousPage, QKeySequence('A')])
        nextPageAction = QAction(self.tr('Next Page'), self)
        # nextPageAction.setShortcuts([QKeySequence.StandardKey.MoveToNextPage, QKeySequence('D')])
        goMenu = QMenu(self.goToolBtn)
        goMenu.addActions([prevPageAction, nextPageAction])
        self.goToolBtn.setMenu(goMenu)
        self.goToolBtn.setPopupMode(QToolButton.InstantPopup)
        self.prevpage_trigger = prevPageAction.triggered
        self.nextpage_trigger = nextPageAction.triggered

        self.toolsToolBtn = TitleBarToolBtn(self)
        self.toolsToolBtn.setText(self.tr('Tools'))
        self.toolsToolBtn.setToolTip(self.tr('Tools menu: utilities for project editing.'))
        
        mergeToolAction = QAction(self.tr('Region Merge Tool'), self)
        mergeToolAction.setShortcut(QKeySequence('Ctrl+Shift+M'))
        self.merge_tool_trigger = mergeToolAction.triggered

        reinpaintAction = QAction(self.tr('Re-run Inpainting Current Page'), self)
        reinpaintAction.setShortcut(QKeySequence('Ctrl+Shift+I'))
        reinpaintAction.setToolTip(self.tr('Re-run Inpainting: apply all existing inpaint masks again on the current page.'))
        self.reinpaint_current_page_trigger = reinpaintAction.triggered

        optimizeInpaintCurrentAction = QAction(self.tr('Optimize Inpainting Current Page'), self)
        optimizeInpaintCurrentAction.setShortcut(QKeySequence('Ctrl+Alt+I'))
        optimizeInpaintCurrentAction.setToolTip(self.tr('Detect leftover text on the current inpainted page and repair it with a second inpainting pass.'))
        self.optimize_inpaint_current_page_trigger = optimizeInpaintCurrentAction.triggered

        optimizeInpaintAllAction = QAction(self.tr('Optimize Inpainting All Pages'), self)
        optimizeInpaintAllAction.setToolTip(self.tr('Detect leftover text on all non-ignored inpainted pages and repair it with a second inpainting pass.'))
        self.optimize_inpaint_all_pages_trigger = optimizeInpaintAllAction.triggered

        upscaleProject2xAction = QAction(self.tr('Upscale Project Images 2x'), self)
        upscaleProject2xAction.setToolTip(self.tr('Replace all project pages with 2x upscaled files, using the Upscaling quality and size-limit settings.'))
        self.upscale_project_2x_trigger = upscaleProject2xAction.triggered

        upscaleProjectSettingsAction = QAction(self.tr('Upscale Project Images Using Settings'), self)
        upscaleProjectSettingsAction.setToolTip(self.tr('Replace all project pages using the configured Upscaling factor, quality, and size limits.'))
        self.upscale_project_settings_trigger = upscaleProjectSettingsAction.triggered

        batchUpscaleFoldersAction = QAction(self.tr('Batch Upscale Folders Using Settings...'), self)
        batchUpscaleFoldersAction.setToolTip(self.tr('Choose a parent folder and replace pages in each source-image subfolder using the configured Upscaling settings.'))
        self.batch_upscale_folders_trigger = batchUpscaleFoldersAction.triggered

        removeMasksAction = QAction(self.tr('Remove All Masks Current Page'), self)
        removeMasksAction.setShortcut(QKeySequence('Ctrl+Shift+Backspace'))
        removeMasksAction.setToolTip(self.tr('Remove every mask on the current page and restore the inpainted pixels from the original image.'))
        self.remove_current_page_masks_trigger = removeMasksAction.triggered

        modelDownloadsAction = QAction(self.tr('Model Downloads'), self)
        modelDownloadsAction.setToolTip(self.tr('Download optional or missing local OCR, detection, inpainting, and translator model files.'))
        self.model_downloads_trigger = modelDownloadsAction.triggered
        
        toolsMenu = QMenu(self.toolsToolBtn)
        toolsMenu.addAction(mergeToolAction)
        toolsMenu.addAction(reinpaintAction)
        toolsMenu.addAction(optimizeInpaintCurrentAction)
        toolsMenu.addAction(optimizeInpaintAllAction)
        toolsMenu.addAction(upscaleProject2xAction)
        toolsMenu.addAction(upscaleProjectSettingsAction)
        toolsMenu.addAction(batchUpscaleFoldersAction)
        toolsMenu.addAction(removeMasksAction)
        toolsMenu.addSeparator()
        toolsMenu.addAction(modelDownloadsAction)
        self.toolsToolBtn.setMenu(toolsMenu)
        self.toolsToolBtn.setPopupMode(QToolButton.InstantPopup)

        self.runToolBtn = TitleBarToolBtn(self)
        self.runToolBtn.setText(self.tr('Run'))
        self.runToolBtn.setToolTip(self.tr('Run menu: choose enabled stages, presets, and translation commands.'))

        self.stageActions = stageActions = [
            QAction(self.tr('Enable Text Detection'), self),
            QAction(self.tr('Enable OCR'), self),
            QAction(self.tr('Enable Translation'), self),
            QAction(self.tr('Enable Inpainting'), self),
            QAction(self.tr('Enable Inpaint Optimization'), self)
        ]
        for idx, sa in enumerate(stageActions):
            sa.setCheckable(True)
            sa.setChecked(pcfg.module.stage_enabled(idx))
            sa.triggered.connect(self.stageEnableStateChanged)

        presetFullRunAction = QAction(self.tr('Preset: Full Run'), self)
        presetTextDetectionAction = QAction(self.tr('Preset: Text Detection'), self)
        presetOcrAction = QAction(self.tr('Preset: OCR'), self)
        presetTranslationAction = QAction(self.tr('Preset: Translation'), self)
        presetInpaintingAction = QAction(self.tr('Preset: Inpainting'), self)
        self.runPresetActions = {
            presetFullRunAction: 'full',
            presetTextDetectionAction: 'text_detection',
            presetOcrAction: 'ocr',
            presetTranslationAction: 'translation',
            presetInpaintingAction: 'inpainting',
        }
        presetFullRunAction.setToolTip(self.tr('Enable text detection, OCR, translation, and inpainting.'))
        presetTextDetectionAction.setToolTip(self.tr('Enable only text detection. OCR, translation, and inpainting are disabled.'))
        presetOcrAction.setToolTip(self.tr('Enable only OCR for existing text regions.'))
        presetTranslationAction.setToolTip(self.tr('Enable only translation for existing source text.'))
        presetInpaintingAction.setToolTip(self.tr('Enable only inpainting for existing regions.'))
        stageActions[4].setToolTip(self.tr('After normal inpainting, detect leftover text on the inpainted page and run a second repair pass.'))
        for action in self.runPresetActions:
            action.triggered.connect(self.runPresetTriggered)

        runAction = QAction(self.tr('Run'), self)
        runWoUpdateTextStyle = QAction(self.tr('Run without updating text style'), self)
        translatePageAction = QAction(self.tr('Translate Page'), self)
        glossScanAction = QAction(self.tr('Gloss Scan Current Manga'), self)
        reviewCurrentPageAction = QAction(self.tr('Review Current Page'), self)
        reviewAllPagesAction = QAction(self.tr('Review All Pages'), self)
        translationBenchmarkAction = QAction(self.tr('Translation Benchmark'), self)
        glossScanAction.setToolTip(self.tr('Detect text and run OCR on the current manga, then build a reusable glossary without translation or inpainting.'))
        reviewCurrentPageAction.setToolTip(self.tr('Review and correct existing translations on the current page with the active LLM translator settings.'))
        reviewAllPagesAction.setToolTip(self.tr('Review and correct existing translations on all non-ignored pages with the active LLM translator settings.'))
        translationBenchmarkAction.setToolTip(self.tr('Compare the current page translation with multiple translators or LLM configurations in a side-by-side table.'))
        runMenu = QMenu(self.runToolBtn)
        runMenu.addActions(stageActions)
        runMenu.addSeparator()
        runMenu.addActions(list(self.runPresetActions.keys()))
        runMenu.addSeparator()
        runMenu.addActions([runAction, runWoUpdateTextStyle, translatePageAction])
        runMenu.addSeparator()
        runMenu.addAction(glossScanAction)
        runMenu.addSeparator()
        runMenu.addActions([reviewCurrentPageAction, reviewAllPagesAction, translationBenchmarkAction])
        self.runToolBtn.setMenu(runMenu)
        self.runToolBtn.setPopupMode(QToolButton.InstantPopup)
        self.run_trigger = runAction.triggered
        self.run_woupdate_textstyle_trigger = runWoUpdateTextStyle.triggered
        self.translate_page_trigger = translatePageAction.triggered
        self.gloss_scan_trigger = glossScanAction.triggered
        self.review_current_page_trigger = reviewCurrentPageAction.triggered
        self.review_all_pages_trigger = reviewAllPagesAction.triggered
        self.translation_benchmark_trigger = translationBenchmarkAction.triggered

        self.iconLabel = QLabel(self)
        if not C.ON_MACOS:
            self.iconLabel.setFixedWidth(LEFTBAR_WIDTH - 12)
        else:
            self.iconLabel.setFixedWidth(LEFTBAR_WIDTH + 8)

        self.titleLabel = QLabel('BallonTranslator')
        self.titleLabel.setObjectName('TitleLabel')
        self.titleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        hlayout = QHBoxLayout(self)
        hlayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hlayout.addWidget(self.iconLabel)
        hlayout.addWidget(self.editToolBtn)
        hlayout.addWidget(self.viewToolBtn)
        hlayout.addWidget(self.goToolBtn)
        hlayout.addWidget(self.runToolBtn)
        hlayout.addWidget(self.toolsToolBtn)
        hlayout.addStretch()
        hlayout.addWidget(self.titleLabel)
        hlayout.addStretch()
        hlayout.setContentsMargins(0, 0, 0, 0)

        if not C.ON_MACOS:
            self.minBtn = QPushButton()
            self.minBtn.setObjectName('minBtn')
            self.minBtn.setToolTip(self.tr('Minimize window'))
            self.minBtn.clicked.connect(self.onMinBtnClicked)
            self.maxBtn = QCheckBox()
            self.maxBtn.setObjectName('maxBtn')
            self.maxBtn.setToolTip(self.tr('Maximize or restore window'))
            self.maxBtn.clicked.connect(self.onMaxBtnClicked)
            self.maxBtn.setFixedSize(48, 27)
            self.closeBtn = QPushButton()
            self.closeBtn.setObjectName('closeBtn')
            self.closeBtn.setToolTip(self.tr('Close window'))
            self.closeBtn.clicked.connect(self.closebtn_clicked)
            hlayout.addWidget(self.minBtn)
            hlayout.addWidget(self.maxBtn)
            hlayout.addWidget(self.closeBtn)
            hlayout.setContentsMargins(0, 0, 0, 0)
            hlayout.setSpacing(0)

    def eventFilter(self, obj, e):
        if obj == self.mainwindow:
            if e.type() == QEvent.Type.WindowStateChange and not C.ON_MACOS:
                self.maxBtn.setChecked(self.mainwindow.isMaximized())
                return False

        return super().eventFilter(obj, e)

    def stageEnableStateChanged(self):
        sender = self.sender()
        idx= self.stageActions.index(sender)
        checked = sender.isChecked()
        self.enable_module.emit(idx, checked)

    def setRunPreset(self, preset_key: str):
        states = self.RUN_PRESETS[preset_key]
        for idx, checked in enumerate(states):
            action = self.stageActions[idx]
            action.blockSignals(True)
            action.setChecked(checked)
            action.blockSignals(False)
            self.enable_module.emit(idx, checked)

    def runPresetTriggered(self):
        preset_key = self.runPresetActions[self.sender()]
        self.setRunPreset(preset_key)

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        super().mouseDoubleClickEvent(e)
        FramelessMoveResize.toggleMaxState(self.mainwindow)

    def onMaxBtnClicked(self):
        FramelessMoveResize.toggleMaxState(self.mainwindow)

    def onMinBtnClicked(self):
        self.mainwindow.showMinimized()

    def on_displaylang_triggered(self):
        ac = self.lang_ac_group.checkedAction()
        self.display_lang_changed.emit(C.DISPLAY_LANGUAGE_MAP[ac.text()])

    def mousePressEvent(self, event: QMouseEvent) -> None:

        if C.FLAG_QT6:
            g_pos = event.globalPosition().toPoint()
        else:
            g_pos = event.globalPos()
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.mainwindow.isMaximized() and \
                event.pos().y() < WINDOW_BORDER_WIDTH:
                pass
            else:
                self.mPos = event.pos()
                self.mPosGlobal = g_pos
        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.mPos = None
        return super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.mPos is not None:
            if C.FLAG_QT6:
                g_pos = event.globalPosition().toPoint()
            else:
                g_pos = event.globalPos()
            FramelessMoveResize.startSystemMove(self.window(), g_pos)

    def hideEvent(self, e) -> None:
        self.mPos = None
        return super().hideEvent(e)

    def leaveEvent(self, e) -> None:
        self.mPos = None
        return super().leaveEvent(e)

    def setTitleContent(
        self,
        proj_name: str = None,
        page_name: str = None,
        save_state: str = None,
        page_index: int = None,
        page_count: int = None,
    ):
        max_proj_len = 50
        max_page_len = 50
        if proj_name is not None:
            if len(proj_name) > max_proj_len:
                proj_name = proj_name[:max_proj_len-3] + '...'
            self.proj_name = proj_name
        if page_name is not None:
            if len(page_name) > max_page_len:
                page_name = page_name[:max_page_len-3] + '...'
            self.page_name = page_name
        if page_index is not None:
            self.page_index = page_index
        if page_count is not None:
            self.page_count = page_count
        if save_state is not None:
            self.save_state = save_state
        title = self.proj_name + ' - ' + self.page_name
        if self.page_name and self.page_index is not None and self.page_count > 0:
            digits = max(3, len(str(self.page_count)))
            page_counter = self.tr('{current}/{total} pages').format(
                current=str(self.page_index).zfill(digits),
                total=str(self.page_count).zfill(digits),
            )
            title += '  ' + page_counter
        if self.save_state != '':
            title += ' - '  + self.save_state
        self.titleLabel.setText(title)


class SmallConfigPutton(QPushButton):
    pass


CFG_ICON  = QIcon('icons/leftbar_config_activate.svg')


class SelectionWithConfigWidget(Widget):

    cfg_clicked = Signal()

    def __init__(self, selector_name: str, add_cfg_btn=True, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        label = ConfigClickableLabel(text=selector_name)
        label.setToolTip(self.tr('Open settings for ') + selector_name)
        label.clicked.connect(self.cfg_clicked)
        
        self.selector = SmallComboBox()
        self.selector.setToolTip(self.tr('Select ') + selector_name)

        self.cfg_btn = None
        if add_cfg_btn:
            self.cfg_btn = SmallConfigPutton()
            self.cfg_btn.setToolTip(self.tr('Configure ') + selector_name)
            self.cfg_btn.clicked.connect(self.cfg_clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        layout2 = QHBoxLayout()
        layout2.setSpacing(0)
        layout2.addWidget(self.selector)
        layout2.addWidget(self.cfg_btn)
        layout2.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        layout.addLayout(layout2)

    def enterEvent(self, event: QEvent) -> None:
        if self.cfg_btn is not None:
            self.cfg_btn.setIcon(CFG_ICON)
        return super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        if self.cfg_btn is not None:
            self.cfg_btn.setIcon(QIcon())
        return super().leaveEvent(event)
    
    def blockSignals(self, block: bool):
        self.selector.blockSignals(block)
        super().blockSignals(block)
    
    def setSelectedValue(self, value: str, block_signals=True):
        if block_signals:
            self.blockSignals(True)
        self.selector.setCurrentText(value)
        if block_signals:
            self.blockSignals(False)
    

class TranslatorSelectionWidget(Widget):

    cfg_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        label = ConfigClickableLabel(text=self.tr('Translate'))
        label.setToolTip(self.tr('Open translator settings.'))
        label.clicked.connect(self.cfg_clicked)
        label_src = ConfigClickableLabel(text=self.tr('Source'))
        label_src.setToolTip(self.tr('Open source language settings.'))
        label_src.clicked.connect(self.cfg_clicked)
        label_tgt = ConfigClickableLabel(text=self.tr('Target'))
        label_tgt.setToolTip(self.tr('Open target language settings.'))
        label_tgt.clicked.connect(self.cfg_clicked)
        
        self.selector = SmallComboBox()
        self.selector.setToolTip(self.tr('Select translator module.'))
        self.src_selector = SmallComboBox()
        self.src_selector.setToolTip(self.tr('Source language.'))
        self.tgt_selector = SmallComboBox()
        self.tgt_selector.setToolTip(self.tr('Target language.'))
        self.cfg_btn = SmallConfigPutton()
        self.cfg_btn.setToolTip(self.tr('Configure translator module.'))
        self.cfg_btn.clicked.connect(self.cfg_clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        layout.addWidget(self.selector)
        layout.addWidget(label_src)
        layout.addWidget(self.src_selector)
        layout.addWidget(label_tgt)
        layout.addWidget(self.tgt_selector)
        layout.addWidget(self.cfg_btn)
        layout.setSpacing(1)

    def enterEvent(self, event: QEvent) -> None:
        if self.cfg_btn is not None:
            self.cfg_btn.setIcon(CFG_ICON)
        return super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        if self.cfg_btn is not None:
            self.cfg_btn.setIcon(QIcon())
        return super().leaveEvent(event)
    
    def blockSignals(self, block: bool):
        self.src_selector.blockSignals(block)
        self.tgt_selector.blockSignals(block)
        self.selector.blockSignals(block)
        super().blockSignals(block)
    
    def finishSetTranslator(self, translator: BaseTranslator):
        self.blockSignals(True)
        self.src_selector.clear()
        self.tgt_selector.clear()
        for lang in translator.supported_src_list:
            label = lang_display_label(lang)
            self.src_selector.addItem(label, lang)
            self.src_selector.setItemData(self.src_selector.count() - 1, label, Qt.ItemDataRole.ToolTipRole)
        for lang in translator.supported_tgt_list:
            label = lang_display_label(lang)
            self.tgt_selector.addItem(label, lang)
            self.tgt_selector.setItemData(self.tgt_selector.count() - 1, label, Qt.ItemDataRole.ToolTipRole)
        self.selector.setCurrentText(translator.name)
        self.src_selector.setCurrentText(lang_display_label(translator.lang_source))
        self.tgt_selector.setCurrentText(lang_display_label(translator.lang_target))
        self.blockSignals(False)



class BottomBar(Widget):
    
    textedit_checkchanged = Signal()
    paintmode_checkchanged = Signal()
    textblock_checkchanged = Signal()

    def __init__(self, mainwindow: QMainWindow, *args, **kwargs) -> None:
        super().__init__(mainwindow, *args, **kwargs)
        self.setFixedHeight(BOTTOMBAR_HEIGHT)
        self.setMouseTracking(True)
        self.mainwindow = mainwindow
        
        self.textdet_selector = SelectionWithConfigWidget(self.tr('Text Detector'))
        self.ocr_selector = SelectionWithConfigWidget(self.tr('OCR'))
        self.inpaint_selector = SelectionWithConfigWidget(self.tr('Inpaint'))
        self.trans_selector = TranslatorSelectionWidget()

        self.hlayout = QHBoxLayout(self)
        self.paintChecker = QCheckBox()
        self.paintChecker.setObjectName('PaintChecker')
        self.paintChecker.setToolTip(self.tr('Enable/disable paint mode'))
        self.paintChecker.clicked.connect(self.onPaintCheckerPressed)
        self.texteditChecker = QCheckBox()
        self.texteditChecker.setObjectName('TexteditChecker')
        self.texteditChecker.setToolTip(self.tr('Enable/disable text edit mode'))
        self.texteditChecker.clicked.connect(self.onTextEditCheckerPressed)
        self.textblockChecker = QCheckBox()
        self.textblockChecker.setObjectName('TextblockChecker')
        self.textblockChecker.setToolTip(self.tr('Show and edit text block bounding boxes.'))
        self.textblockChecker.clicked.connect(self.onTextblockCheckerClicked)
        
        self.originalSlider = PaintQSlider(self.tr("Original image opacity"), Qt.Orientation.Horizontal, self)
        self.originalSlider.setFixedWidth(150)
        self.originalSlider.setRange(0, 100)

        self.textlayerSlider = PaintQSlider(self.tr("Text layer opacity"), Qt.Orientation.Horizontal, self)
        self.textlayerSlider.setFixedWidth(150)
        self.textlayerSlider.setValue(100)
        self.textlayerSlider.setRange(0, 100)
        
        self.hlayout.addWidget(self.textdet_selector)
        self.hlayout.addWidget(self.ocr_selector)
        self.hlayout.addWidget(self.inpaint_selector)
        self.hlayout.addWidget(self.trans_selector)
        # self.hlayout.addWidget(self.translatorStatusbtn)
        # self.hlayout.addWidget(self.transTranspageBtn)
        # self.hlayout.addWidget(self.inpainterStatBtn)
        self.hlayout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.hlayout.addWidget(self.textlayerSlider)
        self.hlayout.addWidget(self.originalSlider)
        self.hlayout.addWidget(self.paintChecker)
        self.hlayout.addWidget(self.texteditChecker)
        self.hlayout.addWidget(self.textblockChecker)
        self.hlayout.setContentsMargins(60, 0, 10, WINDOW_BORDER_WIDTH)


    def onPaintCheckerPressed(self):
        checked = self.paintChecker.isChecked()
        if checked:
            self.texteditChecker.setChecked(False)
        pcfg.imgtrans_paintmode = checked
        self.paintmode_checkchanged.emit()

    def onTextEditCheckerPressed(self):
        checked = self.texteditChecker.isChecked()
        if checked:
            self.paintChecker.setChecked(False)
        pcfg.imgtrans_textedit = checked
        self.textedit_checkchanged.emit()

    def onTextblockCheckerClicked(self):
        self.textblock_checkchanged.emit()
