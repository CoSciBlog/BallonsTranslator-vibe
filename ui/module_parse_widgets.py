import json
from typing import List, Callable

from modules import GET_VALID_INPAINTERS, GET_VALID_TEXTDETECTORS, GET_VALID_TRANSLATORS, GET_VALID_OCR, \
    BaseTranslator, DEFAULT_DEVICE, GPUINTENSIVE_SET
from modules.translators.base import lang_display_label
from utils.logger import logger as LOGGER
from .custom_widget import ConfigComboBox, ParamComboBox, NoBorderPushBtn, ParamNameLabel
from .tooltip_utils import wrap_tooltip
from utils.shared import CONFIG_COMBOBOX_LONG, size2width, CONFIG_COMBOBOX_SHORT, CONFIG_COMBOBOX_HEIGHT
from utils.config import pcfg, sample_module_param_value
from utils.ollama import OLLAMA_DEFAULT_ENDPOINT, ollama_tags_endpoint

from qtpy.QtWidgets import QPlainTextEdit, QHBoxLayout, QVBoxLayout, QWidget, QLabel, QCheckBox, QLineEdit, QGridLayout, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QComboBox, QAbstractItemView, QHeaderView
from qtpy.QtCore import Qt, Signal, QUrl, QTimer
from qtpy.QtGui import QDoubleValidator
from qtpy.QtNetwork import QNetworkAccessManager, QNetworkRequest


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


class OllamaModelManager(QWidget):
    paramwidget_edited = Signal(str, dict)
    model_selected = Signal(str)

    def __init__(self, param_key: str, preferences: dict, parent=None):
        super().__init__(parent)
        self.param_key = param_key
        self.preferences = self._normalize_preferences(preferences)
        self.endpoint_getter = lambda: OLLAMA_DEFAULT_ENDPOINT
        self.provider_getter = lambda: ''
        self._updating = False
        self._reply = None
        self.network_manager = QNetworkAccessManager(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(8)
        title = ParamNameLabel(self.tr('Installed Ollama models'))
        title.setToolTip(self.tr(
            'Queries the configured Ollama server. Favorites and ratings are saved '
            'separately for this translator profile.'
        ))
        layout.addWidget(title)

        actions = QHBoxLayout()
        self.refresh_button = QPushButton(self.tr('Refresh models'))
        self.use_button = QPushButton(self.tr('Use selected model'))
        self.status_label = QLabel()
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.use_button)
        actions.addWidget(self.status_label, 1)
        layout.addLayout(actions)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([
            self.tr('Favorite'), self.tr('Model'), self.tr('Rating')
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(190)
        self.table.setMinimumWidth(CONFIG_FIELD_WIDE)
        layout.addWidget(self.table)

        self.refresh_button.clicked.connect(self.refresh_models)
        self.use_button.clicked.connect(self.use_selected_model)
        self.table.doubleClicked.connect(lambda _index: self.use_selected_model())
        self._update_availability()

    @staticmethod
    def _normalize_preferences(preferences) -> dict:
        if not isinstance(preferences, dict):
            return {}
        normalized = {}
        for model, values in preferences.items():
            if not isinstance(values, dict):
                values = {}
            try:
                rating = max(1, min(5, int(values.get('rating', 3))))
            except (TypeError, ValueError):
                rating = 3
            normalized[str(model)] = {
                'favorite': bool(values.get('favorite', False)),
                'rating': rating,
            }
        return normalized

    def configure(self, endpoint_getter, provider_getter):
        self.endpoint_getter = endpoint_getter
        self.provider_getter = provider_getter
        self._update_availability()
        if (
            str(self.provider_getter()).casefold() == 'ollama'
            and self.table.rowCount() == 0
        ):
            QTimer.singleShot(0, self.refresh_models)

    def _update_availability(self):
        enabled = str(self.provider_getter()).casefold() == 'ollama'
        self.refresh_button.setEnabled(enabled and self._reply is None)
        self.use_button.setEnabled(enabled and self.table.rowCount() > 0)
        if not enabled:
            self.status_label.setText(self.tr('Select Ollama as provider.'))
        elif self.table.rowCount() == 0 and self._reply is None:
            self.status_label.setText(self.tr('Refresh to query installed models.'))

    def refresh_models(self):
        if str(self.provider_getter()).casefold() != 'ollama' or self._reply is not None:
            return
        self.status_label.setText(self.tr('Querying Ollama...'))
        self.refresh_button.setEnabled(False)
        self._reply = self.network_manager.get(
            QNetworkRequest(QUrl(ollama_tags_endpoint(self.endpoint_getter())))
        )
        timer = QTimer(self._reply)
        timer.setSingleShot(True)
        timer.timeout.connect(self._reply.abort)
        timer.start(8000)
        self._reply.finished.connect(self._on_models_finished)

    def _on_models_finished(self):
        reply = self._reply
        self._reply = None
        try:
            payload = json.loads(bytes(reply.readAll()).decode('utf-8'))
            if not isinstance(payload, dict) or not isinstance(payload.get('models'), list):
                raise ValueError('Invalid Ollama /api/tags response')
            models = payload['models']
            names = sorted({
                str(model.get('name') or model.get('model')).strip()
                for model in models
                if isinstance(model, dict) and (model.get('name') or model.get('model'))
            })
            self._set_models(names)
            self.status_label.setText(self.tr('%d installed model(s).') % len(names))
        except Exception as error:
            detail = reply.errorString()
            if not detail or detail == 'Unknown error':
                detail = str(error)
            self.status_label.setText(self.tr('Ollama query failed: ') + detail)
        finally:
            reply.deleteLater()
            self._update_availability()

    def _set_models(self, names):
        for name in names:
            self.preferences.setdefault(name, {'favorite': False, 'rating': 3})
        ordered = sorted(
            names,
            key=lambda name: (
                not self.preferences[name]['favorite'],
                -self.preferences[name]['rating'],
                name.casefold(),
            ),
        )
        self._updating = True
        self.table.setRowCount(len(ordered))
        for row, name in enumerate(ordered):
            favorite = QCheckBox()
            favorite.setChecked(self.preferences[name]['favorite'])
            favorite.stateChanged.connect(
                lambda _state, model=name, checkbox=favorite:
                self._set_favorite(model, checkbox.isChecked())
            )
            container = QWidget()
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            container_layout.addWidget(favorite)
            self.table.setCellWidget(row, 0, container)
            self.table.setItem(row, 1, QTableWidgetItem(name))

            rating = QComboBox()
            rating.addItems(['1', '2', '3', '4', '5'])
            rating.setCurrentText(str(self.preferences[name]['rating']))
            rating.currentTextChanged.connect(
                lambda value, model=name: self._set_rating(model, value)
            )
            self.table.setCellWidget(row, 2, rating)
        self._updating = False
        if ordered:
            self.table.selectRow(0)
        self.paramwidget_edited.emit(self.param_key, dict(self.preferences))

    def _set_favorite(self, model: str, favorite: bool):
        if self._updating:
            return
        self.preferences[model]['favorite'] = bool(favorite)
        self.paramwidget_edited.emit(self.param_key, dict(self.preferences))

    def _set_rating(self, model: str, rating):
        if self._updating:
            return
        self.preferences[model]['rating'] = max(1, min(5, int(rating)))
        self.paramwidget_edited.emit(self.param_key, dict(self.preferences))

    def use_selected_model(self):
        row = self.table.currentRow()
        item = self.table.item(row, 1) if row >= 0 else None
        if item is not None:
            self.model_selected.emit(item.text())


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
        self.param_widget_map = {}
        self.ollama_model_manager = None

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

                elif param_type == 'ollama_models':
                    param_widget = OllamaModelManager(param_key, value)
                    self.ollama_model_manager = param_widget
                    require_label = False

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
                self.param_widget_map[param_key] = param_widget
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

        if self.ollama_model_manager is not None:
            provider_widget = self.param_widget_map.get('provider')
            endpoint_widget = self.param_widget_map.get('endpoint')
            model_widget = self.param_widget_map.get('model')
            override_widget = self.param_widget_map.get('override model')
            endpoint_value = endpoint_widget.text().strip() if endpoint_widget is not None else ''
            if (
                endpoint_widget is not None
                and provider_widget is not None
                and provider_widget.currentText().casefold() == 'ollama'
                and endpoint_value.rstrip('/') in {
                    '',
                    'http://localhost:11434',
                    'http://localhost:11434/v1',
                }
            ):
                endpoint_widget.setText(OLLAMA_DEFAULT_ENDPOINT)
                params['endpoint']['value'] = OLLAMA_DEFAULT_ENDPOINT
            self.ollama_model_manager.configure(
                endpoint_getter=lambda: endpoint_widget.text().strip()
                if endpoint_widget is not None else OLLAMA_DEFAULT_ENDPOINT,
                provider_getter=lambda: provider_widget.currentText()
                if provider_widget is not None else '',
            )
            if provider_widget is not None:
                provider_widget.currentTextChanged.connect(
                    lambda value: self._on_llm_provider_changed(
                        value, endpoint_widget
                    )
                )
            if model_widget is not None and override_widget is not None:
                self.ollama_model_manager.model_selected.connect(
                    lambda model: self._select_ollama_model(
                        model_widget, override_widget, model
                    )
                )

    @staticmethod
    def _select_ollama_model(model_widget, override_widget, model: str):
        model_widget.setCurrentText('OLLAMA: (override model field)')
        override_widget.setText(model)

    def _on_llm_provider_changed(self, provider: str, endpoint_widget):
        if (
            provider.casefold() == 'ollama'
            and endpoint_widget is not None
            and endpoint_widget.text().strip().rstrip('/') in {
                '',
                'http://localhost:11434',
                'http://localhost:11434/v1',
            }
        ):
            endpoint_widget.setText(OLLAMA_DEFAULT_ENDPOINT)
        self.ollama_model_manager._update_availability()
        if (
            provider.casefold() == 'ollama'
            and self.ollama_model_manager.table.rowCount() == 0
        ):
            QTimer.singleShot(0, self.ollama_model_manager.refresh_models)
            
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

    def addModulesParamWidgets(self, module_dict: dict):
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
