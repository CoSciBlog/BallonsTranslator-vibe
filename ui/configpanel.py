from typing import List, Union, Tuple

from qtpy.QtWidgets import QApplication, QPushButton, QKeySequenceEdit, QLayout, QGridLayout, QHBoxLayout, QVBoxLayout, QTreeView, QWidget, QLabel, QSizePolicy, QSpacerItem, QCheckBox, QSplitter, QScrollArea, QLineEdit, QFileDialog, QInputDialog, QMessageBox, QDialog, QStackedWidget
from qtpy.QtCore import Qt, Signal, QSize, QEvent, QItemSelection
from qtpy.QtGui import QStandardItem, QStandardItemModel, QMouseEvent, QFont, QIntValidator, QDoubleValidator, QValidator, QFocusEvent

from .custom_widget import ConfigComboBox, Widget
from utils.config import (
    pcfg,
    save_config,
    export_program_config,
    import_program_config,
    list_config_presets,
    save_config_preset,
    load_config_preset,
    import_config_preset,
    export_config_preset,
    CONFIG_PRESET_DIR,
)
from utils import shared as C
from utils.shared import CONFIG_FONTSIZE_CONTENT, CONFIG_FONTSIZE_HEADER, CONFIG_FONTSIZE_TABLE, CONFIG_COMBOBOX_SHORT, CONFIG_COMBOBOX_LONG, CONFIG_COMBOBOX_MIDEAN, CONFIG_COMBOBOX_HEIGHT
from .module_parse_widgets import InpaintConfigPanel, TextDetectConfigPanel, TranslatorConfigPanel, OCRConfigPanel
from .tooltip_utils import wrap_tooltip

PRESERVE_ACTIVE_WIDGET_CLASS_NAMES = {
    'FrameLessMessageBox',
    'ImgtransProgressMessageBox',
    'KeywordSubWidget',
    'MessageBox',
    'PipelineHistoryWindow',
    'ProgressMessageBox',
    'TranslationBenchmarkWindow',
}

class CustomIntValidator(QIntValidator):

    def __init__(self, bottom: int, top: int, ndigits: int = None, parent = None):
        super().__init__(bottom=bottom, top=top, parent=parent)
        self.ndigits = ndigits

    def validate(self, s: str, pos: int) -> object:
        if not s.isnumeric():
            if s != '':
                return (QValidator.State.Invalid, s, pos)
            else:
                return (QValidator.State.Intermediate, s, pos)
            
        s_ori = s
        d = int(s)
        s = str(d)
        if len(s) != len(s_ori):
            pos -= len(s_ori) - len(s)
        if len(s) > self.ndigits:
            ndel = len(s) - self.ndigits
            s = s[ndel:]
            pos -= ndel
        else:
            if d > self.top():
                if s[-1] == '0':
                    d = self.top()
                else:
                    d = d % self.top()
            d = max(d, self.bottom())
            s = str(d)
        return (QValidator.State.Acceptable, s, pos)


class PercentageLineEdit(QLineEdit):

    finish_edited = Signal(str)

    def __init__(self, default_value: str = '100', parent=None) -> None:
        super().__init__(default_value, parent=parent)
        validator = CustomIntValidator(0, 101, 3)
        self.setValidator(validator)
        self.textEdited.connect(self.on_text_edited)
        self._edited = False

    def on_text_edited(self):
        self._edited = True

    def focusOutEvent(self, e: QFocusEvent) -> None:
        if self._edited:
            text = self.text()
            if not text.isnumeric():
                text = '100'
                self.setText(text)
            self.finish_edited.emit(text)

        return super().focusOutEvent(e)


class ConfigTextLabel(QLabel):
    def __init__(self, text: str, fontsize: int, font_weight: int = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setText(text)
        font = self.font()
        if font_weight is not None:
            font.setWeight(font_weight)
        font.setPointSizeF(fontsize)
        self.setFont(font)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.setOpenExternalLinks(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def setActiveBackground(self):
        self.setStyleSheet("background-color:rgba(30, 147, 229, 51);")


class ConfigSubBlock(Widget):
    pressed = Signal(int, int)
    def __init__(self, widget: Union[QWidget, QLayout], name: str = None, discription: str = None, vertical_layout=True, insert_stretch: bool = False, content_margins = (24, 6, 24, 6), show_description: bool = True) -> None:
        super().__init__()
        self.idx0: int = None
        self.idx1: int = None
        if vertical_layout:
            layout = QVBoxLayout(self)
        else:
            layout = QHBoxLayout(self)
        self.name = name
        tooltip = wrap_tooltip(discription)
        if name is not None:
            textlabel = ConfigTextLabel(name, CONFIG_FONTSIZE_CONTENT, QFont.Weight.Normal)
            if tooltip is not None:
                textlabel.setToolTip(tooltip)
            self.name_label = textlabel
            layout.addWidget(textlabel)
        if discription is not None and show_description:
            description_label = ConfigTextLabel(discription, CONFIG_FONTSIZE_CONTENT-2)
            description_label.setWordWrap(True)
            description_label.setToolTip(tooltip)
            layout.addWidget(description_label)
        if insert_stretch:
            layout.insertStretch(-1)
        if isinstance(widget, QWidget):
            if tooltip is not None and not widget.toolTip():
                widget.setToolTip(tooltip)
            layout.addWidget(widget)
        else:
            layout.addLayout(widget)
        self.widget = widget
        self.setContentsMargins(*content_margins)

    def setIdx(self, idx0: int, idx1: int) -> None:
        self.idx0 = idx0
        self.idx1 = idx1

    def enterEvent(self, e: QEvent) -> None:
        self.pressed.emit(self.idx0, self.idx1)
        return super().enterEvent(e)
    

def combobox_with_label(sel: List[str], name: str, discription: str = None, vertical_layout: bool = False, target_block: QWidget = None, fix_size: bool = True, parent: QWidget = None, insert_stretch: bool = False, show_description: bool = True) -> Tuple[ConfigComboBox, QWidget]:
    combox = ConfigComboBox(fix_size=fix_size, scrollWidget=parent)
    combox.addItems(sel)
    if target_block is None:
        sublock = ConfigSubBlock(combox, name, discription, vertical_layout=vertical_layout, insert_stretch=insert_stretch, show_description=show_description)
        sublock.layout().setAlignment(Qt.AlignmentFlag.AlignLeft)
        sublock.layout().setSpacing(20)
        return combox, sublock
    else:
        layout = target_block.layout()
        layout.addSpacing(20)
        label = ConfigTextLabel(name, CONFIG_FONTSIZE_CONTENT, QFont.Weight.Normal)
        tooltip = wrap_tooltip(discription)
        if tooltip:
            label.setToolTip(tooltip)
            combox.setToolTip(tooltip)
        layout.addWidget(label)
        layout.addWidget(combox)
        return combox, target_block
    
def checkbox_with_label(name: str, discription: str = None, target_block: QWidget = None):
    checkbox = QCheckBox()
    if discription is not None:
        tooltip = wrap_tooltip(discription)
        checkbox.setToolTip(tooltip)
        checkbox.setAccessibleName(name)
        checkbox.setAccessibleDescription(discription)
        description_label = ConfigTextLabel(discription, CONFIG_FONTSIZE_CONTENT - 2)
        description_label.setWordWrap(True)
        description_label.setToolTip(tooltip)
        description_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        row_layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignTop)
        row_layout.addWidget(description_label, 1)
        widget = row
        vertical_layout = True
    else:
        widget = checkbox
        vertical_layout = False

    if target_block is None:
        sublock = ConfigSubBlock(widget, name, vertical_layout=vertical_layout)
        if vertical_layout is False:
            sublock.layout().addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
        target_block = sublock
    return checkbox, target_block
    


class ConfigBlock(Widget):
    sublock_pressed = Signal(int, int)

    def __init__(self, header: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.header = ConfigTextLabel(header, CONFIG_FONTSIZE_HEADER)
        self.vlayout = QVBoxLayout(self)
        self.vlayout.addWidget(self.header)
        self.setContentsMargins(24, 24, 24, 24)
        self.label_list = []
        self.subblock_list = []
        self.index: int = 0

    def setIndex(self, index: int):
        self.index = index

    def addLineEdit(self, name: str = None, discription: str = None, vertical_layout: bool = False):
        le = QLineEdit()
        le.setFixedWidth(CONFIG_COMBOBOX_MIDEAN)
        le.setFixedHeight(45)
        sublock = ConfigSubBlock(le, name, discription, vertical_layout)
        if vertical_layout is False:
            sublock.layout().addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
        self.addSublock(sublock)
        sublock.layout().setSpacing(20)
        return le, sublock

    def addTextLabel(self, text: str = None):
        label = ConfigTextLabel(text, CONFIG_FONTSIZE_HEADER)
        self.vlayout.addWidget(label)
        self.label_list.append(label)

    def addSublock(self, sublock: ConfigSubBlock):
        self.vlayout.addWidget(sublock)
        sublock.setIdx(self.index, len(self.label_list)-1)
        sublock.pressed.connect(lambda idx0, idx1: self.sublock_pressed.emit(idx0, idx1))
        self.subblock_list.append(sublock)

    def addCombobox(self, sel: List[str], name: str, discription: str = None, vertical_layout: bool = False, target_block: QWidget = None, fix_size: bool = True, show_description: bool = True) -> Tuple[ConfigComboBox, QWidget]:
        combox, sublock = combobox_with_label(sel, name, discription, vertical_layout, target_block, fix_size, parent=self, show_description=show_description)
        if target_block is None:
            self.addSublock(sublock)
        return combox, sublock

    def addBlockWidget(self, widget: Union[QWidget, QLayout], name: str = None, discription: str = None, vertical_layout: bool = False) -> ConfigSubBlock:
        sublock = ConfigSubBlock(widget, name, discription, vertical_layout)
        self.addSublock(sublock)
        return sublock

    def addCheckBox(self, name: str, discription: str = None, target_block: ConfigSubBlock = None) -> QCheckBox:
        checkbox, sublock = checkbox_with_label(name, discription, target_block)
        if target_block is None:
            self.addSublock(sublock)
        return checkbox, sublock

    def getSubBlockbyIdx(self, idx: int) -> ConfigSubBlock:
        return self.subblock_list[idx]


class ConfigContent(QScrollArea):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.config_block_list: List[ConfigBlock] = []
        self.scrollContent = Widget()
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.scrollContent)
        vlayout = QVBoxLayout()
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scrollContent.setLayout(vlayout)
        self.setWidgetResizable(True)
        self.setContentsMargins(0, 0, 0, 0)
        self.vlayout = vlayout
        self.active_label: ConfigTextLabel = None

    def addConfigBlock(self, block: ConfigBlock):
        self.vlayout.addWidget(block)
        self.config_block_list.append(block)

    def setActiveLabel(self, idx0: int, idx1: int):
        if self.active_label is not None:
            self.deactiveLabel()
        block = self.config_block_list[idx0]
        if idx1 >= 0:
            self.active_label = block.label_list[idx1]
        else:
            self.active_label = block.header
        self.active_label.setActiveBackground()
        if C.USE_PYSIDE6:
            self.ensureWidgetVisible(self.active_label, ymargin=self.active_label.height() * 7)
        else:
            self.ensureWidgetVisible(self.active_label, yMargin=self.active_label.height() * 7)

    def deactiveLabel(self):
        if self.active_label is not None:
            self.active_label.setStyleSheet("")
            self.active_label = None


class TableItem(QStandardItem):
    def __init__(self, text, fontsize):
        super().__init__()
        font = self.font()
        font.setPointSizeF(fontsize)
        self.setFont(font)
        self.setText(text)
        self.setEditable(False)

    def setBold(self, bold: bool):
        font = self.font()
        font.setBold(bold)
        self.setFont(font)


class TreeModel(QStandardItemModel):
    # https://stackoverflow.com/questions/32229314/pyqt-how-can-i-set-row-heights-of-qtreeview
    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.SizeHintRole:
            size = QSize()
            item = self.itemFromIndex(index)
            size.setHeight(item.font().pointSize()+20)
            return size
        else:
            return super().data(index, role)


class ConfigTable(QTreeView):
    tableitem_pressed = Signal(int, int)
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        treeModel = TreeModel()
        self.tm = treeModel
        self.setModel(treeModel)
        self.selected: TableItem = None
        self.last_selected: TableItem = None
        self.setHeaderHidden(True)
        self.setMinimumWidth(260)

    def addHeader(self, header: str) -> TableItem:
        rootNode = self.model().invisibleRootItem()
        ti = TableItem(header, CONFIG_FONTSIZE_TABLE)
        rootNode.appendRow(ti)
        return ti

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        dis = deselected.indexes()
        sel = selected.indexes()
        model = self.model()
        self.last_selected = model.itemFromIndex(dis[0]) \
            if len(dis) > 0 else None
        
        self.selected = model.itemFromIndex(sel[0]) \
            if len(sel) > 0 else None
        for i in deselected.indexes():
            self.model().itemFromIndex(i).setBold(False)
        
        index = self.currentIndex()
        if index.isValid():
            self.model().itemFromIndex(index).setBold(True)
        super().selectionChanged(selected, deselected)

    def setCurrentItem(self, idx0, idx1):
        index = self.tm.item(idx0, 0).child(idx1).index()
        self.setCurrentIndex(index)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if self.selected is not None:
            parent = self.selected.parent()
            if parent is None:
                idx1 = -1
                idx0 = self.selected.row()
            else:
                idx1 = self.selected.row()
                idx0 = parent.row()
            self.tableitem_pressed.emit(idx0, idx1)


class ConfigPanel(QDialog):

    save_config = Signal()
    settings_imported = Signal()
    unload_models = Signal()

    def _compact_line_edit(self, tooltip: str, width: int = CONFIG_COMBOBOX_SHORT, placeholder: str = '') -> QLineEdit:
        editor = QLineEdit()
        editor.setFixedWidth(width)
        editor.setFixedHeight(CONFIG_COMBOBOX_HEIGHT)
        editor.setToolTip(tooltip)
        if placeholder:
            editor.setPlaceholderText(placeholder)
        return editor

    def _compact_settings_row(self, *widgets: QWidget) -> QWidget:
        row = QWidget()
        layout = QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        columns = 3
        for index, widget in enumerate(widgets):
            layout.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            layout.setColumnStretch(column, 1)
        return row

    def _labeled_compact_widget(self, label: str, widget: QWidget, tooltip: str) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        label_widget = ConfigTextLabel(label, CONFIG_FONTSIZE_CONTENT - 1)
        label_widget.setToolTip(tooltip)
        widget.setToolTip(tooltip)
        layout.addWidget(label_widget)
        layout.addWidget(widget)
        return container
    reload_textstyle = Signal(bool)
    show_only_custom_font = Signal(bool)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._outside_click_filter_installed = False
        self.setObjectName("ConfigPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(self.tr('Settings'))
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setSizeGripEnabled(True)
        self.resize(1180, 760)
        self.setMinimumSize(860, 600)
        self.configTable = ConfigTable()
        self.configTable.setMinimumWidth(220)
        self.configTable.setMaximumWidth(300)
        self.configTable.tableitem_pressed.connect(self.onTableItemPressed)
        self.configContent = ConfigContent()
        dlConfigPanel, dltableitem = self.addConfigBlock(self.tr('DL Module'))
        generalConfigPanel, generalTableItem = self.addConfigBlock(self.tr('General'))
        
        label_text_det = self.tr('Text Detection')
        label_text_ocr = self.tr('OCR')
        label_inpaint = self.tr('Inpaint')
        label_translator = self.tr('Translator')
        label_startup = self.tr('Startup')
        label_upscaling = self.tr('Upscaling')
        label_page_filtering = self.tr('Page filtering')
        label_pipeline = self.tr('Pipeline')
        label_post_merge = self.tr('Post-merge')
        label_typesetting = self.tr('Typesetting')
        label_save = self.tr('Save')
        label_saladict = self.tr('SalaDict')
        label_settings_presets = self.tr('Settings presets')
    
        dltableitem.appendRows([
            TableItem(label_text_det, CONFIG_FONTSIZE_TABLE),
            TableItem(label_text_ocr, CONFIG_FONTSIZE_TABLE),
            TableItem(label_inpaint, CONFIG_FONTSIZE_TABLE),
            TableItem(label_translator, CONFIG_FONTSIZE_TABLE),
        ])
        generalTableItem.appendRows([
            TableItem(label_upscaling, CONFIG_FONTSIZE_TABLE),
            TableItem(label_page_filtering, CONFIG_FONTSIZE_TABLE),
            TableItem(label_pipeline, CONFIG_FONTSIZE_TABLE),
            TableItem(label_post_merge, CONFIG_FONTSIZE_TABLE),
            TableItem(label_settings_presets, CONFIG_FONTSIZE_TABLE),
            TableItem(label_startup, CONFIG_FONTSIZE_TABLE),
            TableItem(label_typesetting, CONFIG_FONTSIZE_TABLE),
            TableItem(label_save, CONFIG_FONTSIZE_TABLE),
            TableItem(label_saladict, CONFIG_FONTSIZE_TABLE),
        ])
        
        self.load_model_checker, msublock = checkbox_with_label(self.tr('Load models on demand'), discription=self.tr('Loads models only when needed. Saves idle RAM/VRAM; first use or module switch takes longer.'))
        self.load_model_checker.stateChanged.connect(self.on_load_model_changed)
        dlConfigPanel.addSublock(msublock)
        self.empty_runcache_checker, msublock = checkbox_with_label(self.tr('Empty cache after RUN'), discription=self.tr('Releases framework caches after each RUN. Helps long sessions; repeated runs may need warm-up again.'))
        dlConfigPanel.addSublock(msublock)
        self.empty_runcache_checker.stateChanged.connect(self.on_runcache_changed)
        self.unload_model_btn = QPushButton(parent=self)
        self.unload_model_btn.setMaximumWidth(500)
        self.unload_model_btn.setText(self.tr('Unload All Models'))
        self.unload_model_btn.setToolTip(self.tr('Immediately unload loaded detection, OCR, inpaint, and translation models from memory. This frees RAM/VRAM now, but the next run is slower while models are loaded again.'))
        self.unload_model_btn.clicked.connect(self.unload_models)
        msublock.layout().addWidget(self.unload_model_btn)

        dlConfigPanel.addTextLabel(label_text_det)
        self.detect_config_panel = TextDetectConfigPanel(self.tr('Detector'), scrollWidget=self)
        self.detect_sub_block = dlConfigPanel.addBlockWidget(self.detect_config_panel)
        self.detect_config_panel.keep_existing_checker.clicked.connect(self.on_keepline_clicked)

        dlConfigPanel.addTextLabel(label_text_ocr)
        self.ocr_config_panel = OCRConfigPanel(self.tr('OCR'), scrollWidget=self)
        self.ocr_sub_block = dlConfigPanel.addBlockWidget(self.ocr_config_panel)

        dlConfigPanel.addTextLabel(label_inpaint)
        self.inpaint_config_panel = InpaintConfigPanel(self.tr('Inpainter'), scrollWidget=self)
        self.inpaint_sub_block = dlConfigPanel.addBlockWidget(self.inpaint_config_panel)

        dlConfigPanel.addTextLabel(label_translator)
        self.trans_config_panel = TranslatorConfigPanel(label_translator, scrollWidget=self)
        self.trans_sub_block = dlConfigPanel.addBlockWidget(self.trans_config_panel)
        self.pronoun_review_checker, review_subblock = checkbox_with_label(
            self.tr('Review and optimize translation with LLM'),
            discription=self.tr('Runs an extra LLM review for natural wording, source accuracy, pronouns, speaker/addressee references, gendered wording, and formality. Adds LLM requests.'))
        keyword_index = self.trans_config_panel.vlayout.indexOf(self.trans_config_panel.replaceOCRkeywordBtn)
        self.trans_config_panel.vlayout.insertWidget(keyword_index, review_subblock)
        self.pronoun_review_checker.stateChanged.connect(self.on_pronoun_review_changed)

        generalConfigPanel.addTextLabel(label_upscaling)
        self.upscale_before_detection_checker, _ = generalConfigPanel.addCheckBox(
            self.tr('Upscale pages before detection'),
            discription=self.tr('Creates a high-resolution working copy before detection. Can improve OCR and masks; uses more RAM/VRAM and slows later steps.'))
        self.upscale_before_detection_checker.stateChanged.connect(self.on_upscale_before_detection_changed)
        upscale_factor_tip = self.tr('Resolution multiplier for pages that pass the size limits. Higher values can improve small text recognition, but each step runs slower and uses more memory. Example: 2.0 for 2x.')
        upscale_max_edge_tip = self.tr('Maximum long-edge resolution after upscaling. Lower limits keep runs faster and lighter; higher limits preserve more detail but slow down later processing.')
        upscale_skip_edge_tip = self.tr('Pages whose original long edge is already above this value are not upscaled. Lower values skip more large pages and speed up runs; use 0 to always allow upscaling.')
        upscale_quality_tip = self.tr('Quality/speed preset for OpenCV upscaling. Fast is quickest, Quality and AnimeSharp are slower, and AnimeSharp adds stronger manga-style sharpening inspired by 2x-AnimeSharpV4.')
        upscale_artifact_tip = self.tr('Optional cleanup applied before enlargement to reduce JPEG blocks and ringing. Light or Medium can improve compressed scans; Strong may soften fine line art and is slower.')
        self.upscale_factor_edit = self._compact_line_edit(upscale_factor_tip, placeholder='2.0')
        self.upscale_factor_edit.setValidator(QDoubleValidator(1.0, 8.0, 2, self.upscale_factor_edit))
        self.upscale_factor_edit.editingFinished.connect(self.on_upscale_numeric_changed)
        self.upscale_max_edge_edit = self._compact_line_edit(upscale_max_edge_tip, placeholder='4096')
        self.upscale_skip_edge_edit = self._compact_line_edit(upscale_skip_edge_tip, placeholder='2500')
        for editor in [self.upscale_max_edge_edit, self.upscale_skip_edge_edit]:
            editor.setValidator(CustomIntValidator(0, 99999, 5))
            editor.editingFinished.connect(self.on_upscale_numeric_changed)
        self.upscale_quality_combobox = ConfigComboBox(scrollWidget=generalConfigPanel)
        self.upscale_quality_combobox.addItems([
            self.tr('Fast'),
            self.tr('Balanced'),
            self.tr('Quality'),
            self.tr('AnimeSharp'),
        ])
        self.upscale_quality_combobox.setFixedHeight(CONFIG_COMBOBOX_HEIGHT)
        self.upscale_quality_combobox.activated.connect(self.on_upscale_quality_changed)
        self.upscale_artifact_combobox = ConfigComboBox(scrollWidget=generalConfigPanel)
        self.upscale_artifact_combobox.addItems([
            self.tr('Off'),
            self.tr('Light'),
            self.tr('Medium'),
            self.tr('Strong'),
        ])
        self.upscale_artifact_combobox.setFixedHeight(CONFIG_COMBOBOX_HEIGHT)
        self.upscale_artifact_combobox.activated.connect(self.on_upscale_artifact_reduction_changed)
        upscale_row = self._compact_settings_row(
            self._labeled_compact_widget(self.tr('Factor'), self.upscale_factor_edit, upscale_factor_tip),
            self._labeled_compact_widget(self.tr('Max long edge'), self.upscale_max_edge_edit, upscale_max_edge_tip),
            self._labeled_compact_widget(self.tr('Skip above'), self.upscale_skip_edge_edit, upscale_skip_edge_tip),
            self._labeled_compact_widget(self.tr('Quality'), self.upscale_quality_combobox, upscale_quality_tip),
            self._labeled_compact_widget(self.tr('Compression cleanup'), self.upscale_artifact_combobox, upscale_artifact_tip),
        )
        generalConfigPanel.addBlockWidget(upscale_row)

        generalConfigPanel.addTextLabel(label_page_filtering)
        self.skip_cover_title_pages_checker, _ = generalConfigPanel.addCheckBox(
            self.tr('Skip detected cover and title pages in pipeline'),
            discription=self.tr('Detects clearly named cover/title pages and color opening covers, then skips text detection, OCR, translation, and inpainting for them. Disable to process marked pages normally.'),
        )
        self.skip_cover_title_pages_checker.stateChanged.connect(self.on_skip_cover_title_pages_changed)

        generalConfigPanel.addTextLabel(label_pipeline)
        self.translate_after_image_processing_checker, _ = generalConfigPanel.addCheckBox(
            self.tr('Translate after image processing'),
            discription=self.tr(
                'Finish text detection, OCR, and inpainting for every page before starting '
                'translation. This avoids overlapping translation with image processing and '
                'can reduce concurrent RAM, VRAM, and API load, but usually increases total run time.'
            ),
        )
        self.translate_after_image_processing_checker.stateChanged.connect(
            self.on_translate_after_image_processing_changed
        )
        self.pipeline_completion_notification_checker, _ = generalConfigPanel.addCheckBox(
            self.tr('Notify when pipeline finishes'),
            discription=self.tr(
                'Plays a short system sound and shows a Windows notification after a '
                'pipeline or complete batch run finishes successfully.'
            ),
        )
        self.pipeline_completion_notification_checker.stateChanged.connect(
            self.on_pipeline_completion_notification_changed
        )

        generalConfigPanel.addTextLabel(label_post_merge)
        self.post_merge_checker, _ = generalConfigPanel.addCheckBox(
            self.tr('Merge nearby text boxes after pipeline'),
            discription=self.tr('Merges nearby boxes after translation using Region Merge Tool rules. Can reduce cleanup; adds a short post-processing pass.'))
        self.post_merge_checker.stateChanged.connect(self.on_post_merge_changed)
        self.post_merge_mode_combobox, _ = generalConfigPanel.addCombobox(
            [
                self.tr('Vertical Merge'),
                self.tr('Horizontal Merge'),
                self.tr('Vertical then Horizontal'),
                self.tr('Horizontal then Vertical'),
            ],
            self.tr('Post-pipeline merge mode'),
            discription=self.tr('Direction used when automatically merging translated text boxes after the pipeline finishes. Broader merge passes can slightly increase post-processing time.'))
        self.post_merge_mode_combobox.activated.connect(self.on_post_merge_mode_changed)
        post_merge_vgap_tip = self.tr('Maximum pixel distance between stacked boxes for automatic vertical merging. Larger values may merge more boxes and add a small amount of processing time.')
        post_merge_hgap_tip = self.tr('Maximum pixel distance between side-by-side boxes for automatic horizontal merging. Larger values may merge more boxes and add a small amount of processing time.')
        post_merge_woverlap_tip = self.tr('Minimum horizontal overlap required when merging boxes above or below each other. Higher values are stricter and can avoid extra merge work.')
        post_merge_hoverlap_tip = self.tr('Minimum vertical overlap required when merging boxes next to each other. Higher values are stricter and can avoid extra merge work.')
        self.post_merge_vgap_edit = self._compact_line_edit(post_merge_vgap_tip, placeholder='30')
        self.post_merge_hgap_edit = self._compact_line_edit(post_merge_hgap_tip, placeholder='30')
        self.post_merge_woverlap_edit = self._compact_line_edit(post_merge_woverlap_tip, placeholder='50')
        self.post_merge_hoverlap_edit = self._compact_line_edit(post_merge_hoverlap_tip, placeholder='50')
        for editor in [
            self.post_merge_vgap_edit,
            self.post_merge_hgap_edit,
            self.post_merge_woverlap_edit,
            self.post_merge_hoverlap_edit,
        ]:
            editor.setValidator(CustomIntValidator(0, 1000, 4))
            editor.editingFinished.connect(self.on_post_merge_numeric_changed)
        post_merge_row = self._compact_settings_row(
            self._labeled_compact_widget(self.tr('Vertical gap'), self.post_merge_vgap_edit, post_merge_vgap_tip),
            self._labeled_compact_widget(self.tr('Horizontal gap'), self.post_merge_hgap_edit, post_merge_hgap_tip),
            self._labeled_compact_widget(self.tr('Horizontal overlap %'), self.post_merge_woverlap_edit, post_merge_woverlap_tip),
            self._labeled_compact_widget(self.tr('Vertical overlap %'), self.post_merge_hoverlap_edit, post_merge_hoverlap_tip),
        )
        generalConfigPanel.addBlockWidget(post_merge_row)

        generalConfigPanel.addTextLabel(label_settings_presets)
        preset_tip = self.tr('Saved settings snapshots. Applying one replaces the current application settings with the values stored in the preset.')
        preset_container = QWidget()
        preset_layout = QVBoxLayout(preset_container)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(8)
        preset_container.setToolTip(preset_tip)

        preset_selector_layout = QHBoxLayout()
        preset_selector_layout.setContentsMargins(0, 0, 0, 0)
        preset_selector_layout.setSpacing(20)
        preset_label = ConfigTextLabel(self.tr('Preset'), CONFIG_FONTSIZE_CONTENT, QFont.Weight.Normal)
        preset_label.setToolTip(preset_tip)
        self.settings_preset_combobox = ConfigComboBox(fix_size=False, scrollWidget=generalConfigPanel)
        self.settings_preset_combobox.setToolTip(preset_tip)
        self.settings_preset_combobox.setFixedWidth(CONFIG_COMBOBOX_LONG)
        preset_selector_layout.addWidget(preset_label)
        preset_selector_layout.addWidget(self.settings_preset_combobox)
        preset_selector_layout.addStretch(1)
        preset_layout.addLayout(preset_selector_layout)

        self.settings_apply_preset_btn = QPushButton(self.tr('Apply preset'), self)
        self.settings_apply_preset_btn.setToolTip(self.tr('Load the selected settings preset into the current session and update the visible controls.'))
        self.settings_refresh_presets_btn = QPushButton(self.tr('Refresh presets'), self)
        self.settings_refresh_presets_btn.setToolTip(self.tr('Reload the list of available preset JSON files from the presets folder.'))
        self.settings_save_preset_btn = QPushButton(self.tr('Save current as preset'), self)
        self.settings_save_preset_btn.setToolTip(self.tr('Save the current settings as a named reusable preset.'))
        self.settings_import_preset_btn = QPushButton(self.tr('Import preset'), self)
        self.settings_import_preset_btn.setToolTip(self.tr('Copy a settings preset JSON file into the local preset library.'))
        self.settings_export_preset_btn = QPushButton(self.tr('Export selected preset'), self)
        self.settings_export_preset_btn.setToolTip(self.tr('Export the selected preset to a JSON file.'))
        self.settings_export_current_btn = QPushButton(self.tr('Export current settings'), self)
        self.settings_export_current_btn.setToolTip(self.tr('Export the current settings directly to a JSON file.'))
        self.settings_import_current_btn = QPushButton(self.tr('Import settings file'), self)
        self.settings_import_current_btn.setToolTip(self.tr('Load a settings JSON file immediately without first saving it as a preset.'))

        preset_buttons = QGridLayout()
        preset_buttons.setContentsMargins(0, 0, 0, 0)
        preset_buttons.setSpacing(8)
        for index, btn in enumerate([
            self.settings_apply_preset_btn,
            self.settings_refresh_presets_btn,
            self.settings_save_preset_btn,
            self.settings_import_preset_btn,
            self.settings_export_preset_btn,
            self.settings_export_current_btn,
            self.settings_import_current_btn,
        ]):
            preset_buttons.addWidget(btn, index // 3, index % 3)
        for column in range(3):
            preset_buttons.setColumnStretch(column, 1)
        preset_layout.addLayout(preset_buttons)
        generalConfigPanel.addBlockWidget(preset_container)

        self.settings_apply_preset_btn.clicked.connect(self.on_apply_settings_preset)
        self.settings_refresh_presets_btn.clicked.connect(
            lambda _checked=False: self.refresh_settings_presets()
        )
        self.settings_save_preset_btn.clicked.connect(self.on_save_settings_preset)
        self.settings_import_preset_btn.clicked.connect(self.on_import_settings_preset)
        self.settings_export_preset_btn.clicked.connect(self.on_export_settings_preset)
        self.settings_export_current_btn.clicked.connect(self.on_export_current_settings)
        self.settings_import_current_btn.clicked.connect(self.on_import_current_settings)
        self.refresh_settings_presets()

        generalConfigPanel.addTextLabel(label_startup)
        self.open_on_startup_checker, _ = generalConfigPanel.addCheckBox(self.tr('Reopen last project on startup'))
        self.open_on_startup_checker.setToolTip(self.tr('Open the most recently used project automatically when the application starts.'))
        self.open_on_startup_checker.stateChanged.connect(self.on_open_onstartup_changed)
        self.prevent_input_wheel_checker, _ = generalConfigPanel.addCheckBox(
            self.tr('Prevent mouse wheel changes on input fields'),
            discription=self.tr('Ignore mouse wheel changes on combo boxes and spin boxes so scrolling settings does not accidentally change values.'))
        self.prevent_input_wheel_checker.stateChanged.connect(self.on_prevent_input_wheel_changed)

        generalConfigPanel.addTextLabel(label_typesetting)
        dec_program_str = self.tr('decide by program')
        use_global_str = self.tr('use global setting')

        global_fntfmt_widget = QWidget()
        global_fntfmt_layout = QGridLayout(global_fntfmt_widget)
        global_fntfmt_layout.setHorizontalSpacing(8)
        global_fntfmt_layout.setVerticalSpacing(6)
        global_fntfmt_widget.setContentsMargins(0, 0, 0, 0)

        b = generalConfigPanel.addBlockWidget(global_fntfmt_widget)
        b.layout().setContentsMargins(0, 0, 0, 0)
        b.setContentsMargins(0, 0, 0, 0)
        self.let_fntsize_combox, sublock = combobox_with_label(
            [dec_program_str, use_global_str], self.tr('Font Size'),
            parent=self, insert_stretch=True)
        tt_fntsize = self.tr('Choose whether translated text keeps the original detected size from the image or always uses the fixed global font size defined in the text style presets.')
        sublock.name_label.setToolTip(tt_fntsize)
        self.let_fntsize_combox.setToolTip(tt_fntsize)
        sublock.setContentsMargins(0, 2, 12, 2)
        global_fntfmt_layout.addWidget(sublock, 0, 0)

        self.let_fntsize_combox.activated.connect(self.on_fntsize_flag_changed)
        
        self.let_fntstroke_combox, sublock = combobox_with_label(
            [dec_program_str, use_global_str], self.tr('Stroke Size'),
            parent=self, insert_stretch=True)
        tt_stroke = self.tr('Choose whether stroke width is detected dynamically per region based on the original text or taken from the fixed global text style preset.')
        sublock.name_label.setToolTip(tt_stroke)
        self.let_fntstroke_combox.setToolTip(tt_stroke)
        sublock.setContentsMargins(0, 2, 12, 2)
        self.let_fntstroke_combox.activated.connect(self.on_fntstroke_flag_changed)
        global_fntfmt_layout.addWidget(sublock, 0, 1)
        
        self.let_fntcolor_combox, sublock = combobox_with_label(
            [dec_program_str, use_global_str], self.tr('Font Color'),
            parent=self, insert_stretch=True)
        tt_color = self.tr('Choose whether the main text color is detected from the original image or forced to use the global font color setting.')
        sublock.name_label.setToolTip(tt_color)
        self.let_fntcolor_combox.setToolTip(tt_color)
        sublock.setContentsMargins(0, 2, 12, 2)
        self.let_fntcolor_combox.activated.connect(self.on_fontcolor_flag_changed)
        global_fntfmt_layout.addWidget(sublock, 1, 0)
        
        self.let_fnt_scolor_combox, sublock = combobox_with_label(
            [dec_program_str, use_global_str], self.tr('Stroke Color'),
            parent=self, insert_stretch=True)
        tt_scolor = self.tr('Choose whether the text outline (stroke) color is detected from the original image or forced to use the global stroke color setting.')
        sublock.name_label.setToolTip(tt_scolor)
        self.let_fnt_scolor_combox.setToolTip(tt_scolor)
        sublock.setContentsMargins(0, 2, 12, 2)
        self.let_fnt_scolor_combox.activated.connect(self.on_font_scolor_flag_changed)
        global_fntfmt_layout.addWidget(sublock, 1, 1)

        self.let_effect_combox, sublock = combobox_with_label(
            [dec_program_str, use_global_str], self.tr('Effect'),
            parent=self, insert_stretch=True)
        tt_effect = self.tr('Choose whether special text effects such as outlines or drop shadows are detected per region or forced to match the global effect settings.')
        sublock.name_label.setToolTip(tt_effect)
        self.let_effect_combox.setToolTip(tt_effect)
        sublock.setContentsMargins(0, 2, 12, 2)
        self.let_effect_combox.activated.connect(self.on_effect_flag_changed)
        global_fntfmt_layout.addWidget(sublock, 2, 0)
        
        self.let_alignment_combox, sublock = combobox_with_label(
            [dec_program_str, use_global_str], self.tr('Alignment'),
            parent=self, insert_stretch=True)
        tt_align = self.tr('Choose whether paragraph text alignment is detected per region or forced to use the global alignment setting.')
        sublock.name_label.setToolTip(tt_align)
        self.let_alignment_combox.setToolTip(tt_align)
        sublock.setContentsMargins(0, 2, 12, 2)
        self.let_alignment_combox.activated.connect(self.on_alignment_flag_changed)
        global_fntfmt_layout.addWidget(sublock, 2, 1)

        self.let_writing_mode_combox, sublock = combobox_with_label(
            [dec_program_str, use_global_str], self.tr('Writing-mode'),
            parent=self, insert_stretch=True)
        tt_writing = self.tr('Choose whether the text direction is detected automatically per region or forced to follow the global writing direction setting.')
        sublock.name_label.setToolTip(tt_writing)
        self.let_writing_mode_combox.setToolTip(tt_writing)
        sublock.setContentsMargins(0, 2, 12, 2)
        self.let_writing_mode_combox.activated.connect(self.on_writing_mode_flag_changed)
        global_fntfmt_layout.addWidget(sublock, 3, 0)
        
        self.let_family_combox, sublock = combobox_with_label(
            [self.tr('Keep existing'), self.tr('Always use global setting')], self.tr('Font Family'),
            parent=self, insert_stretch=True)
        tt_family = self.tr('Choose whether existing region fonts are preserved or entirely replaced by the global font family setting.')
        sublock.name_label.setToolTip(tt_family)
        self.let_family_combox.setToolTip(tt_family)
        sublock.setContentsMargins(0, 2, 12, 2)
        self.let_family_combox.activated.connect(self.on_family_flag_changed)
        global_fntfmt_layout.addWidget(sublock, 3, 1)

        global_fntfmt_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding), 0, 2)

        self.let_autolayout_checker, sublock = generalConfigPanel.addCheckBox(self.tr('Auto layout'), 
                discription=self.tr('Wraps and scales translated text to fit the detected speech bubble. Longer translations are broken across lines instead of expanding into very wide text boxes.'))

        self.let_autolayout_checker.stateChanged.connect(self.on_autolayout_changed)
        self.let_autolayout_fit_bubble_checker, _ = generalConfigPanel.addCheckBox(
            self.tr('Limit auto-layout boxes to speech bubbles'),
            discription=self.tr('Keeps automatically laid-out text boxes within the detected speech-bubble area and always inside the page edge. Disable only for captions or sound effects that intentionally extend outside a bubble.'))
        self.let_autolayout_fit_bubble_checker.stateChanged.connect(self.on_autolayout_fit_bubble_changed)
        self.let_autolayout_no_linebreak_checker, _ = generalConfigPanel.addCheckBox(
            self.tr('Auto layout without stored line breaks'),
            discription=self.tr('Optimizes box size without persisting line breaks in project text. Rendering can still wrap inside the constrained text box.'))
        self.let_autolayout_no_linebreak_checker.stateChanged.connect(self.on_autolayout_no_linebreak_changed)
        self.let_uppercase_checker, _ = generalConfigPanel.addCheckBox(
            self.tr('To uppercase'),
            discription=self.tr('Convert rendered translation text to uppercase.'))
        self.let_uppercase_checker.stateChanged.connect(self.on_uppercase_changed)

        self.let_textstyle_indep_checker, _ = generalConfigPanel.addCheckBox(
            self.tr('Independent text styles for each project'),
            discription=self.tr('Store text style presets separately per project.'))
        self.let_textstyle_indep_checker.stateChanged.connect(self.on_textstyle_indep_changed)

        self.let_show_only_custom_fonts, sublock = generalConfigPanel.addCheckBox(
            self.tr("Show only custom fonts"),
            discription=self.tr('Shows only fonts from the project fonts folder. Easier to scan and faster with many installed system fonts.'))
        self.let_show_only_custom_fonts.stateChanged.connect(self.on_show_only_custom_fonts)

        generalConfigPanel.addTextLabel(label_save)
        result_format_tip = self.tr('Final exported image format. PNG is lossless but can be larger and slower to write; JPG is smaller and often faster; WEBP/JXL can save space but may take longer to encode.')
        self.rst_imgformat_combobox, imsave_sublock = generalConfigPanel.addCombobox(['PNG', 'JPG', 'WEBP', 'JXL'], self.tr('Result image format'), discription=result_format_tip, show_description=False)
        self.rst_imgformat_combobox.activated.connect(self.on_rst_imgformat_changed)
        self.rst_imgquality_edit = PercentageLineEdit('100')
        self.rst_imgquality_edit.setFixedWidth(CONFIG_COMBOBOX_SHORT)
        self.rst_imgquality_edit.finish_edited.connect(self.on_edit_quality_changed)

        result_quality_tip = self.tr('Final image quality for lossy formats. Higher quality keeps more detail but can write larger files and may export slower.')
        self.rst_imgquality_edit.setToolTip(wrap_tooltip(result_quality_tip))
        sublock = ConfigSubBlock(self.rst_imgquality_edit, self.tr('Quality'), result_quality_tip, vertical_layout=False, show_description=False)
        sublock.layout().setAlignment(Qt.AlignmentFlag.AlignLeft)
        sublock.layout().insertStretch(-1)
        imsave_sublock.layout().addWidget(sublock)

        intermediate_format_tip = self.tr('Format for project working images such as masks and inpainted pages. PNG is safest but can use more disk space; JPG/WEBP/JXL can reduce disk usage but may add encoding time.')
        self.intermediate_imgformat_combobox, intermediate_imsave_sublock = generalConfigPanel.addCombobox(['PNG', 'JPG', 'WEBP', 'JXL'], self.tr('Intermediate image format'), discription=intermediate_format_tip, show_description=False)
        self.intermediate_imgformat_combobox.activated.connect(self.on_intermediate_imgformat_changed)
        self.intermediate_imgquality_edit = PercentageLineEdit('100')
        self.intermediate_imgquality_edit.setFixedWidth(CONFIG_COMBOBOX_SHORT)
        self.intermediate_imgquality_edit.finish_edited.connect(self.on_intermediate_quality_changed)

        intermediate_quality_tip = self.tr('Quality for lossy intermediate working images. Higher values preserve detail for later steps, but use more disk space and can slow writes.')
        self.intermediate_imgquality_edit.setToolTip(wrap_tooltip(intermediate_quality_tip))
        sublock = ConfigSubBlock(self.intermediate_imgquality_edit, self.tr('Intermediate quality'), intermediate_quality_tip, vertical_layout=False, show_description=False)
        sublock.layout().setAlignment(Qt.AlignmentFlag.AlignLeft)
        sublock.layout().insertStretch(-1)
        intermediate_imsave_sublock.layout().addWidget(sublock)

        generalConfigPanel.addTextLabel(label_saladict)

        sublock = ConfigSubBlock(ConfigTextLabel(self.tr("<a href=\"https://github.com/dmMaze/BallonsTranslator/tree/master/doc/saladict.md\">Installation guide</a>"), CONFIG_FONTSIZE_CONTENT - 2), vertical_layout=False)
        sublock.layout().insertStretch(-1)
        generalConfigPanel.addSublock(sublock)

        self.selectext_minimenu_checker, _ = generalConfigPanel.addCheckBox(
            self.tr('Show mini menu when selecting text'),
            discription=self.tr('Show the SalaDict mini menu when text is selected.'))
        self.selectext_minimenu_checker.stateChanged.connect(self.on_selectext_minimenu_changed)
        self.saladict_shortcut = QKeySequenceEdit("ALT+W", self)
        self.saladict_shortcut.keySequenceChanged.connect(self.on_saladict_shortcut_changed)
        self.saladict_shortcut.setFixedWidth(CONFIG_COMBOBOX_MIDEAN)

        saladict_shortcut_tip = self.tr('Keyboard shortcut for SalaDict lookup.')
        self.saladict_shortcut.setToolTip(saladict_shortcut_tip)
        sublock = ConfigSubBlock(self.saladict_shortcut, self.tr("Shortcut"), saladict_shortcut_tip, vertical_layout=False)
        sublock.layout().insertStretch(-1)
        generalConfigPanel.addSublock(sublock)
        self.searchurl_combobox, _ = generalConfigPanel.addCombobox(["https://www.google.com/search?q=", "https://www.bing.com/search?q=", "https://duckduckgo.com/?q=", "https://yandex.com/search/?text=", "http://www.baidu.com/s?wd=", "https://search.yahoo.com/search;?p=", "https://www.urbandictionary.com/define.php?term="], self.tr("Search Engines"), discription=self.tr('Search URL used by SalaDict lookups.'), fix_size=False)
        self.searchurl_combobox.setEditable(True)
        self.searchurl_combobox.setFixedWidth(CONFIG_COMBOBOX_LONG)
        self.searchurl_combobox.currentTextChanged.connect(self.on_searchurl_changed)

        self.configPages = self._build_config_pages()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.configTable)
        splitter.addWidget(self.configPages)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 930])
        hlayout = QHBoxLayout(self)

        hlayout.addWidget(splitter)
        hlayout.setSpacing(0)
        hlayout.setContentsMargins(0, 0, 0, 0)

        self.configTable.expandAll()
        first_header = self.configTable.tm.item(0, 0)
        if first_header is not None:
            self.configTable.setCurrentIndex(first_header.index())
            self.onTableItemPressed(0, -1)

    def _build_config_pages(self) -> QStackedWidget:
        pages = QStackedWidget(self)
        self._config_page_indexes = {}
        for idx0, block in enumerate(self.configContent.config_block_list):
            sections = [(-1, block.header, [])]
            sections.extend(
                (idx1, label, []) for idx1, label in enumerate(block.label_list)
            )
            section_map = {idx1: widgets for idx1, _label, widgets in sections}
            for subblock in block.subblock_list:
                section_map.setdefault(subblock.idx1, []).append(subblock)

            for idx1, title, widgets in sections:
                page = self._create_config_page(title, widgets)
                self._config_page_indexes[(idx0, idx1)] = pages.addWidget(page)
        self.configContent.setParent(self)
        self.configContent.hide()
        return pages

    def _create_config_page(self, title: QWidget, widgets: List[QWidget]) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = Widget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(title)
        for widget in widgets:
            layout.addWidget(widget)
        layout.addStretch(1)
        scroll.setWidget(content)
        for widget in content.findChildren(QWidget):
            if hasattr(widget, 'setScrollWidget'):
                widget.setScrollWidget(scroll)
        return scroll

    def refresh_settings_presets(self, selected: str = None):
        current = selected or self.settings_preset_combobox.currentText()
        self.settings_preset_combobox.blockSignals(True)
        self.settings_preset_combobox.clear()
        presets = list_config_presets()
        self.settings_preset_combobox.addItems(presets)
        if current in presets:
            self.settings_preset_combobox.setCurrentText(current)
        self.settings_preset_combobox.blockSignals(False)
        has_presets = len(presets) > 0
        self.settings_apply_preset_btn.setEnabled(has_presets)
        self.settings_export_preset_btn.setEnabled(has_presets)

    def _apply_imported_config(self, config, source_label: str):
        pcfg.merge(config)
        save_config()
        self.setupConfig()
        self.settings_imported.emit()
        QMessageBox.information(self, self.tr('Settings'), self.tr('Settings loaded from ') + source_label)

    def on_apply_settings_preset(self):
        preset_name = self.settings_preset_combobox.currentText()
        if not preset_name:
            return
        try:
            self._apply_imported_config(load_config_preset(preset_name), preset_name)
        except Exception as e:
            QMessageBox.warning(self, self.tr('Settings'), self.tr('Failed to apply settings preset: ') + str(e))

    def on_save_settings_preset(self):
        preset_name, ok = QInputDialog.getText(self, self.tr('Save settings preset'), self.tr('Preset name:'))
        if not ok or not preset_name.strip():
            return
        try:
            preset_path = save_config_preset(preset_name)
            self.refresh_settings_presets(preset_path.rsplit('\\', 1)[-1].rsplit('/', 1)[-1].rsplit('.', 1)[0])
            QMessageBox.information(self, self.tr('Settings'), self.tr('Settings preset saved.'))
        except Exception as e:
            QMessageBox.warning(self, self.tr('Settings'), self.tr('Failed to save settings preset: ') + str(e))

    def on_import_settings_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr('Import settings preset'), CONFIG_PRESET_DIR, self.tr('JSON files (*.json)'))
        if not path:
            return
        try:
            preset_name = import_config_preset(path)
            self.refresh_settings_presets(preset_name)
            QMessageBox.information(self, self.tr('Settings'), self.tr('Settings preset imported.'))
        except Exception as e:
            QMessageBox.warning(self, self.tr('Settings'), self.tr('Failed to import settings preset: ') + str(e))

    def on_export_settings_preset(self):
        preset_name = self.settings_preset_combobox.currentText()
        if not preset_name:
            return
        path, _ = QFileDialog.getSaveFileName(self, self.tr('Export settings preset'), preset_name + '.json', self.tr('JSON files (*.json)'))
        if not path:
            return
        if not path.lower().endswith('.json'):
            path += '.json'
        try:
            if export_config_preset(preset_name, path):
                QMessageBox.information(self, self.tr('Settings'), self.tr('Settings preset exported.'))
            else:
                QMessageBox.warning(self, self.tr('Settings'), self.tr('Failed to export settings preset.'))
        except Exception as e:
            QMessageBox.warning(self, self.tr('Settings'), self.tr('Failed to export settings preset: ') + str(e))

    def on_export_current_settings(self):
        path, _ = QFileDialog.getSaveFileName(self, self.tr('Export current settings'), 'ballonstranslator-settings.json', self.tr('JSON files (*.json)'))
        if not path:
            return
        if not path.lower().endswith('.json'):
            path += '.json'
        if export_program_config(path):
            QMessageBox.information(self, self.tr('Settings'), self.tr('Current settings exported.'))
        else:
            QMessageBox.warning(self, self.tr('Settings'), self.tr('Failed to export current settings.'))

    def on_import_current_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr('Import settings file'), CONFIG_PRESET_DIR, self.tr('JSON files (*.json)'))
        if not path:
            return
        try:
            self._apply_imported_config(import_program_config(path), path)
        except Exception as e:
            QMessageBox.warning(self, self.tr('Settings'), self.tr('Failed to import settings file: ') + str(e))

    def on_load_model_changed(self):
        pcfg.module.load_model_on_demand = self.load_model_checker.isChecked()

    def on_runcache_changed(self):
        pcfg.module.empty_runcache = self.empty_runcache_checker.isChecked()

    def on_keepline_clicked(self):
        pcfg.module.keep_exist_textlines = self.detect_config_panel.keep_existing_checker.isChecked()

    def addConfigBlock(self, header: str) -> Tuple[ConfigBlock, TableItem]:
        cb = ConfigBlock(header, parent=self)
        cb.sublock_pressed.connect(self.onSublockPressed)
        self.configContent.addConfigBlock(cb)
        cb.setIndex(len(self.configContent.config_block_list)-1)
        ti = self.configTable.addHeader(header)
        return cb, ti

    def onSublockPressed(self, idx0, idx1):
        self.configTable.setCurrentItem(idx0, idx1)
        self.configContent.deactiveLabel()

    def onTableItemPressed(self, idx0, idx1):
        page_index = self._config_page_indexes.get((idx0, idx1))
        if page_index is not None:
            self.configPages.setCurrentIndex(page_index)

    def showConfigDialog(self):
        self._installOutsideClickFilter()
        self.show()
        self.raise_()
        self.activateWindow()

    def _installOutsideClickFilter(self):
        if self._outside_click_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._outside_click_filter_installed = True

    def _removeOutsideClickFilter(self):
        if not self._outside_click_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._outside_click_filter_installed = False

    def eventFilter(self, watched, event):
        if not self.isVisible() or not isinstance(watched, QWidget):
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.MouseButtonPress:
            if (
                QApplication.activePopupWidget() is None
                and not self._widgetInsidePanel(watched)
                and not self._activeWidgetInWhitelist()
            ):
                self.hide()
        return super().eventFilter(watched, event)

    def _widgetInsidePanel(self, widget) -> bool:
        while widget is not None:
            if widget is self:
                return True
            widget = widget.parentWidget()
        return False

    def _activeWidgetInWhitelist(self) -> bool:
        return any(
            self._widgetInWhitelist(widget)
            for widget in (
                QApplication.activeWindow(),
                QApplication.activeModalWidget(),
                QApplication.focusWidget(),
            )
        )

    def _widgetInWhitelist(self, widget) -> bool:
        while widget is not None:
            if self._isWhitelistedWidget(widget):
                return True
            window = widget.window()
            if window is not widget and self._isWhitelistedWidget(window):
                return True
            widget = widget.parentWidget()
        return False

    def _isWhitelistedWidget(self, widget) -> bool:
        return (
            isinstance(widget, QMessageBox)
            or widget.__class__.__name__ in PRESERVE_ACTIVE_WIDGET_CLASS_NAMES
        )

    def on_open_onstartup_changed(self):
        pcfg.open_recent_on_startup = self.open_on_startup_checker.isChecked()

    def on_prevent_input_wheel_changed(self):
        pcfg.prevent_input_wheel_changes = self.prevent_input_wheel_checker.isChecked()

    def on_upscale_before_detection_changed(self):
        pcfg.upscale_before_detection = self.upscale_before_detection_checker.isChecked()

    def on_upscale_quality_changed(self):
        quality_map = ['fast', 'balanced', 'quality', 'animesharp']
        pcfg.upscale_quality = quality_map[self.upscale_quality_combobox.currentIndex()]

    def on_upscale_artifact_reduction_changed(self):
        strength_map = ['off', 'light', 'medium', 'strong']
        pcfg.upscale_artifact_reduction = strength_map[self.upscale_artifact_combobox.currentIndex()]

    def on_upscale_numeric_changed(self):
        try:
            factor = float(self.upscale_factor_edit.text().strip())
        except ValueError:
            factor = 2.0
        factor = max(1.0, min(factor, 8.0))
        self.upscale_factor_edit.setText(str(factor))
        pcfg.upscale_factor = factor

        def read_int(editor: QLineEdit, default: int) -> int:
            text = editor.text().strip()
            if not text.isnumeric():
                editor.setText(str(default))
                return default
            return int(text)

        pcfg.upscale_max_long_edge = read_int(self.upscale_max_edge_edit, 4096)
        pcfg.upscale_skip_if_long_edge_above = read_int(self.upscale_skip_edge_edit, 2500)

    def on_fntsize_flag_changed(self):
        pcfg.let_fntsize_flag = self.let_fntsize_combox.currentIndex()

    def on_fntstroke_flag_changed(self):
        pcfg.let_fntstroke_flag = self.let_fntstroke_combox.currentIndex()

    def on_autolayout_changed(self):
        pcfg.let_autolayout_flag = self.let_autolayout_checker.isChecked()

    def on_autolayout_fit_bubble_changed(self):
        pcfg.let_autolayout_fit_bubble_flag = self.let_autolayout_fit_bubble_checker.isChecked()

    def on_autolayout_no_linebreak_changed(self):
        pcfg.let_autolayout_no_linebreak_flag = self.let_autolayout_no_linebreak_checker.isChecked()

    def on_post_merge_changed(self):
        pcfg.module.post_merge_textboxes = self.post_merge_checker.isChecked()

    def on_skip_cover_title_pages_changed(self):
        pcfg.module.skip_cover_title_pages = self.skip_cover_title_pages_checker.isChecked()

    def on_translate_after_image_processing_changed(self):
        pcfg.module.translate_after_image_processing = (
            self.translate_after_image_processing_checker.isChecked()
        )

    def on_pipeline_completion_notification_changed(self):
        pcfg.module.pipeline_completion_notification = (
            self.pipeline_completion_notification_checker.isChecked()
        )

    def on_pronoun_review_changed(self):
        pcfg.module.pronoun_review_after_translation = self.pronoun_review_checker.isChecked()

    def on_post_merge_mode_changed(self):
        mode_map = {
            0: 'VERTICAL',
            1: 'HORIZONTAL',
            2: 'VERTICAL_THEN_HORIZONTAL',
            3: 'HORIZONTAL_THEN_VERTICAL',
        }
        pcfg.module.post_merge_mode = mode_map.get(self.post_merge_mode_combobox.currentIndex(), 'VERTICAL_THEN_HORIZONTAL')

    def on_post_merge_numeric_changed(self):
        def read_int(editor: QLineEdit, default: int) -> int:
            text = editor.text().strip()
            if not text.isnumeric():
                editor.setText(str(default))
                return default
            return int(text)

        pcfg.module.post_merge_max_vertical_gap = read_int(self.post_merge_vgap_edit, 30)
        pcfg.module.post_merge_max_horizontal_gap = read_int(self.post_merge_hgap_edit, 30)
        pcfg.module.post_merge_min_width_overlap_ratio = read_int(self.post_merge_woverlap_edit, 50)
        pcfg.module.post_merge_min_height_overlap_ratio = read_int(self.post_merge_hoverlap_edit, 50)

    def on_uppercase_changed(self):
        pcfg.let_uppercase_flag = self.let_uppercase_checker.isChecked()
        pcfg.let_text_case = 'upper' if pcfg.let_uppercase_flag else 'normal'

    def on_textstyle_indep_changed(self):
        pcfg.let_textstyle_indep_flag = self.let_textstyle_indep_checker.isChecked()
        self.reload_textstyle.emit(pcfg.let_textstyle_indep_flag)

    def on_rst_imgformat_changed(self):
        pcfg.imgsave_ext = '.' + self.rst_imgformat_combobox.currentText().lower()

    def on_intermediate_imgformat_changed(self):
        pcfg.intermediate_imgsave_ext = '.' + self.intermediate_imgformat_combobox.currentText().lower()

    def on_edit_quality_changed(self, value: str):
        pcfg.imgsave_quality = int(value)

    def on_intermediate_quality_changed(self, value: str):
        pcfg.intermediate_imgsave_quality = int(value)

    def on_selectext_minimenu_changed(self):
        pcfg.textselect_mini_menu = self.selectext_minimenu_checker.isChecked()

    def on_saladict_shortcut_changed(self):
        kstr = self.saladict_shortcut.keySequence().toString()
        if kstr:
            pcfg.saladict_shortcut = self.saladict_shortcut.keySequence().toString()

    def on_searchurl_changed(self):
        url = self.searchurl_combobox.currentText()
        pcfg.search_url = url

    def on_fontcolor_flag_changed(self):
        pcfg.let_fntcolor_flag = self.let_fntcolor_combox.currentIndex()

    def on_font_scolor_flag_changed(self):
        pcfg.let_fnt_scolor_flag = self.let_fnt_scolor_combox.currentIndex()

    def on_alignment_flag_changed(self):
        pcfg.let_alignment_flag = self.let_alignment_combox.currentIndex()

    def on_writing_mode_flag_changed(self):
        pcfg.let_writing_mode_flag = self.let_writing_mode_combox.currentIndex()

    def on_family_flag_changed(self):
        pcfg.let_family_flag = self.let_family_combox.currentIndex()

    def on_effect_flag_changed(self):
        pcfg.let_fnteffect_flag = self.let_effect_combox.currentIndex()

    def on_show_only_custom_fonts(self):
        pcfg.let_show_only_custom_fonts_flag = self.let_show_only_custom_fonts.isChecked()
        self.show_only_custom_font.emit(pcfg.let_show_only_custom_fonts_flag)

    def focusOnTranslator(self):
        self.showConfigDialog()
        idx0, idx1 = self.trans_sub_block.idx0, self.trans_sub_block.idx1
        self.configTable.setCurrentItem(idx0, idx1)
        self.configTable.tableitem_pressed.emit(idx0, idx1)

    def focusOnInpaint(self):
        self.showConfigDialog()
        idx0, idx1 = self.inpaint_sub_block.idx0, self.inpaint_sub_block.idx1
        self.configTable.setCurrentItem(idx0, idx1)
        self.configTable.tableitem_pressed.emit(idx0, idx1)

    def focusOnDetect(self):
        self.showConfigDialog()
        idx0, idx1 = self.detect_sub_block.idx0, self.detect_sub_block.idx1
        self.configTable.setCurrentItem(idx0, idx1)
        self.configTable.tableitem_pressed.emit(idx0, idx1)

    def focusOnOCR(self):
        self.showConfigDialog()
        idx0, idx1 = self.ocr_sub_block.idx0, self.ocr_sub_block.idx1
        self.configTable.setCurrentItem(idx0, idx1)
        self.configTable.tableitem_pressed.emit(idx0, idx1)

    def hideEvent(self, e) -> None:
        self._removeOutsideClickFilter()
        self.save_config.emit()
        return super().hideEvent(e)
        
    def setupConfig(self):
        self.blockSignals(True)

        if pcfg.open_recent_on_startup:
            self.open_on_startup_checker.setChecked(True)
        self.prevent_input_wheel_checker.setChecked(pcfg.prevent_input_wheel_changes)
        self.upscale_before_detection_checker.setChecked(pcfg.upscale_before_detection)
        self.upscale_factor_edit.setText(str(pcfg.upscale_factor))
        self.upscale_max_edge_edit.setText(str(pcfg.upscale_max_long_edge))
        self.upscale_skip_edge_edit.setText(str(pcfg.upscale_skip_if_long_edge_above))
        upscale_qualities = ['fast', 'balanced', 'quality', 'animesharp']
        self.upscale_quality_combobox.setCurrentIndex(
            upscale_qualities.index(pcfg.upscale_quality)
            if pcfg.upscale_quality in upscale_qualities else 1
        )
        artifact_levels = ['off', 'light', 'medium', 'strong']
        self.upscale_artifact_combobox.setCurrentIndex(
            artifact_levels.index(pcfg.upscale_artifact_reduction)
            if pcfg.upscale_artifact_reduction in artifact_levels else 0
        )

        self.detect_config_panel.keep_existing_checker.setChecked(pcfg.module.keep_exist_textlines)
        self.let_effect_combox.setCurrentIndex(pcfg.let_fnteffect_flag)
        self.let_fntsize_combox.setCurrentIndex(pcfg.let_fntsize_flag)
        self.let_fntstroke_combox.setCurrentIndex(pcfg.let_fntstroke_flag)
        self.let_fntcolor_combox.setCurrentIndex(pcfg.let_fntcolor_flag)
        self.let_fnt_scolor_combox.setCurrentIndex(pcfg.let_fnt_scolor_flag)
        self.let_alignment_combox.setCurrentIndex(pcfg.let_alignment_flag)
        self.let_family_combox.setCurrentIndex(pcfg.let_family_flag)
        self.let_writing_mode_combox.setCurrentIndex(pcfg.let_writing_mode_flag)
        self.let_autolayout_checker.setChecked(pcfg.let_autolayout_flag)
        self.let_autolayout_fit_bubble_checker.setChecked(pcfg.let_autolayout_fit_bubble_flag)
        self.let_autolayout_no_linebreak_checker.setChecked(pcfg.let_autolayout_no_linebreak_flag)
        self.skip_cover_title_pages_checker.setChecked(pcfg.module.skip_cover_title_pages)
        self.translate_after_image_processing_checker.setChecked(
            pcfg.module.translate_after_image_processing
        )
        self.pipeline_completion_notification_checker.setChecked(
            pcfg.module.pipeline_completion_notification
        )
        self.post_merge_checker.setChecked(pcfg.module.post_merge_textboxes)
        self.pronoun_review_checker.setChecked(pcfg.module.pronoun_review_after_translation)
        post_merge_modes = ['VERTICAL', 'HORIZONTAL', 'VERTICAL_THEN_HORIZONTAL', 'HORIZONTAL_THEN_VERTICAL']
        if pcfg.module.post_merge_mode in post_merge_modes:
            self.post_merge_mode_combobox.setCurrentIndex(post_merge_modes.index(pcfg.module.post_merge_mode))
        self.post_merge_vgap_edit.setText(str(pcfg.module.post_merge_max_vertical_gap))
        self.post_merge_hgap_edit.setText(str(pcfg.module.post_merge_max_horizontal_gap))
        self.post_merge_woverlap_edit.setText(str(pcfg.module.post_merge_min_width_overlap_ratio))
        self.post_merge_hoverlap_edit.setText(str(pcfg.module.post_merge_min_height_overlap_ratio))
        self.selectext_minimenu_checker.setChecked(pcfg.textselect_mini_menu)
        self.let_uppercase_checker.setChecked(pcfg.let_uppercase_flag)
        pcfg.let_text_case = getattr(pcfg, 'let_text_case', 'upper' if pcfg.let_uppercase_flag else 'normal')
        self.let_uppercase_checker.setChecked(pcfg.let_text_case == 'upper')
        self.let_textstyle_indep_checker.setChecked(pcfg.let_textstyle_indep_flag)
        self.saladict_shortcut.setKeySequence(pcfg.saladict_shortcut)
        self.searchurl_combobox.setCurrentText(pcfg.search_url)
        self.ocr_config_panel.restoreEmptyOCRChecker.setChecked(pcfg.restore_ocr_empty)
        self.rst_imgformat_combobox.setCurrentText(pcfg.imgsave_ext.replace('.', '').upper())
        self.intermediate_imgformat_combobox.setCurrentText(pcfg.intermediate_imgsave_ext.replace('.', '').upper())
        self.rst_imgquality_edit.setText(str(pcfg.imgsave_quality))
        self.intermediate_imgquality_edit.setText(str(pcfg.intermediate_imgsave_quality))
        self.load_model_checker.setChecked(pcfg.module.load_model_on_demand)
        self.empty_runcache_checker.setChecked(pcfg.module.empty_runcache)
        self.let_show_only_custom_fonts.setChecked(pcfg.let_show_only_custom_fonts_flag)

        self.blockSignals(False)
