from typing import List, Callable

from modules import GET_VALID_INPAINTERS, GET_VALID_TEXTDETECTORS, GET_VALID_TRANSLATORS, GET_VALID_OCR, \
    BaseTranslator, DEFAULT_DEVICE, GPUINTENSIVE_SET
from modules.translators.base import lang_display_label
from utils.logger import logger as LOGGER
from .custom_widget import ConfigComboBox, ParamComboBox, NoBorderPushBtn, ParamNameLabel
from .tooltip_utils import wrap_tooltip
from utils.shared import CONFIG_COMBOBOX_LONG, size2width, CONFIG_COMBOBOX_SHORT, CONFIG_COMBOBOX_HEIGHT
from utils.config import pcfg, sample_module_param_value

from qtpy.QtWidgets import QPlainTextEdit, QHBoxLayout, QVBoxLayout, QWidget, QLabel, QCheckBox, QLineEdit, QGridLayout, QPushButton, QSizePolicy
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QDoubleValidator


WIDE_PARAM_KEYWORDS = (
    'api key', 'apikey', 'token', 'secret', 'password',
    'endpoint', 'url', 'proxy', 'prompt', 'template', 'glossary', 'sample',
)
EDITOR_PARAM_KEYWORDS = ('prompt', 'template', 'glossary', 'sample')
CONFIG_FIELD_WIDE = int(CONFIG_COMBOBOX_LONG * 1.45)


def param_key_uses_wide_field(param_key: str) -> bool:
    key = param_key.lower()
    return any(keyword in key for keyword in WIDE_PARAM_KEYWORDS)


def param_key_uses_tall_editor(param_key: str) -> bool:
    key = param_key.lower()
    return any(keyword in key for keyword in EDITOR_PARAM_KEYWORDS)


class ParamCheckGroup(QWidget):

    paramwidget_edited = Signal(str, dict)

    def __init__(self, param_key, check_group: dict, parent=None) -> None:
        super().__init__(parent=parent)
        self.param_key = param_key
        layout = QHBoxLayout(self)
        self.label2widget = {}
        for k, v in check_group.items():
            checker = QCheckBox(text=k, parent=self)
            checker.setChecked(v)
            layout.addWidget(checker)
            self.label2widget[k] = checker
            checker.clicked.connect(self.on_checker_clicked)

    def on_checker_clicked(self):
        new_state_dict = {}
        w = QCheckBox()
        for k, w in self.label2widget.items():
            new_state_dict[k] = w.isChecked()
        self.paramwidget_edited.emit(self.param_key, new_state_dict)


class ParamLineEditor(QLineEdit):
    
    paramwidget_edited = Signal(str, str)
    def __init__(self, param_key: str, force_digital, size='short', *args, **kwargs) -> None:
        super().__init__( *args, **kwargs)
        self.param_key = param_key
        width = size2width(size)
        if not force_digital and param_key_uses_wide_field(param_key):
            width = max(width, CONFIG_FIELD_WIDE)
        self.setFixedWidth(width)
        self.setFixedHeight(max(CONFIG_COMBOBOX_HEIGHT, 34))
        self.textChanged.connect(self.on_text_changed)

        if force_digital:
            validator = QDoubleValidator()
            self.setValidator(validator)

    def on_text_changed(self):
        self.paramwidget_edited.emit(self.param_key, self.text())

class ParamEditor(QPlainTextEdit):
    
    paramwidget_edited = Signal(str, str)
    def __init__(self, param_key: str, *args, **kwargs) -> None:
        super().__init__( *args, **kwargs)
        self.param_key = param_key

        if param_key == 'chat sample':
            self.setFixedWidth(CONFIG_FIELD_WIDE)
            self.setFixedHeight(240)
        elif param_key_uses_tall_editor(param_key):
            self.setMinimumWidth(CONFIG_FIELD_WIDE)
            self.setMinimumHeight(270)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            self.setFixedWidth(CONFIG_COMBOBOX_LONG)
            self.setFixedHeight(100)
        # self.setFixedHeight(CONFIG_COMBOBOX_HEIGHT)
        self.textChanged.connect(self.on_text_changed)

    def on_text_changed(self):
        self.paramwidget_edited.emit(self.param_key, self.text())

    def setText(self, text: str):
        self.setPlainText(text)

    def text(self):
        return self.toPlainText()


class ParamCheckerBox(QWidget):
    checker_changed = Signal(bool)
    paramwidget_edited = Signal(str, str)
    def __init__(self, param_key: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.param_key = param_key
        self.checker = QCheckBox()
        name_label = ParamNameLabel(param_key)
        self.name_label = name_label
        hlayout = QHBoxLayout(self)
        hlayout.addWidget(name_label)
        hlayout.addWidget(self.checker)
        hlayout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.checker.stateChanged.connect(self.on_checker_changed)

    def on_checker_changed(self):
        is_checked = self.checker.isChecked()
        self.checker_changed.emit(is_checked)
        checked = 'true' if is_checked else 'false'
        self.paramwidget_edited.emit(self.param_key, checked)


class ParamCheckBox(QCheckBox):
    paramwidget_edited = Signal(str, bool)
    def __init__(self, param_key: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.param_key = param_key
        self.stateChanged.connect(self.on_checker_changed)

    def on_checker_changed(self):
        self.paramwidget_edited.emit(self.param_key, self.isChecked())


def get_param_display_name(param_key: str, param_dict: dict = None):
    if param_dict is not None and isinstance(param_dict, dict):
        if 'display_name' in param_dict:
            return param_dict['display_name']
    return param_key


class ParamPushButton(QPushButton):
    paramwidget_edited = Signal(str, str)
    def __init__(self, param_key: str, param_dict: dict = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.param_key = param_key
        self.setText(get_param_display_name(param_key, param_dict))
        self.clicked.connect(self.on_clicked)

    def on_clicked(self):
        self.paramwidget_edited.emit(self.param_key, '')


class ParamWidget(QWidget):

    paramwidget_edited = Signal(str, dict)

    def __init__(self, params, scrollWidget: QWidget = None, module_config_key: str = '', module_name: str = '', *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.module_config_key = module_config_key
        self.module_name = module_name
        layout = QHBoxLayout(self)
        self.param_layout = param_layout = QGridLayout()
        param_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        param_layout.setContentsMargins(0, 0, 0, 0)
        param_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(param_layout)
        layout.addStretch(-1)

        if 'description' in params:
            self.setToolTip(wrap_tooltip(params['description']))

        for ii, param_key in enumerate(params):
            if param_key == 'description' or param_key.startswith('__'):
                continue
            display_param_name = param_key
            description = None

            require_label = True
            is_str = isinstance(params[param_key], str)
            is_digital = isinstance(params[param_key], float) or isinstance(params[param_key], int)
            param_widget = None
            reset_btn = None

            if isinstance(params[param_key], bool):
                param_widget = ParamCheckBox(param_key)
                val = params[param_key]
                param_widget.setChecked(val)
                param_widget.paramwidget_edited.connect(self.on_paramwidget_edited)

            elif is_str or is_digital:
                param_widget = ParamLineEditor(param_key, force_digital=is_digital)
                val = params[param_key]
                if is_digital:
                    val = str(val)
                param_widget.setText(val)
                param_widget.paramwidget_edited.connect(self.on_paramwidget_edited)

            elif isinstance(params[param_key], dict):
                param_dict = params[param_key]
                display_param_name = get_param_display_name(param_key, param_dict)
                description = param_dict.get('description')
                value = params[param_key]['value']
                param_widget = None  # Ensure initialization
                param_type = param_dict['type'] if 'type' in param_dict else 'line_editor'
                flush_btn = param_dict.get('flush_btn', False)
                path_selector = param_dict.get('path_selector', False)
                param_size = param_dict.get('size', 'short')
                if param_type == 'selector':
                    if 'url' in param_key:
                        size = CONFIG_FIELD_WIDE
                    else:
                        size = size2width(param_size)

                    param_widget = ParamComboBox(
                        param_key, param_dict['options'], size=size, scrollWidget=scrollWidget, flush_btn=flush_btn, path_selector=path_selector)

                    if param_key == 'device' and DEFAULT_DEVICE == 'cpu':
                        param_dict['value'] = 'cpu'
                        for ii, device in enumerate(param_dict['options']):
                            if device in GPUINTENSIVE_SET:
                                model = param_widget.model()
                                item = model.item(ii, 0)
                                item.setEnabled(False)
                    param_widget.setCurrentText(str(value))
                    param_widget.setEditable(param_dict.get('editable', False))

                elif param_type == 'editor':
                    param_widget = ParamEditor(param_key)
                    param_widget.setText(value)
                    key_l = param_key.lower()
                    if 'prompt' in key_l or 'glossary' in key_l:
                        reset_value = sample_module_param_value(self.module_config_key, self.module_name, param_key, None)
                        if reset_value is not None:
                            reset_btn = QPushButton(self.tr('Reset'))
                            reset_btn.setToolTip(self.tr('Reset this prompt to config.sample default.'))
                            reset_btn.clicked.connect(lambda checked=False, w=param_widget, k=param_key, v=reset_value: self.on_resetbtn_clicked(w, k, v))

                elif param_type == 'checkbox':
                    param_widget = ParamCheckBox(param_key)
                    if isinstance(value, str):
                        value = value.lower().strip() == 'true'
                        params[param_key]['value'] = value
                    param_widget.setChecked(value)

                elif param_type == 'pushbtn':
                    param_widget = ParamPushButton(param_key, param_dict)
                    require_label = False

                elif param_type == 'line_editor':
                    param_widget = ParamLineEditor(param_key, force_digital=is_digital)
                    param_widget.setText(str(value))

                elif param_type == 'check_group':
                    param_widget = ParamCheckGroup(param_key, check_group=value)

                if param_widget is not None:
                    param_widget.paramwidget_edited.connect(self.on_paramwidget_edited)

            tooltip = wrap_tooltip(description)
            if tooltip and param_widget is not None:
                param_widget.setToolTip(tooltip)
            widget_idx = 0
            if require_label:
                param_label = ParamNameLabel(display_param_name)
                if tooltip:
                    param_label.setToolTip(tooltip)
                param_layout.addWidget(param_label, ii, 0)
                widget_idx = 1
            if param_widget is not None:
                pw_lo = None
                if hasattr(param_widget, 'flush_btn') or hasattr(param_widget, 'path_select_btn') or reset_btn is not None:
                    pw_lo = QHBoxLayout()
                    pw_lo.addWidget(param_widget)
                if hasattr(param_widget, 'flush_btn'):
                    pw_lo.addWidget(param_widget.flush_btn)
                    param_widget.flushbtn_clicked.connect(self.on_flushbtn_clicked)
                if hasattr(param_widget, 'path_select_btn'):
                    pw_lo.addWidget(param_widget.path_select_btn)
                    param_widget.pathbtn_clicked.connect(self.on_pathbtn_clicked)
                if reset_btn is not None:
                    pw_lo.addWidget(reset_btn)
                if pw_lo is None:
                    param_layout.addWidget(param_widget, ii, widget_idx)
                else:
                    param_layout.addLayout(pw_lo, ii, widget_idx)
            else:
                v = params[param_key]
                raise ValueError(f"Failed to initialize widget for key-value pair: {param_key}-{v}")
            
    def on_flushbtn_clicked(self):
        paramw: ParamComboBox = self.sender()
        content_dict = {'content': '', 'widget': paramw, 'flush': True}
        self.paramwidget_edited.emit(paramw.param_key, content_dict)

    def on_pathbtn_clicked(self):
        paramw: ParamComboBox = self.sender()
        content_dict = {'content': '', 'widget': paramw, 'select_path': True}
        self.paramwidget_edited.emit(paramw.param_key, content_dict)

    def on_resetbtn_clicked(self, param_widget, param_key: str, value):
        param_widget.setText(value)
        content_dict = {'content': value}
        self.paramwidget_edited.emit(param_key, content_dict)

    def on_paramwidget_edited(self, param_key, param_content):
        content_dict = {'content': param_content}
        self.paramwidget_edited.emit(param_key, content_dict)

class ModuleParseWidgets(QWidget):
    def addModulesParamWidgets(self, ocr_instance):
        self.params = ocr_instance.get_params()
        self.on_module_changed()

    def on_module_changed(self):
        self.updateModuleParamWidget()

    def updateModuleParamWidget(self):
        widget = ParamWidget(self.params, scrollWidget=self)
        layout = QVBoxLayout()
        layout.addWidget(widget)
        self.setLayout(layout)

class ModuleConfigParseWidget(QWidget):
    module_changed = Signal(str)
    paramwidget_edited = Signal(str, dict)
    def __init__(self, module_name: str, get_valid_module_keys: Callable, scrollWidget: QWidget, add_from: int = 1, module_config_key: str = '', *args, **kwargs) -> None:
        super().__init__( *args, **kwargs)
        self.get_valid_module_keys = get_valid_module_keys
        self.module_config_key = module_config_key
        self.module_combobox = ConfigComboBox(scrollWidget=scrollWidget)
        self.params_layout = QHBoxLayout()
        self.params_layout.setContentsMargins(0, 0, 0, 0)

        p_layout = QHBoxLayout()
        p_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.module_label = ParamNameLabel(module_name)
        module_tooltip = self.tr('Select which module implementation is used for this step. Different modules can be much faster or slower depending on CPU/GPU support, model size, and network/API latency.')
        self.module_label.setToolTip(module_tooltip)
        self.module_combobox.setToolTip(module_tooltip)
        p_layout.addWidget(self.module_label)
        p_layout.addWidget(self.module_combobox)
        p_layout.addStretch(-1)
        self.p_layout = p_layout

        layout = QVBoxLayout(self)
        self.param_widget_map = {}
        layout.addLayout(p_layout) 
        layout.addLayout(self.params_layout)
        layout.setSpacing(30)
        self.vlayout = layout

        self.visibleWidget: QWidget = None
        self.module_dict: dict = {}

    def addModulesParamWidgets(self, module_dict: dict, current_module: str = None):
        invalid_module_keys = []
        valid_modulekeys = self.get_valid_module_keys()

        num_widgets_before = len(self.param_widget_map)

        for module in module_dict:
            if module not in valid_modulekeys:
                invalid_module_keys.append(module)
                continue

            if module in self.param_widget_map:
                LOGGER.warning(f'duplicated module key: {module}')
                continue

            self.module_combobox.addItem(module)
            params = module_dict[module]
            if params is not None:
                self.param_widget_map[module] = None

        if len(invalid_module_keys) > 0:
            LOGGER.warning(F'Invalid module keys: {invalid_module_keys}')
            for ik in invalid_module_keys:
                module_dict.pop(ik)

        self.module_dict = module_dict

        num_widgets_after = len(self.param_widget_map)
        if num_widgets_before == 0 and num_widgets_after > 0:
            if current_module in self.param_widget_map:
                self.module_combobox.setCurrentText(current_module)
            self.on_module_changed()
            self.module_combobox.currentTextChanged.connect(self.on_module_changed)

    def setModule(self, module: str):
        self.blockSignals(True)
        self.module_combobox.setCurrentText(module)
        self.updateModuleParamWidget()
        self.blockSignals(False)

    def updateModuleParamWidget(self):
        module = self.module_combobox.currentText()
        if self.visibleWidget is not None:
            self.visibleWidget.hide()
        if module in self.param_widget_map:
            widget: QWidget = self.param_widget_map[module]
            if widget is None:
                # lazy load widgets
                params = self.module_dict[module]
                widget = ParamWidget(params, scrollWidget=self, module_config_key=self.module_config_key, module_name=module)
                widget.paramwidget_edited.connect(self.paramwidget_edited)
                self.param_widget_map[module] = widget
                self.params_layout.addWidget(widget)
            else:
                widget.show()
            self.visibleWidget = widget

    def on_module_changed(self):
        self.updateModuleParamWidget()
        self.module_changed.emit(self.module_combobox.currentText())


class TranslatorConfigPanel(ModuleConfigParseWidget):

    show_pre_MT_keyword_window = Signal()
    show_MT_keyword_window = Signal()
    show_OCR_keyword_window = Signal()

    def __init__(self, module_name, scrollWidget: QWidget = None, *args, **kwargs) -> None:
        super().__init__(module_name, GET_VALID_TRANSLATORS, scrollWidget=scrollWidget, module_config_key='translator_params', *args, **kwargs)
        self.translator_changed = self.module_changed
    
        self.source_combobox = ConfigComboBox(scrollWidget=scrollWidget)
        self.target_combobox = ConfigComboBox(scrollWidget=scrollWidget)
        self.source_combobox.setToolTip(self.tr('Language expected in the detected source text.'))
        self.target_combobox.setToolTip(self.tr('Language used for translated output.'))
        self.replacePreMTkeywordBtn = NoBorderPushBtn(self.tr("Keyword substitution for machine translation source text"), self)
        self.replacePreMTkeywordBtn.setToolTip(self.tr("Configure replacements that run before machine translation reads the source text."))
        self.replacePreMTkeywordBtn.clicked.connect(self.show_pre_MT_keyword_window)
        self.replacePreMTkeywordBtn.setFixedWidth(500)
        self.replaceMTkeywordBtn = NoBorderPushBtn(self.tr("Keyword substitution for machine translation"), self)
        self.replaceMTkeywordBtn.setToolTip(self.tr("Configure replacements that run on machine translation output."))
        self.replaceMTkeywordBtn.clicked.connect(self.show_MT_keyword_window)
        self.replaceMTkeywordBtn.setFixedWidth(500)
        self.replaceOCRkeywordBtn = NoBorderPushBtn(self.tr("Keyword substitution for source text"), self)
        self.replaceOCRkeywordBtn.setToolTip(self.tr("Configure replacements that run on OCR/source text before translation."))
        self.replaceOCRkeywordBtn.clicked.connect(self.show_OCR_keyword_window)
        self.replaceOCRkeywordBtn.setFixedWidth(500)
        self.translateByTextblockBox = ParamCheckerBox(self.tr('Translate each text block individually'))
        self.translateByTextblockBox.setToolTip(self.tr('Translate every detected text block as a separate request instead of batching them together. This can improve isolation for providers that struggle with batches, but it usually slows translation because it creates many more requests.'))
        self.translateByTextblockBox.name_label.setToolTip(self.translateByTextblockBox.toolTip())

        st_layout = QHBoxLayout()
        st_layout.setSpacing(15)
        st_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        st_layout.addWidget(ParamNameLabel(self.tr('Source')))
        st_layout.addWidget(self.source_combobox)
        st_layout.addWidget(ParamNameLabel(self.tr('Target')))
        st_layout.addWidget(self.target_combobox)
        
        self.vlayout.insertLayout(1, st_layout) 
        self.vlayout.addWidget(self.translateByTextblockBox)
        self.vlayout.addWidget(self.replaceOCRkeywordBtn)
        self.vlayout.addWidget(self.replacePreMTkeywordBtn)
        self.vlayout.addWidget(self.replaceMTkeywordBtn)

    def finishSetTranslator(self, translator: BaseTranslator):
        self.source_combobox.blockSignals(True)
        self.target_combobox.blockSignals(True)
        self.module_combobox.blockSignals(True)

        self.source_combobox.clear()
        self.target_combobox.clear()

        for lang in translator.supported_src_list:
            self.source_combobox.addItem(lang_display_label(lang), lang)
        for lang in translator.supported_tgt_list:
            self.target_combobox.addItem(lang_display_label(lang), lang)
        self.module_combobox.setCurrentText(translator.name)
        self.source_combobox.setCurrentText(lang_display_label(translator.lang_source))
        self.target_combobox.setCurrentText(lang_display_label(translator.lang_target))
        self.updateModuleParamWidget()
        self.source_combobox.blockSignals(False)
        self.target_combobox.blockSignals(False)
        self.module_combobox.blockSignals(False)


class InpaintConfigPanel(ModuleConfigParseWidget):
    def __init__(self, module_name: str, scrollWidget: QWidget = None, *args, **kwargs) -> None:
        super().__init__(module_name, GET_VALID_INPAINTERS, scrollWidget = scrollWidget, module_config_key='inpainter_params', *args, **kwargs)
        self.inpainter_changed = self.module_changed
        self.setInpainter = self.setModule
        self.needInpaintChecker = ParamCheckerBox(self.tr('Let the program decide whether it is necessary to use the selected inpaint method.'))
        self.needInpaintChecker.setToolTip(self.tr('When enabled, the app decides per region whether inpainting is needed before rendering translated text.'))
        self.needInpaintChecker.name_label.setToolTip(self.needInpaintChecker.toolTip())
        self.vlayout.addWidget(self.needInpaintChecker)
        self.filter_mask_by_bboxes_checker = QCheckBox(self.tr('Filter inpaint mask by text boxes'))
        self.filter_mask_by_bboxes_checker.setToolTip(self.tr('Limit the inpaint mask to detected text-box regions before running the inpainter.'))
        self.vlayout.addWidget(self.filter_mask_by_bboxes_checker)

    def showEvent(self, e) -> None:
        self.p_layout.insertWidget(1, self.module_combobox)
        super().showEvent(e)

    def hideEvent(self, e) -> None:
        self.p_layout.removeWidget(self.module_combobox)
        return super().hideEvent(e)

class TextDetectConfigPanel(ModuleConfigParseWidget):
    def __init__(self, module_name: str, scrollWidget: QWidget = None, *args, **kwargs) -> None:
        super().__init__(module_name, GET_VALID_TEXTDETECTORS, scrollWidget = scrollWidget, module_config_key='textdetector_params', *args, **kwargs)
        self.detector_changed = self.module_changed
        self.setDetector = self.setModule
        self.keep_existing_checker = QCheckBox(text=self.tr('Keep Existing Lines'))
        self.keep_existing_checker.setToolTip(self.tr('Keep manually edited or existing text lines instead of replacing them during detection.'))
        self.p_layout.insertWidget(2, self.keep_existing_checker)
        

class OCRConfigPanel(ModuleConfigParseWidget):
    def __init__(self, module_name: str, scrollWidget: QWidget = None, *args, **kwargs) -> None:
        super().__init__(module_name, GET_VALID_OCR, scrollWidget = scrollWidget, module_config_key='ocr_params', *args, **kwargs)
        self.ocr_changed = self.module_changed
        self.setOCR = self.setModule
        self.restoreEmptyOCRChecker = QCheckBox(self.tr("Delete and restore region where OCR return empty string."), self)
        self.restoreEmptyOCRChecker.setToolTip(self.tr("Remove OCR regions that return empty text and restore the underlying image area."))
        self.restoreEmptyOCRChecker.clicked.connect(self.on_restore_empty_ocr)
        self.vlayout.addWidget(self.restoreEmptyOCRChecker)
        # 字体检测选项
        self.fontDetectChecker = QCheckBox(self.tr("Font Detection"), self)
        self.fontDetectChecker.setToolTip(self.tr("Try to detect font properties from the source image for each OCR region."))
        self.fontDetectChecker.setChecked(pcfg.module.ocr_font_detect)
        self.fontDetectChecker.clicked.connect(self.on_fontdetect_changed)
        self.vlayout.addWidget(self.fontDetectChecker)

    def on_restore_empty_ocr(self):
        pcfg.restore_ocr_empty = self.restoreEmptyOCRChecker.isChecked()

    def on_fontdetect_changed(self):
        pcfg.module.ocr_font_detect = self.fontDetectChecker.isChecked()
