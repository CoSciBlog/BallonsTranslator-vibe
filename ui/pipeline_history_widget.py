from qtpy.QtCore import QEvent, Qt
from qtpy.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QAbstractItemView,
    QSizePolicy,
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
    COLUMN_WEIGHTS = (18, 11, 10, 10, 7, 15, 24, 11, 10)
    COLUMN_MIN_WIDTHS = (110, 70, 65, 70, 50, 85, 125, 70, 70)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.imgtrans_proj: ProjImgTrans = None
        self.setWindowTitle(self.tr('Pipeline History'))
        self.resize(1180, 560)
        self._history_path = ''

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

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
                lambda visible, index=column: self._set_column_visible(index, visible)
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
        self.table.viewport().installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.addLayout(top_layout)
        layout.addWidget(self.table)

    @classmethod
    def responsive_column_widths(cls, available_width: int, visible_columns=None):
        if visible_columns is None:
            visible_columns = list(range(len(cls.HEADERS)))
        visible_columns = list(visible_columns)
        if not visible_columns:
            return {}

        minimum_total = sum(cls.COLUMN_MIN_WIDTHS[column] for column in visible_columns)
        available_width = max(0, int(available_width))
        if available_width <= minimum_total:
            return {
                column: cls.COLUMN_MIN_WIDTHS[column]
                for column in visible_columns
            }

        widths = {}
        remaining_columns = list(visible_columns)
        remaining_width = available_width
        while remaining_columns:
            weight_total = sum(cls.COLUMN_WEIGHTS[column] for column in remaining_columns)
            constrained = [
                column
                for column in remaining_columns
                if remaining_width * cls.COLUMN_WEIGHTS[column] / weight_total
                < cls.COLUMN_MIN_WIDTHS[column]
            ]
            if not constrained:
                assigned = 0
                for column in remaining_columns[:-1]:
                    width = int(
                        remaining_width * cls.COLUMN_WEIGHTS[column] / weight_total
                    )
                    widths[column] = width
                    assigned += width
                widths[remaining_columns[-1]] = remaining_width - assigned
                break
            for column in constrained:
                width = cls.COLUMN_MIN_WIDTHS[column]
                widths[column] = width
                remaining_width -= width
                remaining_columns.remove(column)
        return widths

    def _resize_columns_to_viewport(self):
        visible_columns = [
            column
            for column in range(len(self.HEADERS))
            if not self.table.isColumnHidden(column)
        ]
        widths = self.responsive_column_widths(
            self.table.viewport().width(), visible_columns
        )
        header = self.table.horizontalHeader()
        for column, width in widths.items():
            header.resizeSection(column, width)

    def _update_path_label(self):
        if not self._history_path:
            return
        width = max(40, self.path_label.width())
        text = self.path_label.fontMetrics().elidedText(
            self._history_path,
            Qt.TextElideMode.ElideMiddle,
            width,
        )
        self.path_label.setText(text)
        self.path_label.setToolTip(self._history_path)

    def _set_column_visible(self, column: int, visible: bool):
        self.table.setColumnHidden(column, not visible)
        self._resize_columns_to_viewport()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'path_label'):
            self._update_path_label()
        if hasattr(self, 'table'):
            self._resize_columns_to_viewport()

    def eventFilter(self, watched, event):
        if (
            hasattr(self, 'table')
            and watched is self.table.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            self._resize_columns_to_viewport()
        return super().eventFilter(watched, event)

    def set_project(self, imgtrans_proj: ProjImgTrans):
        self.imgtrans_proj = imgtrans_proj
        self.refresh()

    def refresh(self):
        if self.imgtrans_proj is None or self.imgtrans_proj.is_empty:
            self._history_path = self.tr('No project is open.')
            self._update_path_label()
            self.table.setRowCount(0)
            return

        self._history_path = self.imgtrans_proj.pipeline_history_path()
        self._update_path_label()
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
        self._resize_columns_to_viewport()

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
