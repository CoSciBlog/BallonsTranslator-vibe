"""Project glossary manager backed by the Qt-free glossary workspace."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from qtpy.QtCore import QCoreApplication, Qt
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ballontranslator.glossary import (
    DuplicateGlossaryEntryError,
    GlossaryCategory,
    GlossaryEntry,
    GlossaryOrigin,
    GlossaryStatus,
    GlossaryWorkspace,
)
from ballontranslator.utils import shared
from ballontranslator.utils.config import pcfg

from .framelesswindow import (
    DialogCloseButton,
    FramelessWindow,
    OutsideClickFramelessMixin,
)


class GlossaryEntryDialog(QDialog):
    """Edit one writable glossary entry with explicit review state."""

    def __init__(self, entry: Optional[GlossaryEntry] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr('Glossary Entry'))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.original = QLineEdit(entry.original if entry else '', self)
        self.translation = QLineEdit(entry.translation if entry else '', self)
        self.source_language = QLineEdit(entry.source_language if entry else '', self)
        self.target_language = QLineEdit(entry.target_language if entry else '', self)
        self.category = QComboBox(self)
        for category in GlossaryCategory:
            self.category.addItem(_category_label(self, category), category.value)
        self.aliases = QLineEdit(', '.join(entry.aliases) if entry else '', self)
        self.description = QTextEdit(entry.description if entry else '', self)
        self.description.setMaximumHeight(90)
        self.status = QComboBox(self)
        for status in GlossaryStatus:
            self.status.addItem(_status_label(self, status), status.value)
        self.protected = QCheckBox(self.tr('Prevent automatic changes'), self)
        self.protected.setChecked(bool(entry and entry.protected))
        if entry:
            self.category.setCurrentIndex(self.category.findData(entry.category.value))
            self.status.setCurrentIndex(self.status.findData(entry.status.value))
        form.addRow(self.tr('Original term'), self.original)
        form.addRow(self.tr('Translation'), self.translation)
        form.addRow(self.tr('Source language'), self.source_language)
        form.addRow(self.tr('Target language'), self.target_language)
        form.addRow(self.tr('Category'), self.category)
        form.addRow(self.tr('Aliases'), self.aliases)
        form.addRow(self.tr('Notes'), self.description)
        form.addRow('', self.protected)
        form.addRow(self.tr('Status'), self.status)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            'original': self.original.text().strip(),
            'translation': self.translation.text().strip(),
            'source_language': self.source_language.text().strip(),
            'target_language': self.target_language.text().strip(),
            'category': self.category.currentData(),
            'aliases': tuple(
                value.strip() for value in self.aliases.text().split(',')
                if value.strip()
            ),
            'description': self.description.toPlainText().strip(),
            'status': self.status.currentData(),
            'protected': self.protected.isChecked(),
        }


class GlossaryWindow(OutsideClickFramelessMixin, FramelessWindow):
    """Manage project, series, and reference glossaries in one window.

    >>> issubclass(GlossaryWindow, FramelessWindow)
    True
    """

    ENTRY_COLUMNS = (
        'Original', 'Translation', 'Category', 'Aliases', 'Status',
        'Protected', 'Origin', 'Source',
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        window_type = getattr(Qt, 'WindowType', Qt)
        super().__init__(parent, window_type.Dialog)
        self.setObjectName('GlossaryWindow')
        self.setWindowTitle(self.tr('Glossary Manager'))
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumSize(860, 560)
        self.resize(1040, 680)
        opaque = shared.ON_WINDOWS or shared.ON_MACOS
        self.setProperty('opaqueFrame', opaque)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        if not opaque:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._workspace: Optional[GlossaryWorkspace] = None
        self._translation_pairs: Tuple[Tuple[str, str], ...] = ()
        self._entry_rows = []
        self._conflict_rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0 if opaque else 5, 0 if opaque else 5, 0 if opaque else 5, 0 if opaque else 5)
        surface = QFrame(self)
        surface.setObjectName('GlossarySurface')
        root.addWidget(surface)
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(18, 14, 18, 18)

        self.title_bar = QWidget(surface)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel(self.tr('Glossary Manager'), self.title_bar)
        title.setObjectName('GlossaryTitle')
        title_layout.addWidget(title)
        title_layout.addStretch()
        self.close_button = DialogCloseButton(self.title_bar)
        self.close_button.clicked.connect(self.hide)
        title_layout.addWidget(self.close_button)
        layout.addWidget(self.title_bar)

        self.tabs = QTabWidget(surface)
        self.tabs.addTab(self._build_entries_tab(), self.tr('Entries'))
        self.tabs.addTab(self._build_sources_tab(), self.tr('Sources'))
        self.tabs.addTab(self._build_conflicts_tab(), self.tr('Conflicts'))
        layout.addWidget(self.tabs)
        self._set_enabled_state()

    def _preserve_on_outside_click(self) -> bool:
        return True

    def set_workspace(
        self,
        workspace: Optional[GlossaryWorkspace],
        translation_pairs: Sequence[Tuple[str, str]] = (),
    ) -> None:
        self._workspace = workspace
        self._translation_pairs = tuple(translation_pairs)
        self._set_enabled_state()
        self.refresh()

    def refresh(self) -> None:
        self._refresh_entries()
        self._refresh_sources()
        self._refresh_conflicts()

    def _build_entries_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        self.search_edit = QLineEdit(tab)
        self.search_edit.setPlaceholderText(self.tr('Search terms, translations, aliases, or notes'))
        self.search_edit.textChanged.connect(self._refresh_entries)
        self.status_filter = QComboBox(tab)
        self.status_filter.addItem(self.tr('All statuses'), '')
        for status in GlossaryStatus:
            self.status_filter.addItem(_status_label(self, status), status.value)
        self.status_filter.currentIndexChanged.connect(self._refresh_entries)
        self.category_filter = QComboBox(tab)
        self.category_filter.addItem(self.tr('All categories'), '')
        for category in GlossaryCategory:
            self.category_filter.addItem(_category_label(self, category), category.value)
        self.category_filter.currentIndexChanged.connect(self._refresh_entries)
        self.source_filter = QComboBox(tab)
        self.source_filter.currentIndexChanged.connect(self._refresh_entries)
        controls.addWidget(self.search_edit, 1)
        controls.addWidget(self.status_filter)
        controls.addWidget(self.category_filter)
        controls.addWidget(self.source_filter)
        layout.addLayout(controls)

        self.entry_table = QTableWidget(0, len(self.ENTRY_COLUMNS), tab)
        self.entry_table.setHorizontalHeaderLabels([
            self.tr('Original'), self.tr('Translation'), self.tr('Category'),
            self.tr('Aliases'), self.tr('Status'), self.tr('Protected'),
            self.tr('Origin'), self.tr('Source'),
        ])
        self.entry_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.entry_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.entry_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.entry_table.horizontalHeader().setStretchLastSection(True)
        self.entry_table.doubleClicked.connect(self._edit_entry)
        layout.addWidget(self.entry_table, 1)

        actions = QHBoxLayout()
        for text, slot in (
            (self.tr('Add'), self._add_entry),
            (self.tr('Edit'), self._edit_entry),
            (self.tr('Delete'), self._delete_entry),
            (self.tr('Confirm'), self._confirm_entry),
            (self.tr('Reject'), self._reject_entry),
            (self.tr('Toggle protection'), self._toggle_protection),
        ):
            button = QPushButton(text, tab)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        maintenance = QHBoxLayout()
        for text, slot in (
            (self.tr('Fill missing translations'), self._fill_missing_translations),
            (self.tr('Import JSON'), self._import_glossary),
            (self.tr('Export JSON'), self._export_glossary),
        ):
            button = QPushButton(text, tab)
            button.clicked.connect(slot)
            maintenance.addWidget(button)
        maintenance.addStretch()
        layout.addLayout(maintenance)
        return tab

    def _build_sources_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        help_label = QLabel(self.tr(
            'Project entries are writable. Series entries are shared between chapters; reference glossaries are read-only.'
        ), tab)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        self.sources_list = QListWidget(tab)
        layout.addWidget(self.sources_list, 1)
        actions = QHBoxLayout()
        for text, slot in (
            (self.tr('Select series glossary'), self._select_series),
            (self.tr('Remove series glossary'), self._remove_series),
            (self.tr('Add reference glossary'), self._add_reference),
            (self.tr('Remove selected reference'), self._remove_reference),
            (self.tr('Copy confirmed entries to series'), self._promote_to_series),
        ):
            button = QPushButton(text, tab)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        return tab

    def _build_conflicts_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        self.conflict_table = QTableWidget(0, 5, tab)
        self.conflict_table.setHorizontalHeaderLabels([
            self.tr('Term'), self.tr('Translation'), self.tr('Source'),
            self.tr('Status'), self.tr('Priority'),
        ])
        self.conflict_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.conflict_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.conflict_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.conflict_table, 1)
        self.resolve_button = QPushButton(self.tr('Use selected translation in project glossary'), tab)
        self.resolve_button.clicked.connect(self._resolve_conflict)
        layout.addWidget(self.resolve_button)
        return tab

    def _set_enabled_state(self) -> None:
        if hasattr(self, 'tabs'):
            self.tabs.setEnabled(self._workspace is not None)

    def _refresh_entries(self, *_args) -> None:
        if not hasattr(self, 'entry_table'):
            return
        self.entry_table.setRowCount(0)
        self._entry_rows = []
        workspace = self._workspace
        if workspace is None:
            return
        source_filter = self.source_filter.currentData() if self.source_filter.count() else ''
        query = self.search_edit.text().casefold().strip()
        category = self.category_filter.currentData()
        status = self.status_filter.currentData()
        for record in workspace.source_entries():
            entry = record.entry
            if source_filter and record.source_id != source_filter:
                continue
            if category and entry.category.value != category:
                continue
            if status and entry.status.value != status:
                continue
            searchable = ' '.join((entry.original, entry.translation, entry.description, *entry.aliases)).casefold()
            if query and query not in searchable:
                continue
            row = self.entry_table.rowCount()
            self.entry_table.insertRow(row)
            values = (
                entry.original, entry.translation, _category_label(self, entry.category),
                ', '.join(entry.aliases), _status_label(self, entry.status),
                self.tr('Yes') if entry.protected else self.tr('No'),
                _origin_label(self, entry.origin), _source_label(self, record.source_kind),
            )
            for column, value in enumerate(values):
                self.entry_table.setItem(row, column, QTableWidgetItem(str(value)))
            self._entry_rows.append(record)

    def _refresh_sources(self) -> None:
        if not hasattr(self, 'sources_list'):
            return
        self.sources_list.clear()
        current = self.source_filter.currentData() if self.source_filter.count() else ''
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem(self.tr('All sources'), '')
        if self._workspace:
            for source in self._workspace.sources:
                label = '{} — {}'.format(
                    _source_label(self, source.kind),
                    source.path or self.tr('In memory'),
                )
                item = QListWidgetItem(label, self.sources_list)
                item.setData(Qt.ItemDataRole.UserRole, source.path)
                item.setData(Qt.ItemDataRole.UserRole + 1, source.kind)
                self.source_filter.addItem(_source_label(self, source.kind), source.source_id)
        index = self.source_filter.findData(current)
        self.source_filter.setCurrentIndex(max(0, index))
        self.source_filter.blockSignals(False)

    def _refresh_conflicts(self) -> None:
        if not hasattr(self, 'conflict_table'):
            return
        self.conflict_table.setRowCount(0)
        self._conflict_rows = []
        if not self._workspace:
            if hasattr(self, 'tabs'):
                self.tabs.setTabText(2, self.tr('Conflicts'))
            return
        conflicts = self._workspace.conflicts()
        if hasattr(self, 'tabs'):
            label = self.tr('Conflicts')
            if pcfg.module.project_glossary_conflict_warnings and conflicts:
                label = '{} ({})'.format(label, len(conflicts))
            self.tabs.setTabText(2, label)
        for conflict in conflicts:
            for candidate in (conflict.winner,) + conflict.alternatives:
                row = self.conflict_table.rowCount()
                self.conflict_table.insertRow(row)
                values = (
                    conflict.term, candidate.entry.translation,
                    _source_label(self, candidate.source_kind),
                    _status_label(self, candidate.entry.status),
                    candidate.priority,
                )
                for column, value in enumerate(values):
                    self.conflict_table.setItem(row, column, QTableWidgetItem(str(value)))
                self._conflict_rows.append(candidate)

    def _selected_entry(self):
        row = self.entry_table.currentRow()
        return self._entry_rows[row] if 0 <= row < len(self._entry_rows) else None

    def _selected_service(self):
        record = self._selected_entry()
        if record is None or not record.writable or self._workspace is None:
            return None
        if record.source_kind == 'project':
            return self._workspace.project
        return self._workspace.series.service if self._workspace.series else None

    def _add_entry(self) -> None:
        if not self._workspace:
            return
        self._run_entry_dialog(self._workspace.project)

    def _edit_entry(self, *_args) -> None:
        record = self._selected_entry()
        service = self._selected_service()
        if record is None or service is None:
            self._information(self.tr('Select a writable project or series entry.'))
            return
        self._run_entry_dialog(service, record.entry)

    def _run_entry_dialog(self, service, entry: Optional[GlossaryEntry] = None) -> None:
        dialog = GlossaryEntryDialog(entry, self)
        try:
            if dialog.exec_() != QDialog.Accepted:
                return
            values = dialog.values()
            if not values['original']:
                self._error(self.tr('The original term is required.'))
                return
            if entry is None:
                values['origin'] = GlossaryOrigin.MANUAL.value
                service.create_entry(**values)
            else:
                service.update_entry(entry.id, **values)
            self.refresh()
        except (ValueError, DuplicateGlossaryEntryError) as error:
            self._error(str(error))
        finally:
            dialog.deleteLater()

    def _delete_entry(self) -> None:
        record = self._selected_entry()
        service = self._selected_service()
        if record is None or service is None:
            return
        answer = QMessageBox.question(self, self.tr('Delete glossary entry'), self.tr('Delete the selected entry?'))
        if answer == QMessageBox.StandardButton.Yes:
            service.delete_entry(record.entry.id)
            self.refresh()

    def _confirm_entry(self) -> None:
        self._set_status(GlossaryStatus.CONFIRMED)

    def _reject_entry(self) -> None:
        self._set_status(GlossaryStatus.REJECTED)

    def _set_status(self, status: GlossaryStatus) -> None:
        record = self._selected_entry()
        service = self._selected_service()
        if record and service:
            service.update_entry(record.entry.id, status=status.value)
            self.refresh()

    def _toggle_protection(self) -> None:
        record = self._selected_entry()
        service = self._selected_service()
        if record and service:
            service.protect_entry(record.entry.id, not record.entry.protected)
            self.refresh()

    def _fill_missing_translations(self) -> None:
        """Recover empty project mappings from translated text blocks."""

        if not self._workspace:
            return
        updated = self._workspace.project.backfill_missing_translations(
            self._translation_pairs
        )
        self.refresh()
        if updated:
            message = self.tr('Filled {count} missing translation(s).').format(
                count=updated
            )
        else:
            message = self.tr(
                'No unambiguous translated text blocks matched empty entries.'
            )
        self._information(message)

    def _import_glossary(self) -> None:
        if not self._workspace:
            return
        path, _ = QFileDialog.getOpenFileName(self, self.tr('Import Glossary'), '', self.tr('JSON Files (*.json)'))
        if path:
            result = self._workspace.merge_into_project(path)
            self._information(self.tr('Imported: {added}; duplicates: {duplicates}; conflicts: {conflicts}').format(
                added=result.added, duplicates=result.duplicates, conflicts=result.conflicts
            ))
            self.refresh()

    def _export_glossary(self) -> None:
        if not self._workspace:
            return
        path, _ = QFileDialog.getSaveFileName(self, self.tr('Export Glossary'), 'glossary.json', self.tr('JSON Files (*.json)'))
        if path:
            self._workspace.project.export_file(path)

    def _select_series(self) -> None:
        if not self._workspace:
            return
        path, _ = QFileDialog.getSaveFileName(self, self.tr('Select Series Glossary'), 'series_glossary.json', self.tr('JSON Files (*.json)'))
        if path:
            self._workspace.assign_series(path)
            pcfg.module.project_glossary_series_enabled = True
            pcfg.module.project_glossary_series_path = path
            self.series_setting.setChecked(True)
            self.refresh()

    def _remove_series(self) -> None:
        if self._workspace:
            self._workspace.clear_series()
            pcfg.module.project_glossary_series_enabled = False
            pcfg.module.project_glossary_series_path = ''
            self.series_setting.setChecked(False)
            self.refresh()

    def _add_reference(self) -> None:
        if not self._workspace:
            return
        path, _ = QFileDialog.getOpenFileName(self, self.tr('Add Reference Glossary'), '', self.tr('JSON Files (*.json)'))
        if path:
            self._workspace.add_reference(path)
            pcfg.module.project_glossary_reference_paths = [source.path for source in self._workspace.references]
            self.refresh()

    def _remove_reference(self) -> None:
        if not self._workspace:
            return
        item = self.sources_list.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole + 1) == 'reference':
            self._workspace.remove_reference(item.data(Qt.ItemDataRole.UserRole))
            pcfg.module.project_glossary_reference_paths = [source.path for source in self._workspace.references]
            self.refresh()

    def _promote_to_series(self) -> None:
        if not self._workspace:
            return
        try:
            result = self._workspace.promote_confirmed_to_series()
        except RuntimeError as error:
            self._error(str(error))
            return
        self._information(self.tr('Copied: {added}; duplicates: {duplicates}; conflicts: {conflicts}').format(
            added=result.added, duplicates=result.duplicates, conflicts=result.conflicts
        ))
        self.refresh()

    def _resolve_conflict(self) -> None:
        if not self._workspace:
            return
        row = self.conflict_table.currentRow()
        if not 0 <= row < len(self._conflict_rows):
            return
        candidate = self._conflict_rows[row].entry
        matches = self._workspace.project.find_duplicates(candidate.original, candidate.aliases)
        if matches:
            self._workspace.project.update_entry(
                matches[0].id,
                translation=candidate.translation,
                status=GlossaryStatus.CONFIRMED.value,
            )
        else:
            values = candidate.to_dict()
            for key in ('id', 'created_at', 'updated_at', 'schema_version'):
                values.pop(key, None)
            values['origin'] = GlossaryOrigin.MANUAL.value
            values['status'] = GlossaryStatus.CONFIRMED.value
            self._workspace.project.create_entry(**values)
        self.refresh()

    def _error(self, message: str) -> None:
        QMessageBox.warning(self, self.tr('Glossary'), message)

    def _information(self, message: str) -> None:
        QMessageBox.information(self, self.tr('Glossary'), message)


def _category_label(widget: QWidget, category: GlossaryCategory) -> str:
    labels = {
        GlossaryCategory.CHARACTER: QCoreApplication.translate('GlossaryWindow', 'Character'),
        GlossaryCategory.PLACE: QCoreApplication.translate('GlossaryWindow', 'Place'),
        GlossaryCategory.ORGANIZATION: QCoreApplication.translate('GlossaryWindow', 'Organization'),
        GlossaryCategory.TITLE: QCoreApplication.translate('GlossaryWindow', 'Title'),
        GlossaryCategory.HONORIFIC: QCoreApplication.translate('GlossaryWindow', 'Honorific'),
        GlossaryCategory.ITEM: QCoreApplication.translate('GlossaryWindow', 'Item'),
        GlossaryCategory.ABILITY: QCoreApplication.translate('GlossaryWindow', 'Ability'),
        GlossaryCategory.TERMINOLOGY: QCoreApplication.translate('GlossaryWindow', 'Terminology'),
        GlossaryCategory.CATCHPHRASE: QCoreApplication.translate('GlossaryWindow', 'Catchphrase'),
        GlossaryCategory.OTHER: QCoreApplication.translate('GlossaryWindow', 'Other'),
    }
    return labels[category]


def _status_label(widget: QWidget, status: GlossaryStatus) -> str:
    labels = {
        GlossaryStatus.SUGGESTION: QCoreApplication.translate('GlossaryWindow', 'Suggestion'),
        GlossaryStatus.CONFIRMED: QCoreApplication.translate('GlossaryWindow', 'Confirmed'),
        GlossaryStatus.REJECTED: QCoreApplication.translate('GlossaryWindow', 'Rejected'),
    }
    return labels[status]


def _origin_label(widget: QWidget, origin: GlossaryOrigin) -> str:
    labels = {
        GlossaryOrigin.MANUAL: QCoreApplication.translate('GlossaryWindow', 'Manual'),
        GlossaryOrigin.OCR: QCoreApplication.translate('GlossaryWindow', 'OCR'),
        GlossaryOrigin.LLM: QCoreApplication.translate('GlossaryWindow', 'LLM'),
        GlossaryOrigin.IMPORT: QCoreApplication.translate('GlossaryWindow', 'Import'),
    }
    return labels[origin]


def _source_label(widget: QWidget, kind: str) -> str:
    return {
        'project': QCoreApplication.translate('GlossaryWindow', 'Project'),
        'series': QCoreApplication.translate('GlossaryWindow', 'Series'),
        'reference': QCoreApplication.translate('GlossaryWindow', 'Reference'),
    }.get(kind, kind)
