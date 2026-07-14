from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QAbstractItemView,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from utils.proj_imgtrans import ProjImgTrans


class PipelineHistoryWindow(QDialog):
    HEADERS = [
        'Started',
        'Step',
        'Status',
        'Duration',
        'Pages',
        'Module',
        'LLM / Model',
        'Provider',
        'Reasoning',
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.imgtrans_proj: ProjImgTrans = None
        self.setWindowTitle(self.tr('Pipeline History'))
        self.resize(1180, 560)

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.refresh_button = QPushButton(self.tr('Refresh'))
        self.refresh_button.clicked.connect(self.refresh)

        self.columns_button = QPushButton(self.tr('Columns'))
        self.columns_menu = QMenu(self.columns_button)
        self.column_actions = []
        for column, header in enumerate(self.HEADERS):
            action = self.columns_menu.addAction(self.tr(header))
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(
                lambda visible, index=column: self.table.setColumnHidden(index, not visible)
            )
            self.column_actions.append(action)
        self.columns_button.setMenu(self.columns_menu)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.path_label, 1)
        top_layout.addWidget(self.columns_button)
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
        rows = []
        for entry in reversed(entries):
            rows.extend(self._entry_rows(entry))
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    @classmethod
    def _entry_rows(cls, entry):
        if not isinstance(entry, dict):
            return []
        common = [entry.get('started_at', '')]
        summary = common + [
            'Pipeline',
            entry.get('status', ''),
            cls._format_duration(entry.get('duration_seconds')),
            str(entry.get('page_count', '')),
            '',
            '',
            '',
            '',
        ]
        rows = [summary]
        for step in cls._history_steps(entry):
            if not step.get('enabled'):
                continue
            module = step.get('module', {})
            if not isinstance(module, dict):
                module = {}
            provider = str(module.get('provider', ''))
            reasoning = ''
            if provider.casefold() == 'ollama':
                reasoning = cls.tristate_text(module.get('reasoning'))
            rows.append(common + [
                step.get('label', step.get('step', '')),
                step.get('status', entry.get('status', '')),
                cls._format_duration(step.get('duration_seconds')),
                str(entry.get('page_count', '')),
                module.get('name', ''),
                module.get('effective_model', module.get('model', '')),
                provider,
                reasoning,
            ])
        return rows

    @staticmethod
    def _history_steps(entry):
        steps = entry.get('steps')
        if isinstance(steps, list):
            return [step for step in steps if isinstance(step, dict)]

        stages = entry.get('stages', {})
        modules = entry.get('modules', {})
        if not isinstance(stages, dict):
            stages = {}
        if not isinstance(modules, dict):
            modules = {}
        definitions = [
            ('text_detection', 'Text Detection', 'detect', 'textdetector'),
            ('ocr', 'OCR', 'ocr', 'ocr'),
            ('translate', 'Translate', 'translate', 'translator'),
            ('inpaint', 'Inpaint', 'inpaint', 'inpainter'),
        ]
        return [
            {
                'step': step,
                'label': label,
                'enabled': bool(stages.get(stage_key)),
                'status': entry.get('status', ''),
                'module': modules.get(module_key, {}),
            }
            for step, label, stage_key, module_key in definitions
        ]

    @staticmethod
    def tristate_text(value) -> str:
        if value is None or value == '':
            return ''
        return 'Yes' if bool(value) else 'No'

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
