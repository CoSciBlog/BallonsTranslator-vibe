from __future__ import annotations

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ballontranslator.utils.translation_benchmark import TranslationBenchmarkReport


class TranslationBenchmarkResultsWidget(QWidget):
    """Select one completed benchmark variant for the live editor preview."""

    preview_requested = Signal(int)
    project_translation_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('BenchmarkResultsPanel')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        title = QLabel(self.tr('Benchmark results'), self)
        title.setObjectName('BenchmarkResultsTitle')
        description = QLabel(
            self.tr('Select an LLM model to preview its translation.'),
            self,
        )
        description.setObjectName('BenchmarkResultsDescription')
        description.setWordWrap(True)

        self.results_list = QListWidget(self)
        self.results_list.setObjectName('BenchmarkResultsList')
        self.results_list.setSelectionMode(
            QListWidget.SelectionMode.SingleSelection
        )
        self.results_list.currentRowChanged.connect(self._selection_changed)

        self.page_status = QLabel(self)
        self.page_status.setObjectName('BenchmarkResultsPageStatus')
        self.page_status.setWordWrap(True)

        self.project_translation_button = QPushButton(
            self.tr('Show project translation'),
            self,
        )
        self.project_translation_button.setToolTip(self.tr(
            'Stop the benchmark preview and return to the editable translation.'
        ))
        self.project_translation_button.clicked.connect(
            self.project_translation_requested.emit
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(self.results_list, 1)
        layout.addWidget(self.page_status)
        layout.addWidget(self.project_translation_button)

    def set_report(
        self,
        report: TranslationBenchmarkReport,
        selected_run_index: int = 0,
    ) -> bool:
        """List runs with preview data and select an original report index."""

        self.results_list.blockSignals(True)
        self.results_list.clear()
        selected_row = -1
        for run_index, run in enumerate(report.runs):
            if not run.preview_pages:
                continue
            profile_name = run.variant.profile.name or run.variant.id or self.tr(
                'LLM profile'
            )
            model = run.variant.model or self.tr('Unknown model')
            item = QListWidgetItem(f'{profile_name}\n{model}')
            item.setData(Qt.ItemDataRole.UserRole, run_index)
            item.setToolTip(self.tr(
                'Profile: {profile}\nModel: {model}\nStatus: {status}'
            ).format(
                profile=profile_name,
                model=model,
                status=run.status,
            ))
            self.results_list.addItem(item)
            if run_index == selected_run_index:
                selected_row = self.results_list.count() - 1

        if self.results_list.count():
            self.results_list.setCurrentRow(
                selected_row if selected_row >= 0 else 0
            )
        self.results_list.blockSignals(False)
        if not self.results_list.count():
            self.page_status.setText(self.tr('No completed benchmark results.'))
            return False
        self.preview_requested.emit(self.selected_run_index())
        return True

    def clear_report(self) -> None:
        self.results_list.blockSignals(True)
        self.results_list.clear()
        self.results_list.blockSignals(False)
        self.page_status.clear()

    def clear_preview_selection(self) -> None:
        self.results_list.blockSignals(True)
        self.results_list.clearSelection()
        self.results_list.setCurrentRow(-1)
        self.results_list.blockSignals(False)

    def selected_run_index(self) -> int:
        item = self.results_list.currentItem()
        if item is None:
            return -1
        run_index = item.data(Qt.ItemDataRole.UserRole)
        return run_index if isinstance(run_index, int) else -1

    def set_page_status(self, page: str, available: bool) -> None:
        if available:
            self.page_status.setText(
                self.tr('Previewing {page}').format(page=page)
            )
        else:
            self.page_status.setText(
                self.tr('No benchmark result for {page}').format(page=page)
            )

    def set_project_translation_status(self, page: str) -> None:
        self.page_status.setText(
            self.tr('Showing editable project translation for {page}').format(
                page=page
            )
        )

    def _selection_changed(self, _row: int) -> None:
        run_index = self.selected_run_index()
        if run_index >= 0:
            self.preview_requested.emit(run_index)
