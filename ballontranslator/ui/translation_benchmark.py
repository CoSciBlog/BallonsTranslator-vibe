import copy
import json
import os
import os.path as osp
import time
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from qtpy.QtCore import Qt, QThread, Signal
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules import GET_VALID_TRANSLATORS, TRANSLATORS
from modules.translators.trans_llm_api import LLM_API_Translator, LLM_API_Translator_2
from modules.translators.trans_two_step import TwoStepTranslator
from utils.config import pcfg
from utils.logger import logger as LOGGER
from utils.shared import PROGRAM_PATH


BENCHMARK_CONFIG_PATH = osp.join(PROGRAM_PATH, "config", "translation_benchmark.json")
LLM_TRANSLATOR_KEYS = ["LLM_API_Translator", "LLM_API_Translator_2", "Two-Step Translator"]


@dataclass
class BenchmarkProfile:
    name: str = "LLM benchmark"
    translator: str = "LLM_API_Translator"
    provider: str = "Ollama"
    endpoint: str = "http://localhost:11434"
    model: str = ""
    translate_each_text_block: bool = False
    reasoning: bool = False
    temperature: float = 0.1
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    request_prompt: str = ""
    system_prompt: str = ""


@dataclass
class BenchmarkSettings:
    profiles: List[BenchmarkProfile] = field(default_factory=list)
    include_google: bool = True
    include_deepl: bool = True


def _param_value(params: Dict[str, Any], key: str, default=None):
    value = params.get(key, default)
    if isinstance(value, dict):
        return value.get("value", default)
    return value


def _set_param(params: Dict[str, Any], key: str, value: Any) -> None:
    current = params.get(key)
    if isinstance(current, dict):
        current["value"] = value
    else:
        params[key] = {"value": value}


def _default_params_for(translator_key: str) -> Dict[str, Any]:
    if translator_key == "Two-Step Translator":
        return copy.deepcopy(TwoStepTranslator.params)
    if translator_key == "LLM_API_Translator_2":
        return copy.deepcopy(LLM_API_Translator_2.params)
    return copy.deepcopy(LLM_API_Translator.params)


def _profile_from_current(translator_key: str = None) -> BenchmarkProfile:
    valid = GET_VALID_TRANSLATORS()
    translator_key = translator_key or pcfg.module.translator
    if translator_key not in LLM_TRANSLATOR_KEYS:
        translator_key = "LLM_API_Translator" if "LLM_API_Translator" in valid else LLM_TRANSLATOR_KEYS[0]
    params = copy.deepcopy(pcfg.module.translator_params.get(translator_key) or _default_params_for(translator_key))
    model = _param_value(params, "override model", "") or _param_value(params, "model", "")
    return BenchmarkProfile(
        name=f"{translator_key}: {model or 'current'}",
        translator=translator_key,
        provider=str(_param_value(params, "provider", "Ollama") or "Ollama"),
        endpoint=str(_param_value(params, "endpoint", "") or ""),
        model=str(model or ""),
        translate_each_text_block=bool(pcfg.module.translate_by_textblock),
        reasoning=bool(_param_value(params, "reasoning", False)),
        temperature=float(_param_value(params, "temperature", 0.1) or 0.1),
        top_p=float(_param_value(params, "top p", 1.0) or 1.0),
        frequency_penalty=float(_param_value(params, "frequency penalty", 0.0) or 0.0),
        presence_penalty=float(_param_value(params, "presence penalty", 0.0) or 0.0),
        request_prompt=str(_param_value(params, "request prompt", "") or ""),
        system_prompt=str(_param_value(params, "system_prompt", "") or ""),
    )


def load_benchmark_settings() -> BenchmarkSettings:
    if not osp.exists(BENCHMARK_CONFIG_PATH):
        return BenchmarkSettings(profiles=[_profile_from_current()])
    try:
        with open(BENCHMARK_CONFIG_PATH, "r", encoding="utf8") as fh:
            data = json.load(fh)
        profiles = [BenchmarkProfile(**profile) for profile in data.get("profiles", [])]
        return BenchmarkSettings(
            profiles=profiles or [_profile_from_current()],
            include_google=bool(data.get("include_google", True)),
            include_deepl=bool(data.get("include_deepl", True)),
        )
    except Exception:
        LOGGER.warning("Failed to load translation benchmark settings.", exc_info=True)
        return BenchmarkSettings(profiles=[_profile_from_current()])


def save_benchmark_settings(settings: BenchmarkSettings) -> None:
    os.makedirs(osp.dirname(BENCHMARK_CONFIG_PATH), exist_ok=True)
    with open(BENCHMARK_CONFIG_PATH, "w", encoding="utf8") as fh:
        json.dump(
            {
                "profiles": [asdict(profile) for profile in settings.profiles],
                "include_google": settings.include_google,
                "include_deepl": settings.include_deepl,
            },
            fh,
            ensure_ascii=False,
            indent=2,
        )


class BenchmarkProfileDialog(QDialog):
    def __init__(self, profile: BenchmarkProfile = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Benchmark Model"))
        self.setMinimumWidth(720)
        self.profile = copy.deepcopy(profile) if profile is not None else _profile_from_current()
        self._setup_ui()
        self._load_profile(self.profile)

    def _setup_ui(self) -> None:
        self.name_edit = QLineEdit()
        self.translator_combo = QComboBox()
        self.translator_combo.addItems([key for key in LLM_TRANSLATOR_KEYS if key in GET_VALID_TRANSLATORS()])
        self.provider_edit = QLineEdit()
        self.endpoint_edit = QLineEdit()
        self.model_edit = QLineEdit()
        self.each_block_checker = QCheckBox(self.tr("Translate each text block individually"))
        self.reasoning_checker = QCheckBox(self.tr("Reasoning"))

        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setDecimals(3)
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setDecimals(3)
        self.frequency_spin = QDoubleSpinBox()
        self.frequency_spin.setRange(-2.0, 2.0)
        self.frequency_spin.setSingleStep(0.1)
        self.frequency_spin.setDecimals(3)
        self.presence_spin = QDoubleSpinBox()
        self.presence_spin.setRange(-2.0, 2.0)
        self.presence_spin.setSingleStep(0.1)
        self.presence_spin.setDecimals(3)

        self.system_prompt_edit = QPlainTextEdit()
        self.system_prompt_edit.setMinimumHeight(130)
        self.request_prompt_edit = QPlainTextEdit()
        self.request_prompt_edit.setMinimumHeight(130)

        form = QFormLayout()
        form.addRow(self.tr("Name"), self.name_edit)
        form.addRow(self.tr("Translator"), self.translator_combo)
        form.addRow(self.tr("Provider"), self.provider_edit)
        form.addRow(self.tr("Endpoint"), self.endpoint_edit)
        form.addRow(self.tr("Model"), self.model_edit)
        form.addRow("", self.each_block_checker)
        form.addRow("", self.reasoning_checker)
        form.addRow(self.tr("Temperature"), self.temperature_spin)
        form.addRow(self.tr("Top p"), self.top_p_spin)
        form.addRow(self.tr("Frequency penalty"), self.frequency_spin)
        form.addRow(self.tr("Presence penalty"), self.presence_spin)
        form.addRow(self.tr("System prompt"), self.system_prompt_edit)
        form.addRow(self.tr("Request prompt"), self.request_prompt_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _load_profile(self, profile: BenchmarkProfile) -> None:
        self.name_edit.setText(profile.name)
        self.translator_combo.setCurrentText(profile.translator)
        self.provider_edit.setText(profile.provider)
        self.endpoint_edit.setText(profile.endpoint)
        self.model_edit.setText(profile.model)
        self.each_block_checker.setChecked(profile.translate_each_text_block)
        self.reasoning_checker.setChecked(profile.reasoning)
        self.temperature_spin.setValue(profile.temperature)
        self.top_p_spin.setValue(profile.top_p)
        self.frequency_spin.setValue(profile.frequency_penalty)
        self.presence_spin.setValue(profile.presence_penalty)
        self.system_prompt_edit.setPlainText(profile.system_prompt)
        self.request_prompt_edit.setPlainText(profile.request_prompt)

    def selected_profile(self) -> BenchmarkProfile:
        name = self.name_edit.text().strip()
        model = self.model_edit.text().strip()
        translator = self.translator_combo.currentText() or "LLM_API_Translator"
        return BenchmarkProfile(
            name=name or f"{translator}: {model or 'current'}",
            translator=translator,
            provider=self.provider_edit.text().strip() or "Ollama",
            endpoint=self.endpoint_edit.text().strip(),
            model=model,
            translate_each_text_block=self.each_block_checker.isChecked(),
            reasoning=self.reasoning_checker.isChecked(),
            temperature=self.temperature_spin.value(),
            top_p=self.top_p_spin.value(),
            frequency_penalty=self.frequency_spin.value(),
            presence_penalty=self.presence_spin.value(),
            request_prompt=self.request_prompt_edit.toPlainText(),
            system_prompt=self.system_prompt_edit.toPlainText(),
        )


class TranslationBenchmarkWorker(QThread):
    result_ready = Signal(int, str, list, float)
    error_ready = Signal(int, str, str)
    status_changed = Signal(str)
    finished_all = Signal()

    def __init__(
        self,
        source_texts: List[str],
        jobs: List[Dict[str, Any]],
        source_lang: str,
        target_lang: str,
        imgtrans_proj=None,
        page_key: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source_texts = source_texts
        self.jobs = jobs
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.imgtrans_proj = imgtrans_proj
        self.page_key = page_key

    def run(self) -> None:
        for column_idx, job in enumerate(self.jobs, start=2):
            if self.isInterruptionRequested():
                break
            label = job["label"]
            started = time.time()
            self.status_changed.emit(f"Running {label} ...")
            try:
                translated = self._translate_job(job)
                elapsed = time.time() - started
                self.result_ready.emit(column_idx, label, translated, elapsed)
            except Exception as exc:
                LOGGER.error(traceback.format_exc())
                self.error_ready.emit(column_idx, label, f"{type(exc).__name__}: {exc}")

        self.status_changed.emit("Benchmark finished.")
        self.finished_all.emit()

    def _translate_job(self, job: Dict[str, Any]) -> List[str]:
        translator_name = job["translator"]
        translator_cls = TRANSLATORS.module_dict[translator_name]
        params = copy.deepcopy(job.get("params") or {})
        translator = translator_cls(
            self.source_lang,
            self.target_lang,
            raise_unsupported_lang=False,
            **params,
        )
        if hasattr(translator, "set_project_glossary") and self.imgtrans_proj is not None:
            translator.set_project_glossary(getattr(self.imgtrans_proj, "glossary", {}))
        if hasattr(translator, "set_page_context"):
            translator.set_page_context(self.imgtrans_proj, self.page_key)

        try:
            return self._translate_texts(translator, bool(job.get("each_block", False)))
        finally:
            if hasattr(translator, "clear_page_context"):
                translator.clear_page_context()

    def _translate_texts(self, translator, each_block: bool) -> List[str]:
        outputs = ["" for _ in self.source_texts]
        non_empty = [(idx, text or "") for idx, text in enumerate(self.source_texts) if str(text or "").strip()]
        if each_block:
            for idx, text in non_empty:
                translated = translator.translate([text])
                if isinstance(translated, str):
                    translated = [translated]
                outputs[idx] = (translated or [""])[0] or ""
            return outputs

        translated = translator.translate([text for _idx, text in non_empty])
        if isinstance(translated, str):
            translated = [translated]
        for (idx, _text), result in zip(non_empty, translated or []):
            outputs[idx] = result or ""
        return outputs


class TranslationBenchmarkWindow(QDialog):
    def __init__(
        self,
        source_texts: List[str],
        current_translator: str,
        imgtrans_proj=None,
        page_key: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source_texts = source_texts
        self.current_translator = current_translator
        self.imgtrans_proj = imgtrans_proj
        self.page_key = page_key
        self.worker = None
        self.settings = load_benchmark_settings()

        self.setWindowTitle(self.tr("Translation Benchmark"))
        self.setMinimumSize(1180, 740)
        self._setup_ui()
        self.refresh_profile_list()

    def _setup_ui(self) -> None:
        self.page_label = QLabel(self.tr("Current page: {page}").format(page=self.page_key or "-"))
        self.status_label = QLabel(self.tr("Add benchmark models, choose baselines, and run the benchmark."))

        self.profile_list = QListWidget()
        self.profile_list.setMinimumWidth(320)
        self.profile_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.include_google_checker = QCheckBox(self.tr("Google baseline"))
        self.include_google_checker.setChecked(self.settings.include_google)
        self.include_google_checker.stateChanged.connect(self.save_settings_from_ui)
        self.include_deepl_checker = QCheckBox(self.tr("DeepL baseline"))
        self.include_deepl_checker.setChecked(self.settings.include_deepl)
        self.include_deepl_checker.stateChanged.connect(self.save_settings_from_ui)

        self.add_button = QPushButton(self.tr("Add Model"))
        self.add_button.clicked.connect(self.add_profile)
        self.edit_button = QPushButton(self.tr("Edit"))
        self.edit_button.clicked.connect(self.edit_profile)
        self.remove_button = QPushButton(self.tr("Remove"))
        self.remove_button.clicked.connect(self.remove_profile)
        self.duplicate_button = QPushButton(self.tr("Duplicate"))
        self.duplicate_button.clicked.connect(self.duplicate_profile)

        self.table = QTableWidget(len(self.source_texts), 2)
        self.table.setHorizontalHeaderLabels([self.tr("#"), self.tr("Source")])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        for row, text in enumerate(self.source_texts):
            number_item = QTableWidgetItem(str(row + 1))
            number_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, number_item)
            self.table.setItem(row, 1, QTableWidgetItem(text or ""))
        self.table.setColumnWidth(0, 48)
        self.table.setColumnWidth(1, 360)
        self.table.resizeRowsToContents()

        self.run_button = QPushButton(self.tr("Run Benchmark"))
        self.run_button.setToolTip(self.tr("Translate current-page source text with every configured benchmark model and enabled baseline."))
        self.run_button.clicked.connect(self.run_benchmark)
        self.close_button = QPushButton(self.tr("Close"))
        self.close_button.clicked.connect(self.close)

        profile_buttons = QHBoxLayout()
        profile_buttons.addWidget(self.add_button)
        profile_buttons.addWidget(self.edit_button)
        profile_buttons.addWidget(self.duplicate_button)
        profile_buttons.addWidget(self.remove_button)

        run_buttons = QHBoxLayout()
        run_buttons.addWidget(self.run_button)
        run_buttons.addStretch()
        run_buttons.addWidget(self.close_button)

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel(self.tr("Benchmark models")))
        left_layout.addWidget(self.profile_list)
        left_layout.addLayout(profile_buttons)
        left_layout.addWidget(QLabel(self.tr("Comparison baselines")))
        left_layout.addWidget(self.include_google_checker)
        left_layout.addWidget(self.include_deepl_checker)
        left_layout.addStretch()
        left_layout.addLayout(run_buttons)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        body = QHBoxLayout()
        body.addWidget(left_widget, 1)
        body.addWidget(self.table, 3)

        layout = QVBoxLayout(self)
        layout.addWidget(self.page_label)
        layout.addLayout(body)
        layout.addWidget(self.status_label)

    def refresh_profile_list(self) -> None:
        self.profile_list.clear()
        for profile in self.settings.profiles:
            item = QListWidgetItem(self.profile_label(profile))
            item.setToolTip(self.profile_tooltip(profile))
            self.profile_list.addItem(item)

    def profile_label(self, profile: BenchmarkProfile) -> str:
        block_mode = self.tr("per block") if profile.translate_each_text_block else self.tr("batch")
        reasoning = self.tr("reasoning") if profile.reasoning else self.tr("no reasoning")
        return f"{profile.name} | {profile.model or 'current model'} | {block_mode} | {reasoning}"

    def profile_tooltip(self, profile: BenchmarkProfile) -> str:
        return (
            f"{profile.translator}\n"
            f"provider={profile.provider}\nendpoint={profile.endpoint}\n"
            f"temperature={profile.temperature}, top_p={profile.top_p}, "
            f"frequency_penalty={profile.frequency_penalty}, presence_penalty={profile.presence_penalty}"
        )

    def selected_profile_index(self) -> int:
        row = self.profile_list.currentRow()
        return row if 0 <= row < len(self.settings.profiles) else -1

    def save_settings_from_ui(self) -> None:
        self.settings.include_google = self.include_google_checker.isChecked()
        self.settings.include_deepl = self.include_deepl_checker.isChecked()
        save_benchmark_settings(self.settings)

    def add_profile(self) -> None:
        dialog = BenchmarkProfileDialog(_profile_from_current(), self)
        if dialog.exec_():
            self.settings.profiles.append(dialog.selected_profile())
            self.save_settings_from_ui()
            self.refresh_profile_list()

    def edit_profile(self) -> None:
        idx = self.selected_profile_index()
        if idx < 0:
            return
        dialog = BenchmarkProfileDialog(self.settings.profiles[idx], self)
        if dialog.exec_():
            self.settings.profiles[idx] = dialog.selected_profile()
            self.save_settings_from_ui()
            self.refresh_profile_list()
            self.profile_list.setCurrentRow(idx)

    def duplicate_profile(self) -> None:
        idx = self.selected_profile_index()
        if idx < 0:
            return
        profile = copy.deepcopy(self.settings.profiles[idx])
        profile.name = f"{profile.name} copy"
        self.settings.profiles.append(profile)
        self.save_settings_from_ui()
        self.refresh_profile_list()
        self.profile_list.setCurrentRow(len(self.settings.profiles) - 1)

    def remove_profile(self) -> None:
        idx = self.selected_profile_index()
        if idx < 0:
            return
        del self.settings.profiles[idx]
        self.save_settings_from_ui()
        self.refresh_profile_list()

    def _params_for_profile(self, profile: BenchmarkProfile) -> Dict[str, Any]:
        params = copy.deepcopy(pcfg.module.translator_params.get(profile.translator) or _default_params_for(profile.translator))
        _set_param(params, "provider", profile.provider)
        _set_param(params, "endpoint", profile.endpoint)
        _set_param(params, "override model", profile.model)
        _set_param(params, "temperature", profile.temperature)
        _set_param(params, "top p", profile.top_p)
        _set_param(params, "frequency penalty", profile.frequency_penalty)
        _set_param(params, "presence penalty", profile.presence_penalty)
        _set_param(params, "reasoning", profile.reasoning)
        if profile.request_prompt:
            _set_param(params, "request prompt", profile.request_prompt)
        if profile.system_prompt:
            _set_param(params, "system_prompt", profile.system_prompt)
        return params

    def _benchmark_jobs(self) -> List[Dict[str, Any]]:
        jobs = []
        for profile in self.settings.profiles:
            jobs.append(
                {
                    "label": profile.name,
                    "translator": profile.translator,
                    "params": self._params_for_profile(profile),
                    "each_block": profile.translate_each_text_block,
                }
            )
        if self.include_google_checker.isChecked() and "google" in GET_VALID_TRANSLATORS():
            jobs.append(
                {
                    "label": self.tr("Google baseline"),
                    "translator": "google",
                    "params": copy.deepcopy(pcfg.module.translator_params.get("google", {})),
                    "each_block": False,
                }
            )
        if self.include_deepl_checker.isChecked() and "DeepL" in GET_VALID_TRANSLATORS():
            jobs.append(
                {
                    "label": self.tr("DeepL baseline"),
                    "translator": "DeepL",
                    "params": copy.deepcopy(pcfg.module.translator_params.get("DeepL", {})),
                    "each_block": False,
                }
            )
        return jobs

    def run_benchmark(self) -> None:
        self.save_settings_from_ui()
        jobs = self._benchmark_jobs()
        if not jobs:
            self.status_label.setText(self.tr("Add at least one benchmark model or enable a baseline."))
            return

        headers = [self.tr("#"), self.tr("Source")] + [job["label"] for job in jobs]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        for idx, _job in enumerate(jobs, start=2):
            self.table.setColumnWidth(idx, 300)
            for row in range(len(self.source_texts)):
                self.table.setItem(row, idx, QTableWidgetItem(self.tr("Queued")))

        self.run_button.setEnabled(False)
        self.worker = TranslationBenchmarkWorker(
            self.source_texts,
            jobs,
            pcfg.module.translate_source,
            pcfg.module.translate_target,
            self.imgtrans_proj,
            self.page_key,
            self,
        )
        self.worker.result_ready.connect(self.on_result_ready)
        self.worker.error_ready.connect(self.on_error_ready)
        self.worker.status_changed.connect(self.status_label.setText)
        self.worker.finished_all.connect(self.on_finished_all)
        self.worker.start()

    def on_result_ready(self, column_idx: int, label: str, translations: List[str], elapsed: float) -> None:
        self.table.setHorizontalHeaderItem(column_idx, QTableWidgetItem(f"{label} ({elapsed:.1f}s)"))
        for row, text in enumerate(translations):
            self.table.setItem(row, column_idx, QTableWidgetItem(text or ""))
        self.table.resizeRowsToContents()

    def on_error_ready(self, column_idx: int, label: str, message: str) -> None:
        self.table.setHorizontalHeaderItem(column_idx, QTableWidgetItem(f"{label} (error)"))
        for row in range(len(self.source_texts)):
            self.table.setItem(row, column_idx, QTableWidgetItem(message))

    def on_finished_all(self) -> None:
        self.run_button.setEnabled(True)
        self.worker = None

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(
                self,
                self.tr("Benchmark running"),
                self.tr("Benchmark is still running. Wait for it to finish before closing."),
            )
            event.ignore()
            return
        super().closeEvent(event)
