from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ballontranslator.utils import shared
from ballontranslator.utils.pipeline_history import PipelineHistoryStore

from .framelesswindow import (
    DialogCloseButton,
    FramelessWindow,
    OutsideClickFramelessMixin,
)


class PipelineHistoryWindow(OutsideClickFramelessMixin, FramelessWindow):
    """Read-only history viewer for the active project."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        window_type = getattr(Qt, 'WindowType', Qt)
        super().__init__(parent, window_type.Dialog)
        self.setObjectName('PipelineHistoryWindow')
        self.setWindowTitle(self.tr('Pipeline History'))
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumSize(820, 500)
        self.resize(1040, 620)
        self._store: Optional[PipelineHistoryStore] = None
        self._entries = []

        opaque = shared.ON_WINDOWS or shared.ON_MACOS
        self.setProperty('opaqueFrame', opaque)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        if not opaque:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        root = QVBoxLayout(self)
        root.setContentsMargins(*(0, 0, 0, 0) if opaque else (5, 5, 5, 5))
        surface = QFrame(self)
        surface.setObjectName('PipelineHistorySurface')
        root.addWidget(surface)
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(18, 14, 18, 18)

        self.title_bar = QWidget(surface)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.addWidget(QLabel(self.tr('Pipeline History'), self.title_bar))
        title_layout.addStretch()
        refresh_button = QPushButton(self.tr('Refresh'), self.title_bar)
        refresh_button.clicked.connect(self.refresh)
        title_layout.addWidget(refresh_button)
        self.close_button = DialogCloseButton(self.title_bar)
        self.close_button.clicked.connect(self.hide)
        title_layout.addWidget(self.close_button)
        layout.addWidget(self.title_bar)

        self.table = QTableWidget(0, 7, surface)
        self.table.setHorizontalHeaderLabels([
            self.tr('Started'), self.tr('Duration'), self.tr('Status'),
            self.tr('Operation'), self.tr('Stages'), self.tr('Translator'),
            self.tr('LLM model'),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._show_selected_details)
        layout.addWidget(self.table, 2)

        self.details = QTextEdit(surface)
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(180)
        layout.addWidget(self.details, 1)

    def _preserve_on_outside_click(self) -> bool:
        return True

    def set_directory(self, directory: str) -> None:
        self._store = PipelineHistoryStore(directory) if directory else None
        self.refresh()

    def refresh(self) -> None:
        try:
            self._entries = self._store.load() if self._store is not None else []
        except Exception as error:
            self._entries = []
            QMessageBox.warning(
                self,
                self.tr('Pipeline History'),
                self.tr('The pipeline history could not be loaded: {error}').format(
                    error=error
                ),
            )
        entries = list(reversed(self._entries))
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            details = entry.get('details') or {}
            pipeline = details.get('pipeline') or {}
            llm = details.get('translation_llm') or {}
            stages = ', '.join(
                self._stage_label(stage)
                for stage in (pipeline.get('stages') or [])
            )
            modules = pipeline.get('modules') or {}
            values = (
                _local_timestamp(entry.get('started_at')),
                _duration(entry.get('duration_seconds')),
                self._status_label(str(entry.get('status') or '')),
                self._operation_label(str(entry.get('kind') or '')),
                stages,
                str(modules.get('translator') or ''),
                str(llm.get('model') or ''),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, entry)
                self.table.setItem(row, column, item)
        if entries:
            self.table.selectRow(0)
        else:
            self.details.clear()

    def _show_selected_details(self) -> None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self.details.setPlainText(
            json.dumps(entry, ensure_ascii=False, indent=2) if entry else ''
        )

    def _status_label(self, status: str) -> str:
        return {
            'running': self.tr('Running'),
            'completed': self.tr('Completed'),
            'failed': self.tr('Failed'),
            'cancelled': self.tr('Cancelled'),
        }.get(status, status)

    def _operation_label(self, operation: str) -> str:
        return {
            'pipeline': self.tr('Pipeline'),
            'pipeline_continue': self.tr('Continue pipeline'),
            'render': self.tr('Render'),
            'reinpaint': self.tr('Re-inpainting'),
            'batch': self.tr('Batch processing'),
            'batch_task': self.tr('Batch phase'),
        }.get(operation, operation)

    def _stage_label(self, stage: str) -> str:
        return {
            'detect': self.tr('Text detection'),
            'ocr': self.tr('OCR'),
            'inpaint': self.tr('Inpaint'),
            'translate': self.tr('Translation'),
        }.get(stage, stage)


def _local_timestamp(value) -> str:
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone().strftime(
            '%Y-%m-%d %H:%M:%S'
        )
    except ValueError:
        return str(value or '')


def _duration(value) -> str:
    if value is None:
        return '—'
    seconds = max(0.0, float(value))
    hours, remainder = divmod(int(seconds), 3600)
    minutes, whole_seconds = divmod(remainder, 60)
    if hours:
        return f'{hours:d}:{minutes:02d}:{whole_seconds:02d}'
    return f'{minutes:02d}:{whole_seconds:02d}'
