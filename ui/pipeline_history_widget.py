from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QAbstractItemView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from utils.proj_imgtrans import ProjImgTrans


class PipelineHistoryWindow(QDialog):
    HEADERS = [
        'Started',
        'Pipeline',
        'Status',
        'Duration',
        'Pages',
        'Translator',
        'LLM / Model',
        'Provider',
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.imgtrans_proj: ProjImgTrans = None
        self.setWindowTitle(self.tr('Pipeline History'))
        self.resize(980, 520)

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.refresh_button = QPushButton(self.tr('Refresh'))
        self.refresh_button.clicked.connect(self.refresh)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.path_label, 1)
        top_layout.addWidget(self.refresh_button)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        selection_behavior = getattr(
            getattr(QAbstractItemView, 'SelectionBehavior', QAbstractItemView),
            'SelectRows',
        )
        edit_trigger = getattr(
            getattr(QAbstractItemView, 'EditTrigger', QAbstractItemView),
            'NoEditTriggers',
        )
        self.table.setSelectionBehavior(selection_behavior)
        self.table.setEditTriggers(edit_trigger)
        self.table.verticalHeader().setVisible(False)

        layout = QVBoxLayout(self)
        layout.addLayout(top_layout)
        layout.addWidget(self.table)

    def set_project(self, imgtrans_proj: ProjImgTrans):
        self.imgtrans_proj = imgtrans_proj
        self.refresh()

    def refresh(self):
        if self.imgtrans_proj is None or self.imgtrans_proj.is_empty:
            self.path_label.setText(self.tr('No project is open.'))
            self.table.setRowCount(0)
            return

        self.path_label.setText(self.imgtrans_proj.pipeline_history_path())
        entries = self.imgtrans_proj.load_pipeline_history().get('entries', [])
        entries = list(reversed(entries))
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            modules = entry.get('modules', {}) if isinstance(entry, dict) else {}
            translator = modules.get('translator', {}) if isinstance(modules, dict) else {}
            values = [
                entry.get('started_at', ''),
                entry.get('pipeline', entry.get('process', '')),
                entry.get('status', ''),
                self._format_duration(entry.get('duration_seconds')),
                str(entry.get('page_count', '')),
                translator.get('name', ''),
                translator.get('effective_model', translator.get('model', '')),
                translator.get('provider', ''),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    @staticmethod
    def _format_duration(value) -> str:
        if value is None or value == '':
            return ''
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return str(value)
        if seconds < 60:
            return f'{seconds:.1f}s'
        minutes = int(seconds // 60)
        rest = seconds - minutes * 60
        return f'{minutes}m {rest:.1f}s'
