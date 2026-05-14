import copy
import time
import traceback
from typing import Dict, List

from qtpy.QtCore import Qt, QThread, Signal
from qtpy.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

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

        self.setWindowTitle(self.tr("Translation Benchmark"))
        self.setMinimumSize(980, 620)
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

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.status_label.setText(self.tr("Benchmark is still running. Wait for it to finish before closing."))
            event.ignore()
            return
        super().closeEvent(event)
