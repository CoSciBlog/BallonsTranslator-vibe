from __future__ import annotations

import json
import threading
import time
import traceback
from typing import Dict, List, Optional, Sequence

from qtpy.QtCore import QIODevice, QSaveFile, QThread, Qt, Signal
from qtpy.QtGui import QCloseEvent
from qtpy.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ballontranslator.modules.exceptions import LLMRequestStopped
from ballontranslator.modules.translators.trans_llm import LLMTranslator
from ballontranslator.utils.config import pcfg
from ballontranslator.utils.io_utils import text_is_empty
from ballontranslator.utils.llm_profiles import (
    LLM_OCR_KEY,
    LLMProfile,
    resolve_api_key,
)
from ballontranslator.utils.logger import logger as LOGGER
from ballontranslator.utils.proj_imgtrans import ProjImgTrans
from ballontranslator.utils.translation_benchmark import (
    TranslationBenchmarkReport,
    TranslationBenchmarkRun,
    TranslationBenchmarkVariant,
    clone_project_for_benchmark,
    page_texts,
    save_benchmark_report,
)


class TranslationBenchmarkWorker(QThread):
    """Run shared detection/OCR and isolated LLM translations off the UI thread."""

    progress_changed = Signal(int, int, str)
    report_ready = Signal(object)
    benchmark_failed = Signal(str)

    def __init__(
        self,
        project: ProjImgTrans,
        pages: Sequence[str],
        variants: Sequence[TranslationBenchmarkVariant],
        text_detector,
        ocr,
        source_language: str,
        target_language: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.pages = list(pages)
        self.variants = list(variants)
        self.text_detector = text_detector
        self.ocr = ocr
        self.source_language = source_language
        self.target_language = target_language
        self.stop_event = threading.Event()

    def request_stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        try:
            self.report_ready.emit(self.execute())
        except LLMRequestStopped:
            # A transport may surface cancellation before the worker reaches a
            # regular stop checkpoint. Return no error dialog for user stops.
            if not self.stop_event.is_set():
                self.benchmark_failed.emit(traceback.format_exc())
        except Exception:
            self.benchmark_failed.emit(traceback.format_exc())

    def execute(self) -> TranslationBenchmarkReport:
        working_project = clone_project_for_benchmark(self.project)
        total_steps = len(self.pages) * (2 + len(self.variants))
        completed_steps = 0
        shared_start = time.perf_counter()

        for page in self.pages:
            self._check_stopped()
            image = working_project.read_img(page)
            if hasattr(self.text_detector, 'set_stop_event'):
                self.text_detector.set_stop_event(self.stop_event)
            _mask, blocks = self.text_detector.detect(image, working_project)
            working_project.pages[page] = blocks
            completed_steps += 1
            self.progress_changed.emit(
                completed_steps,
                total_steps,
                self.tr('Text detection: {page}').format(page=page),
            )

            self._check_stopped()
            if hasattr(self.ocr, 'set_stop_event'):
                self.ocr.set_stop_event(self.stop_event)
            if getattr(self.ocr, 'name', '') == LLM_OCR_KEY:
                result = self.ocr.run_ocr(image, blocks, full_page=True)
            else:
                result = self.ocr.run_ocr(image, blocks)
            if isinstance(result, list):
                blocks = result
            if pcfg.restore_ocr_empty:
                blocks = [
                    block for block in blocks
                    if not text_is_empty(block.get_text())
                ]
            working_project.pages[page] = blocks
            completed_steps += 1
            self.progress_changed.emit(
                completed_steps,
                total_steps,
                self.tr('OCR: {page}').format(page=page),
            )

        shared_duration = time.perf_counter() - shared_start
        frozen_pages = {
            page: working_project.pages[page] for page in self.pages
        }
        sources = page_texts(working_project, self.pages, 'source')
        runs: List[TranslationBenchmarkRun] = []
        cancelled = False

        for variant in self.variants:
            if self.stop_event.is_set():
                cancelled = True
                break
            run = TranslationBenchmarkRun(variant=variant)
            variant_project = clone_project_for_benchmark(
                working_project,
                frozen_pages,
            )
            translator = LLMTranslator(
                self.source_language,
                self.target_language,
                profile_override=variant.profile,
            )
            if hasattr(translator, 'set_stop_event'):
                translator.set_stop_event(self.stop_event)
            variant_start = time.perf_counter()
            try:
                for page in self.pages:
                    self._check_stopped()
                    blocks = variant_project.pages[page]
                    variant_project.begin_full_page_translation(page)
                    translator.translate_textblk_lst(
                        blocks,
                        project=variant_project,
                        page_key=page,
                        full_page=True,
                    )
                    translator.on_page_translation_finished(
                        variant_project,
                        page,
                    )
                    variant_project.mark_translation_finished(
                        page,
                        self.target_language,
                    )
                    completed_steps += 1
                    self.progress_changed.emit(
                        completed_steps,
                        total_steps,
                        self.tr('{variant}: {page}').format(
                            variant=variant.label,
                            page=page,
                        ),
                    )
            except LLMRequestStopped as error:
                if self.stop_event.is_set():
                    run.status = 'cancelled'
                    cancelled = True
                else:
                    run.status = 'failed'
                    run.error = _public_variant_error(error, variant.profile)
            except Exception as error:
                run.status = 'failed'
                run.error = _public_variant_error(error, variant.profile)
                LOGGER.exception(
                    'Translation benchmark variant failed: %s',
                    variant.label,
                )
            finally:
                run.translations = page_texts(
                    variant_project,
                    self.pages,
                    'translation',
                )
                run.duration_seconds = time.perf_counter() - variant_start
                runs.append(run)
            if cancelled:
                break

        return TranslationBenchmarkReport(
            pages=list(self.pages),
            sources=sources,
            source_language=self.source_language,
            target_language=self.target_language,
            text_detector=str(getattr(self.text_detector, 'name', '')),
            ocr=str(getattr(self.ocr, 'name', '')),
            detection_ocr_seconds=shared_duration,
            runs=runs,
            cancelled=cancelled,
        )

    def _check_stopped(self) -> None:
        if self.stop_event.is_set():
            raise LLMRequestStopped('Translation benchmark stopped.')


def _public_variant_error(error: Exception, profile: LLMProfile) -> str:
    """Format a useful exportable error while redacting the profile secret."""

    message = f'{type(error).__name__}: {error}'
    try:
        api_key = resolve_api_key(profile)
    except Exception:
        api_key = ''
    if api_key:
        message = message.replace(api_key, '[redacted]')
    return message


class TranslationBenchmarkDialog(QDialog):
    """Configure and inspect a non-destructive translation benchmark."""

    def __init__(self, project: ProjImgTrans, module_manager, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.module_manager = module_manager
        self.worker: Optional[TranslationBenchmarkWorker] = None
        self.report: Optional[TranslationBenchmarkReport] = None
        self._pending_report: Optional[TranslationBenchmarkReport] = None
        self._pending_error = ''
        self._preparing = False
        self._profiles: Dict[str, LLMProfile] = {
            profile.id: profile
            for profile in pcfg.module.llm_profiles
            if profile.support_text and profile.model
        }

        self.setWindowTitle(self.tr('Translation Benchmark'))
        self.setMinimumSize(900, 620)
        self.resize(1120, 760)
        layout = QVBoxLayout(self)

        intro = QLabel(self.tr(
            'Text detection and OCR run once. Every selected LLM profile then '
            'translates an isolated copy of the same OCR result; the open '
            'project and its translation history are not changed.'
        ), self)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel(self.tr('Pages'), self))
        self.scope_combo = QComboBox(self)
        self.scope_combo.addItem(self.tr('Current page'), 'current')
        self.scope_combo.addItem(self.tr('All non-ignored pages'), 'all')
        scope_row.addWidget(self.scope_combo)
        scope_row.addStretch()
        self.request_count = QLabel(self)
        scope_row.addWidget(self.request_count)
        layout.addLayout(scope_row)

        self.profile_table = QTableWidget(0, 5, self)
        self.profile_table.setHorizontalHeaderLabels([
            self.tr('Use'), self.tr('Profile'), self.tr('Backend'),
            self.tr('Model'), self.tr('Key settings'),
        ])
        self.profile_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.profile_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        header = self.profile_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._populate_profiles()
        self.profile_table.itemChanged.connect(self._update_start_state)
        self.scope_combo.currentIndexChanged.connect(self._update_start_state)
        layout.addWidget(self.profile_table, 1)

        profile_note = QLabel(self.tr(
            'Duplicate an LLM profile in Settings to compare another model, '
            'prompt, sampling value, review mode, or adjacent-page context.'
        ), self)
        profile_note.setWordWrap(True)
        layout.addWidget(profile_note)

        self.progress_label = QLabel('', self)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress_label.hide()
        self.progress.hide()
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress)

        self.results = QTabWidget(self)
        self.summary_table = QTableWidget(0, 5, self.results)
        self.summary_table.setHorizontalHeaderLabels([
            self.tr('Profile'), self.tr('Model'), self.tr('Status'),
            self.tr('Translation time'), self.tr('Error'),
        ])
        self.summary_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.summary_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.details_table = QTableWidget(0, 0, self.results)
        self.details_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.details_table.setWordWrap(True)
        self.results.addTab(self.summary_table, self.tr('Summary'))
        self.results.addTab(self.details_table, self.tr('Block comparison'))
        self.results.hide()
        layout.addWidget(self.results, 2)

        buttons = QHBoxLayout()
        self.start_button = QPushButton(self.tr('Start benchmark'), self)
        self.stop_button = QPushButton(self.tr('Stop'), self)
        self.export_json_button = QPushButton(self.tr('Export JSON...'), self)
        self.export_csv_button = QPushButton(self.tr('Export CSV...'), self)
        self.close_button = QPushButton(self.tr('Close'), self)
        self.start_button.clicked.connect(self._prepare_benchmark)
        self.stop_button.clicked.connect(self._stop_benchmark)
        self.export_json_button.clicked.connect(self._export_json)
        self.export_csv_button.clicked.connect(self._export_csv)
        self.close_button.clicked.connect(self.reject)
        self.stop_button.hide()
        self.export_json_button.setEnabled(False)
        self.export_csv_button.setEnabled(False)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        buttons.addWidget(self.export_json_button)
        buttons.addWidget(self.export_csv_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self._update_start_state()

    def _populate_profiles(self) -> None:
        profiles = list(self._profiles.values())
        profiles.sort(
            key=lambda profile: profile.id != pcfg.module.translator_llm_id
        )
        self.profile_table.setRowCount(len(profiles))
        for row, profile in enumerate(profiles):
            use_item = QTableWidgetItem('')
            use_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
            )
            use_item.setCheckState(
                Qt.CheckState.Checked if row < 2 else Qt.CheckState.Unchecked
            )
            use_item.setData(Qt.ItemDataRole.UserRole, profile.id)
            settings = self.tr(
                'Temp {temperature}, Top P {top_p}, Thinking {thinking}, '
                'Review {review}, Adjacent {adjacent}'
            ).format(
                temperature=profile.temperature,
                top_p=profile.top_p,
                thinking=profile.thinking_level,
                review='✓' if profile.review_translation else '—',
                adjacent='✓' if profile.use_adjacent_page_context else '—',
            )
            values = (
                profile.name or profile.id,
                profile.backend,
                profile.model,
                settings,
            )
            self.profile_table.setItem(row, 0, use_item)
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                if column == 4:
                    public_settings = (
                        TranslationBenchmarkVariant.from_profile(profile)
                        .public_settings()
                    )
                    item.setToolTip(json.dumps(
                        public_settings,
                        ensure_ascii=False,
                        indent=2,
                    ))
                self.profile_table.setItem(row, column, item)

    def selected_variants(self) -> List[TranslationBenchmarkVariant]:
        variants = []
        for row in range(self.profile_table.rowCount()):
            item = self.profile_table.item(row, 0)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            profile = self._profiles.get(str(item.data(Qt.ItemDataRole.UserRole)))
            if profile is not None:
                variants.append(TranslationBenchmarkVariant.from_profile(profile))
        return variants

    def selected_pages(self) -> List[str]:
        if self.scope_combo.currentData() == 'current':
            current = self.project.current_img
            return self.project.pipeline_pages([current]) if current else []
        return self.project.pipeline_pages()

    def _update_start_state(self, *_args) -> None:
        variants = self.selected_variants()
        pages = self.selected_pages()
        minimum_requests = len(variants) * len(pages)
        self.request_count.setText(
            self.tr('At least {count} LLM page request(s)').format(
                count=minimum_requests
            )
        )
        self.start_button.setEnabled(
            not self._preparing
            and self.worker is None
            and len(variants) >= 2
            and bool(pages)
        )

    def _prepare_benchmark(self) -> None:
        if len(self.selected_variants()) < 2 or not self.selected_pages():
            return
        self._preparing = True
        self._set_running_ui(True)
        self.progress_label.setText(self.tr('Preparing text detector and OCR...'))
        self.module_manager.prepareTranslationBenchmark(
            self._start_worker,
            self._preparation_failed,
        )

    def _start_worker(self) -> None:
        self._preparing = False
        pages = self.selected_pages()
        variants = self.selected_variants()
        if not pages or len(variants) < 2:
            self._preparation_failed()
            return
        self.report = None
        self._pending_report = None
        self._pending_error = ''
        self.results.hide()
        self.export_json_button.setEnabled(False)
        self.export_csv_button.setEnabled(False)
        self.worker = TranslationBenchmarkWorker(
            self.project,
            pages,
            variants,
            self.module_manager.textdetector,
            self.module_manager.ocr,
            pcfg.module.translate_source,
            pcfg.module.translate_target,
            self,
        )
        self.worker.progress_changed.connect(self._update_progress)
        self.worker.report_ready.connect(self._store_report)
        self.worker.benchmark_failed.connect(self._store_error)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _preparation_failed(self) -> None:
        self._preparing = False
        self._set_running_ui(False)
        self.progress_label.setText(self.tr('Module preparation was cancelled or failed.'))
        self.progress_label.setVisible(True)
        self._update_start_state()

    def _set_running_ui(self, running: bool) -> None:
        self.profile_table.setEnabled(not running)
        self.scope_combo.setEnabled(not running)
        self.start_button.setVisible(not running)
        self.stop_button.setVisible(running)
        self.stop_button.setEnabled(running)
        self.close_button.setEnabled(not running)
        self.progress_label.setVisible(running)
        self.progress.setVisible(running)
        if not running:
            self._update_start_state()

    def _update_progress(self, completed: int, total: int, message: str) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(completed)
        self.progress_label.setText(message)

    def _store_report(self, report: TranslationBenchmarkReport) -> None:
        self._pending_report = report

    def _store_error(self, error: str) -> None:
        self._pending_error = error

    def _worker_finished(self) -> None:
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        self._set_running_ui(False)
        if self._pending_error:
            self.progress_label.setText(self.tr('Benchmark failed.'))
            QMessageBox.critical(
                self,
                self.tr('Translation Benchmark'),
                self.tr('The benchmark could not be completed.\n\n{error}').format(
                    error=self._pending_error
                ),
            )
            return
        if self._pending_report is None:
            self.progress_label.setText(self.tr('Benchmark stopped.'))
            self.progress_label.setVisible(True)
            return
        self.report = self._pending_report
        self._render_report()
        self.progress_label.setVisible(True)
        status = (
            self.tr('Benchmark stopped; partial results are shown.')
            if self.report.cancelled
            else self.tr('Benchmark completed.')
        )
        try:
            saved_path = save_benchmark_report(self.project.directory, self.report)
        except Exception as exc:
            LOGGER.exception('Failed to save translation benchmark report')
            self.progress_label.setText(status)
            QMessageBox.warning(
                self,
                self.tr('Translation Benchmark'),
                self.tr(
                    'The benchmark results could not be saved automatically '
                    'in the project folder.\n\n{error}'
                ).format(error=exc),
            )
        else:
            self.progress_label.setText(
                f'{status}\n'
                + self.tr('Saved automatically to:\n{path}').format(
                    path=saved_path,
                )
            )
        self.export_json_button.setEnabled(True)
        self.export_csv_button.setEnabled(True)

    def _render_report(self) -> None:
        report = self.report
        if report is None:
            return
        self.summary_table.setRowCount(len(report.runs) + 1)
        shared_values = (
            self.tr('Shared detection + OCR'),
            f'{report.text_detector} / {report.ocr}',
            self.tr('Completed'),
            f'{report.detection_ocr_seconds:.2f} s',
            '',
        )
        for column, value in enumerate(shared_values):
            self.summary_table.setItem(0, column, QTableWidgetItem(value))
        for row, run in enumerate(report.runs, start=1):
            values = (
                run.variant.label,
                run.variant.model,
                self._status_label(run.status),
                f'{run.duration_seconds:.2f} s',
                self._last_error_line(run.error),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 4 and run.error:
                    item.setToolTip(run.error)
                self.summary_table.setItem(row, column, item)

        self.details_table.clear()
        self.details_table.setColumnCount(3 + len(report.runs))
        self.details_table.setHorizontalHeaderLabels(
            [self.tr('Page'), self.tr('Block'), self.tr('Source')]
            + [run.variant.label for run in report.runs]
        )
        row_count = sum(len(report.sources.get(page, [])) for page in report.pages)
        self.details_table.setRowCount(row_count)
        row = 0
        for page in report.pages:
            for block_index, source in enumerate(report.sources.get(page, [])):
                base_values = (page, str(block_index + 1), source)
                for column, value in enumerate(base_values):
                    self.details_table.setItem(row, column, QTableWidgetItem(value))
                for offset, run in enumerate(report.runs, start=3):
                    translations = run.translations.get(page, [])
                    translation = (
                        translations[block_index]
                        if block_index < len(translations)
                        else ''
                    )
                    self.details_table.setItem(
                        row,
                        offset,
                        QTableWidgetItem(translation),
                    )
                row += 1
        detail_header = self.details_table.horizontalHeader()
        detail_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        detail_header.setStretchLastSection(True)
        self.details_table.resizeRowsToContents()
        self.results.show()

    def _status_label(self, status: str) -> str:
        return {
            'completed': self.tr('Completed'),
            'failed': self.tr('Failed'),
            'cancelled': self.tr('Cancelled'),
        }.get(status, status)

    @staticmethod
    def _last_error_line(error: str) -> str:
        lines = [line.strip() for line in error.splitlines() if line.strip()]
        return lines[-1] if lines else ''

    def _stop_benchmark(self) -> None:
        self.stop_button.setEnabled(False)
        self.progress_label.setText(self.tr('Stopping benchmark...'))
        if self._preparing:
            self.module_manager.cancelModulePreparation()
        elif self.worker is not None:
            self.worker.request_stop()

    def _export_json(self) -> None:
        if self.report is None:
            return
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            self.tr('Export benchmark JSON'),
            'translation-benchmark.json',
            self.tr('JSON files (*.json)'),
        )
        if filename:
            self._write_export(
                filename,
                json.dumps(self.report.to_dict(), ensure_ascii=False, indent=2),
            )

    def _export_csv(self) -> None:
        if self.report is None:
            return
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            self.tr('Export benchmark CSV'),
            'translation-benchmark.csv',
            self.tr('CSV files (*.csv)'),
        )
        if filename:
            self._write_export(filename, self.report.to_csv())

    def _write_export(self, filename: str, content: str) -> None:
        output = QSaveFile(filename)
        open_mode = getattr(getattr(QIODevice, 'OpenModeFlag', QIODevice), 'WriteOnly')
        if not output.open(open_mode):
            QMessageBox.warning(
                self,
                self.tr('Translation Benchmark'),
                self.tr('The benchmark export could not be opened for writing.'),
            )
            return
        output.write(content.encode('utf-8-sig'))
        if not output.commit():
            QMessageBox.warning(
                self,
                self.tr('Translation Benchmark'),
                self.tr('The benchmark export could not be saved.'),
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._preparing or self.worker is not None:
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        # Escape and the title-bar close action must not destroy an active
        # worker. Cancellation remains explicit through the Stop button.
        if self._preparing or self.worker is not None:
            return
        super().reject()
