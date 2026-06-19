import copy
import time
import traceback
from typing import Dict, List

from qtpy.QtCore import Qt, QThread, Signal
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from benchmarks.llm_model_matrix import BenchmarkConfig, BenchmarkInput, run_benchmark_matrix
from modules import GET_VALID_TRANSLATORS, TRANSLATORS
from utils.config import pcfg
from utils.logger import logger as LOGGER


class TranslationBenchmarkWorker(QThread):
    result_ready = Signal(int, str, list, float)
    error_ready = Signal(int, str, str)
    status_changed = Signal(str)
    finished_all = Signal()

    def __init__(
        self,
        source_texts: List[str],
        translator_names: List[str],
        translator_params: Dict[str, dict],
        source_lang: str,
        target_lang: str,
        imgtrans_proj=None,
        page_key: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source_texts = source_texts
        self.translator_names = translator_names
        self.translator_params = translator_params
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.imgtrans_proj = imgtrans_proj
        self.page_key = page_key

    def run(self) -> None:
        for column_idx, translator_name in enumerate(self.translator_names, start=2):
            if self.isInterruptionRequested():
                break

            started = time.time()
            self.status_changed.emit(f"Running {translator_name} ...")
            try:
                translated = self._translate_with(translator_name)
                elapsed = time.time() - started
                self.result_ready.emit(column_idx, translator_name, translated, elapsed)
            except Exception as exc:
                LOGGER.error(traceback.format_exc())
                self.error_ready.emit(column_idx, translator_name, f"{type(exc).__name__}: {exc}")

        self.status_changed.emit("Benchmark finished.")
        self.finished_all.emit()

    def _translate_with(self, translator_name: str) -> List[str]:
        translator_cls = TRANSLATORS.module_dict[translator_name]
        params = copy.deepcopy(self.translator_params.get(translator_name, {}))
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

        outputs = ["" for _ in self.source_texts]
        non_empty_indices = []
        non_empty_texts = []
        for idx, text in enumerate(self.source_texts):
            text = text or ""
            if text.strip():
                non_empty_indices.append(idx)
                non_empty_texts.append(text)

        if non_empty_texts:
            translated = translator.translate(non_empty_texts)
            if isinstance(translated, str):
                translated = [translated]
            for idx, text in zip(non_empty_indices, translated):
                outputs[idx] = text or ""

        if hasattr(translator, "clear_page_context"):
            translator.clear_page_context()
        return outputs


class ModelMatrixBenchmarkWorker(QThread):
    status_changed = Signal(str)
    finished_paths = Signal(str, str, str, str)
    error_ready = Signal(str)

    def __init__(
        self,
        source_texts: List[str],
        config: BenchmarkConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source_texts = source_texts
        self.config = config

    def run(self) -> None:
        try:
            self.status_changed.emit("Running LLM model matrix benchmark ...")
            result = run_benchmark_matrix(
                BenchmarkInput(source_texts=self.source_texts),
                self.config,
            )
            self.finished_paths.emit(
                result.artifacts.json_path,
                result.artifacts.csv_path,
                result.artifacts.summary_path,
                result.summary,
            )
        except Exception as exc:
            LOGGER.error(traceback.format_exc())
            self.error_ready.emit(f"{type(exc).__name__}: {exc}")


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
        self.matrix_worker = None

        self.setWindowTitle(self.tr("Translation Benchmark"))
        self.setMinimumSize(1120, 720)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.page_label = QLabel(self.tr("Current page: {page}").format(page=self.page_key or "-"))
        self.status_label = QLabel(self.tr("Select translators and run the benchmark."))

        self.translator_list = QListWidget()
        self.translator_list.setMinimumWidth(240)
        self._populate_translators()

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
        self.table.setColumnWidth(1, 320)
        self.table.resizeRowsToContents()

        self.run_button = QPushButton(self.tr("Run Benchmark"))
        self.run_button.setToolTip(self.tr("Translate the current page with the selected translators and compare the results side by side."))
        self.run_button.clicked.connect(self.run_benchmark)

        self.matrix_models_edit = QPlainTextEdit()
        self.matrix_models_edit.setPlainText("translategemma:12b\ntranslategemma:27b\nqwen3.5:9b")
        self.matrix_models_edit.setFixedHeight(86)

        self.matrix_runs_spin = QSpinBox()
        self.matrix_runs_spin.setRange(1, 100)
        self.matrix_runs_spin.setValue(3)

        self.matrix_warmup_spin = QSpinBox()
        self.matrix_warmup_spin.setRange(0, 20)
        self.matrix_warmup_spin.setValue(0)

        self.matrix_provider_edit = QLineEdit("Ollama")
        self.matrix_endpoint_edit = QLineEdit("http://localhost:11434")

        self.matrix_max_tokens_spin = QSpinBox()
        self.matrix_max_tokens_spin.setRange(1, 200000)
        self.matrix_max_tokens_spin.setValue(4096)

        self.matrix_num_ctx_spin = QSpinBox()
        self.matrix_num_ctx_spin.setRange(0, 200000)
        self.matrix_num_ctx_spin.setValue(0)

        self.matrix_llm_checker = QCheckBox(self.tr("LLM"))
        self.matrix_llm_checker.setChecked(True)
        self.matrix_two_step_checker = QCheckBox(self.tr("Two-Step"))
        self.matrix_two_step_checker.setChecked(True)
        self.matrix_reasoning_checker = QCheckBox(self.tr("Reasoning"))
        self.matrix_json_mode_checker = QCheckBox(self.tr("JSON mode"))
        self.matrix_json_mode_checker.setChecked(True)

        self.matrix_button = QPushButton(self.tr("Run LLM Model Matrix"))
        self.matrix_button.setToolTip(self.tr("Run repeated LLM and Two-Step benchmarks for each listed model and export JSON, CSV, and summary files."))
        self.matrix_button.clicked.connect(self.run_model_matrix_benchmark)

        self.close_button = QPushButton(self.tr("Close"))
        self.close_button.clicked.connect(self.close)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.run_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel(self.tr("Translators")))
        left_layout.addWidget(self.translator_list)
        left_layout.addLayout(button_layout)
        left_layout.addWidget(QLabel(self.tr("LLM model matrix")))
        left_layout.addWidget(self.matrix_models_edit)
        matrix_type_layout = QHBoxLayout()
        matrix_type_layout.addWidget(self.matrix_llm_checker)
        matrix_type_layout.addWidget(self.matrix_two_step_checker)
        matrix_type_layout.addWidget(self.matrix_reasoning_checker)
        matrix_type_layout.addWidget(self.matrix_json_mode_checker)
        left_layout.addLayout(matrix_type_layout)
        matrix_runs_layout = QHBoxLayout()
        matrix_runs_layout.addWidget(QLabel(self.tr("Runs")))
        matrix_runs_layout.addWidget(self.matrix_runs_spin)
        matrix_runs_layout.addWidget(QLabel(self.tr("Warmup")))
        matrix_runs_layout.addWidget(self.matrix_warmup_spin)
        left_layout.addLayout(matrix_runs_layout)
        left_layout.addWidget(QLabel(self.tr("Provider")))
        left_layout.addWidget(self.matrix_provider_edit)
        left_layout.addWidget(QLabel(self.tr("Endpoint")))
        left_layout.addWidget(self.matrix_endpoint_edit)
        matrix_token_layout = QHBoxLayout()
        matrix_token_layout.addWidget(QLabel(self.tr("Max tokens")))
        matrix_token_layout.addWidget(self.matrix_max_tokens_spin)
        matrix_token_layout.addWidget(QLabel(self.tr("num_ctx")))
        matrix_token_layout.addWidget(self.matrix_num_ctx_spin)
        left_layout.addLayout(matrix_token_layout)
        left_layout.addWidget(self.matrix_button)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        layout = QVBoxLayout(self)
        layout.addWidget(self.page_label)
        layout.addWidget(splitter)
        layout.addWidget(self.status_label)

    def _populate_translators(self) -> None:
        preferred = [
            self.current_translator,
            "Two-Step Translator",
            "LLM_API_Translator_2",
            "LLM_API_Translator",
            "ChatGPT",
            "DeepL",
            "Google",
            "copy source",
        ]
        valid_translators = GET_VALID_TRANSLATORS()
        default_checked = []
        for name in preferred:
            if name in valid_translators and name not in default_checked:
                default_checked.append(name)
        if not default_checked and valid_translators:
            default_checked.append(valid_translators[0])

        for translator_name in valid_translators:
            item = QListWidgetItem(translator_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if translator_name in default_checked[:3] else Qt.CheckState.Unchecked
            )
            self.translator_list.addItem(item)

    def selected_translators(self) -> List[str]:
        selected = []
        for row in range(self.translator_list.count()):
            item = self.translator_list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected

    def run_benchmark(self) -> None:
        translator_names = self.selected_translators()
        if not translator_names:
            self.status_label.setText(self.tr("Select at least one translator."))
            return

        self.table.setColumnCount(2 + len(translator_names))
        self.table.setHorizontalHeaderLabels([self.tr("#"), self.tr("Source")] + translator_names)
        for idx, name in enumerate(translator_names, start=2):
            self.table.setColumnWidth(idx, 280)
            for row in range(len(self.source_texts)):
                self.table.setItem(row, idx, QTableWidgetItem(self.tr("Running ...")))

        self.run_button.setEnabled(False)
        self.worker = TranslationBenchmarkWorker(
            self.source_texts,
            translator_names,
            copy.deepcopy(pcfg.module.translator_params),
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

    def run_model_matrix_benchmark(self) -> None:
        models = [
            line.strip()
            for line in self.matrix_models_edit.toPlainText().replace(",", "\n").splitlines()
            if line.strip()
        ]
        if not models:
            self.status_label.setText(self.tr("Enter at least one model for the model matrix."))
            return

        translator_types = []
        if self.matrix_llm_checker.isChecked():
            translator_types.append("llm")
        if self.matrix_two_step_checker.isChecked():
            translator_types.append("two_step")
        if not translator_types:
            self.status_label.setText(self.tr("Select LLM, Two-Step, or both."))
            return

        num_ctx = self.matrix_num_ctx_spin.value()
        config = BenchmarkConfig(
            models=models,
            translator_types=translator_types,
            runs_per_model=self.matrix_runs_spin.value(),
            provider=self.matrix_provider_edit.text().strip() or "Ollama",
            endpoint=self.matrix_endpoint_edit.text().strip(),
            max_tokens=self.matrix_max_tokens_spin.value(),
            num_ctx=num_ctx if num_ctx > 0 else None,
            reasoning=self.matrix_reasoning_checker.isChecked(),
            json_mode=self.matrix_json_mode_checker.isChecked(),
            source_lang=pcfg.module.translate_source,
            target_lang=pcfg.module.translate_target,
            warmup_runs=self.matrix_warmup_spin.value(),
            base_translator_params=copy.deepcopy(pcfg.module.translator_params),
        )
        self.matrix_button.setEnabled(False)
        self.matrix_worker = ModelMatrixBenchmarkWorker(self.source_texts, config, self)
        self.matrix_worker.status_changed.connect(self.status_label.setText)
        self.matrix_worker.finished_paths.connect(self.on_model_matrix_finished)
        self.matrix_worker.error_ready.connect(self.on_model_matrix_error)
        self.matrix_worker.start()

    def on_result_ready(self, column_idx: int, translator_name: str, translations: List[str], elapsed: float) -> None:
        header = f"{translator_name} ({elapsed:.1f}s)"
        self.table.setHorizontalHeaderItem(column_idx, QTableWidgetItem(header))
        for row, text in enumerate(translations):
            self.table.setItem(row, column_idx, QTableWidgetItem(text or ""))
        self.table.resizeRowsToContents()

    def on_error_ready(self, column_idx: int, translator_name: str, message: str) -> None:
        header = f"{translator_name} (error)"
        self.table.setHorizontalHeaderItem(column_idx, QTableWidgetItem(header))
        for row in range(len(self.source_texts)):
            self.table.setItem(row, column_idx, QTableWidgetItem(message))

    def on_finished_all(self) -> None:
        self.run_button.setEnabled(True)
        self.worker = None

    def on_model_matrix_finished(self, json_path: str, csv_path: str, summary_path: str, summary: str) -> None:
        self.matrix_button.setEnabled(True)
        self.matrix_worker = None
        self.status_label.setText(
            self.tr("Model matrix benchmark saved: {summary_path}").format(summary_path=summary_path)
        )
        LOGGER.info("LLM model matrix benchmark summary:\n%s", summary)

    def on_model_matrix_error(self, message: str) -> None:
        self.matrix_button.setEnabled(True)
        self.matrix_worker = None
        self.status_label.setText(self.tr("Model matrix benchmark failed: {message}").format(message=message))

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.status_label.setText(self.tr("Benchmark is still running. Wait for it to finish before closing."))
            event.ignore()
            return
        if self.matrix_worker is not None and self.matrix_worker.isRunning():
            self.status_label.setText(self.tr("Model matrix benchmark is still running. Wait for it to finish before closing."))
            event.ignore()
            return
        super().closeEvent(event)
