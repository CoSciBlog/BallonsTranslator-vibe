import json
from typing import Dict, List

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QStandardItem, QStandardItemModel
from qtpy.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QTableView,
    QVBoxLayout,
)

from .custom_widget import NoBorderPushBtn
from utils.glossary_replacement import parse_glossary_entries
from utils.glossary_template import build_glossary_from_translated_folder


class GlossaryWindow(QDialog):
    saved = Signal(dict)

    HEADERS = ("Source", "Target", "Category", "Note")

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(self.tr("Project Glossary"))
        self.setModal(False)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)
        self.project_glossary = {
            "entries": "",
            "prompt": "",
            "reference_entries": "",
            "reference_prompt": "",
        }
        self._loading = False

        self.info_label = QLabel(
            self.tr("Glossary entries saved in the current project's glossary.json.")
        )
        self.info_label.setToolTip(
            self.tr(
                "These entries are passed to LLM translators for consistent names, places, titles, and recurring terms."
            )
        )

        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels([self.tr(header) for header in self.HEADERS])
        self.table = QTableView(self)
        self.table.setModel(self.model)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setToolTip(
            self.tr(
                "Project glossary entries. Format when saved: source => target [category] # note."
            )
        )

        self.prompt_label = QLabel(self.tr("Glossary prompt"))
        self.prompt_label.setToolTip(
            self.tr("Custom instructions inserted before the project glossary in LLM translation prompts.")
        )
        self.prompt_editor = QPlainTextEdit(self)
        self.prompt_editor.setToolTip(
            self.tr(
                "Tell the translator how to apply glossary entries. Keep category and note metadata out of translated text."
            )
        )

        self.reference_label = QLabel(self.tr("Reference glossary"))
        self.reference_label.setToolTip(
            self.tr(
                "Optional imported glossary from another chapter or an official translation template. It is used as context and does not replace project entries."
            )
        )
        self.reference_editor = QPlainTextEdit(self)
        self.reference_editor.setToolTip(
            self.tr(
                "Reference entries use the same source => target [category] # note format. Project entries win when terms conflict."
            )
        )
        self.reference_prompt_label = QLabel(self.tr("Reference prompt"))
        self.reference_prompt_editor = QPlainTextEdit(self)
        self.reference_prompt_editor.setMaximumHeight(70)
        self.reference_prompt_editor.setToolTip(
            self.tr("Optional instructions for using the reference glossary.")
        )

        self.new_btn = NoBorderPushBtn(self.tr("New"), self)
        self.new_btn.setToolTip(self.tr("Add an empty glossary entry."))
        self.new_btn.clicked.connect(self.add_empty_row)
        self.del_btn = NoBorderPushBtn(self.tr("Delete"), self)
        self.del_btn.setToolTip(self.tr("Delete selected glossary entries."))
        self.del_btn.clicked.connect(self.delete_selected_rows)
        self.import_btn = NoBorderPushBtn(self.tr("Import Glossary"), self)
        self.import_btn.setToolTip(self.tr("Import glossary entries from a glossary.json file into the project table."))
        self.import_btn.clicked.connect(self.import_glossary)
        self.import_ref_btn = NoBorderPushBtn(self.tr("Import Reference"), self)
        self.import_ref_btn.setToolTip(self.tr("Import another chapter's glossary.json as reference context."))
        self.import_ref_btn.clicked.connect(self.import_reference_glossary)
        self.export_btn = NoBorderPushBtn(self.tr("Export Glossary"), self)
        self.export_btn.setToolTip(self.tr("Export this glossary as a JSON file."))
        self.export_btn.clicked.connect(self.export_glossary)
        self.template_btn = NoBorderPushBtn(self.tr("Build From Translated Folder"), self)
        self.template_btn.setToolTip(
            self.tr(
                "Choose a folder with an already translated manga/project and extract likely names, places, organizations, and titles."
            )
        )
        self.template_btn.clicked.connect(self.build_template_from_folder)
        self.include_subfolders = QCheckBox(self.tr("Include subfolders"), self)
        self.include_subfolders.setToolTip(self.tr("Scan nested chapter folders when building a glossary template."))
        self.save_btn = NoBorderPushBtn(self.tr("Save Glossary"), self)
        self.save_btn.setToolTip(self.tr("Save the glossary into the current project's glossary.json."))
        self.save_btn.clicked.connect(self.save_glossary)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        layout.addWidget(self.table)
        edit_buttons = QHBoxLayout()
        for button in (self.new_btn, self.del_btn, self.import_btn, self.import_ref_btn, self.export_btn):
            edit_buttons.addWidget(button)
        layout.addLayout(edit_buttons)
        template_buttons = QHBoxLayout()
        template_buttons.addWidget(self.template_btn)
        template_buttons.addWidget(self.include_subfolders)
        layout.addLayout(template_buttons)
        layout.addWidget(self.prompt_label)
        layout.addWidget(self.prompt_editor)
        layout.addWidget(self.reference_label)
        layout.addWidget(self.reference_editor)
        layout.addWidget(self.reference_prompt_label)
        layout.addWidget(self.reference_prompt_editor)
        layout.addWidget(self.save_btn)
        self.setMinimumSize(820, 700)

    def load_glossary(self, glossary: Dict[str, str]):
        self._loading = True
        self.project_glossary = dict(glossary or {})
        self.model.removeRows(0, self.model.rowCount())
        for entry in parse_glossary_entries(self.project_glossary.get("entries", "")):
            self.add_row(entry, save=False)
        self.prompt_editor.setPlainText(self.project_glossary.get("prompt", ""))
        self.reference_editor.setPlainText(self.project_glossary.get("reference_entries", ""))
        self.reference_prompt_editor.setPlainText(self.project_glossary.get("reference_prompt", ""))
        self._loading = False

    def add_empty_row(self):
        self.add_row({"source": "", "target": "", "category": "term", "note": ""})

    def add_row(self, entry: Dict[str, str], save=True):
        row = self.model.rowCount()
        values = [
            entry.get("source", ""),
            entry.get("target", ""),
            entry.get("category", "term") or "term",
            entry.get("note", ""),
        ]
        for col, value in enumerate(values):
            self.model.setItem(row, col, QStandardItem(value))
        if save and not self._loading:
            self.project_glossary = self.collect_glossary()

    def delete_selected_rows(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.model.removeRow(row)

    def collect_glossary(self) -> Dict[str, str]:
        lines: List[str] = []
        for row in range(self.model.rowCount()):
            values = []
            for col in range(4):
                item = self.model.item(row, col)
                values.append(item.text().strip() if item is not None else "")
            source, target, category, note = values
            if not source or not target:
                continue
            line = f"{source} => {target}"
            if category:
                line += f" [{category}]"
            if note:
                line += f" # {note}"
            lines.append(line)
        return {
            "entries": "\n".join(lines),
            "prompt": self.prompt_editor.toPlainText().strip(),
            "reference_entries": self.reference_editor.toPlainText().strip(),
            "reference_prompt": self.reference_prompt_editor.toPlainText().strip(),
        }

    def save_glossary(self):
        self.project_glossary = self.collect_glossary()
        self.saved.emit(dict(self.project_glossary))

    def import_glossary(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import Glossary"),
            "",
            self.tr("Glossary JSON (*.json);;All Files (*)"),
        )
        if not path:
            return
        try:
            glossary = self._read_glossary_file(path)
            for entry in parse_glossary_entries(glossary.get("entries", "")):
                self.add_row(entry)
            if glossary.get("prompt") and not self.prompt_editor.toPlainText().strip():
                self.prompt_editor.setPlainText(glossary.get("prompt", ""))
            QMessageBox.information(self, self.tr("Glossary"), self.tr("Glossary imported."))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("Glossary"), self.tr("Failed to import glossary: ") + str(exc))

    def import_reference_glossary(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import Reference Glossary"),
            "",
            self.tr("Glossary JSON (*.json);;All Files (*)"),
        )
        if not path:
            return
        try:
            glossary = self._read_glossary_file(path)
            reference = "\n".join(
                part for part in (
                    glossary.get("entries", ""),
                    glossary.get("reference_entries", ""),
                ) if part
            )
            self.reference_editor.setPlainText(reference)
            if glossary.get("reference_prompt"):
                self.reference_prompt_editor.setPlainText(glossary.get("reference_prompt", ""))
            QMessageBox.information(self, self.tr("Glossary"), self.tr("Reference glossary imported."))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("Glossary"), self.tr("Failed to import reference glossary: ") + str(exc))

    def export_glossary(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export Glossary"),
            "glossary.json",
            self.tr("Glossary JSON (*.json);;All Files (*)"),
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf8") as f:
                json.dump(self.collect_glossary(), f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, self.tr("Glossary"), self.tr("Glossary exported."))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("Glossary"), self.tr("Failed to export glossary: ") + str(exc))

    def build_template_from_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("Choose Translated Manga Folder"),
            "",
        )
        if not folder:
            return
        try:
            glossary = build_glossary_from_translated_folder(
                folder,
                include_subfolders=self.include_subfolders.isChecked(),
            )
            entries = glossary.get("entries", "")
            if not entries:
                QMessageBox.information(
                    self,
                    self.tr("Glossary"),
                    self.tr("No glossary candidates found in the selected folder."),
                )
                return
            self.reference_editor.setPlainText(entries)
            QMessageBox.information(
                self,
                self.tr("Glossary"),
                self.tr("Reference glossary template created from translated folder."),
            )
        except Exception as exc:
            QMessageBox.warning(self, self.tr("Glossary"), self.tr("Failed to build glossary template: ") + str(exc))

    @staticmethod
    def _read_glossary_file(path: str) -> Dict[str, str]:
        with open(path, "r", encoding="utf8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object.")
        return {
            "entries": payload.get("entries", payload.get("glossary", "")) or "",
            "prompt": payload.get("prompt", "") or "",
            "reference_entries": payload.get("reference_entries", payload.get("reference", "")) or "",
            "reference_prompt": payload.get("reference_prompt", "") or "",
        }

    @staticmethod
    def parse_entries(text: str) -> List[Dict[str, str]]:
        return parse_glossary_entries(text)
