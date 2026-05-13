import re
from typing import Dict, List

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QStandardItem, QStandardItemModel
from qtpy.QtWidgets import (
    QDialog,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTableView,
    QVBoxLayout,
)

from .custom_widget import NoBorderPushBtn


class GlossaryWindow(QDialog):
    saved = Signal(dict)

    HEADERS = ("Source", "Target", "Category", "Note")

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(self.tr("Project Glossary"))
        self.setModal(False)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)
        self.project_glossary = {"entries": "", "prompt": ""}
        self._loading = False

        self.info_label = QLabel(
            self.tr("Glossary entries saved in the current project's imgtrans JSON.")
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

        self.new_btn = NoBorderPushBtn(self.tr("New"), self)
        self.new_btn.setToolTip(self.tr("Add an empty glossary entry."))
        self.new_btn.clicked.connect(self.add_empty_row)
        self.del_btn = NoBorderPushBtn(self.tr("Delete"), self)
        self.del_btn.setToolTip(self.tr("Delete selected glossary entries."))
        self.del_btn.clicked.connect(self.delete_selected_rows)
        self.save_btn = NoBorderPushBtn(self.tr("Save Glossary"), self)
        self.save_btn.setToolTip(self.tr("Save the glossary into the current project's imgtrans JSON."))
        self.save_btn.clicked.connect(self.save_glossary)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        layout.addWidget(self.table)
        layout.addWidget(self.new_btn)
        layout.addWidget(self.del_btn)
        layout.addWidget(self.prompt_label)
        layout.addWidget(self.prompt_editor)
        layout.addWidget(self.save_btn)
        self.setMinimumSize(760, 520)

    def load_glossary(self, glossary: Dict[str, str]):
        self._loading = True
        self.project_glossary = dict(glossary or {})
        self.model.removeRows(0, self.model.rowCount())
        for entry in self.parse_entries(self.project_glossary.get("entries", "")):
            self.add_row(entry, save=False)
        self.prompt_editor.setPlainText(self.project_glossary.get("prompt", ""))
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
        }

    def save_glossary(self):
        self.project_glossary = self.collect_glossary()
        self.saved.emit(dict(self.project_glossary))

    @staticmethod
    def parse_entries(text: str) -> List[Dict[str, str]]:
        entries = []
        for line in (text or "").splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#") or "=>" not in clean:
                continue
            source, rest = [part.strip() for part in clean.split("=>", 1)]
            note = ""
            if "#" in rest:
                rest, note = [part.strip() for part in rest.split("#", 1)]
            category = "term"
            category_match = re.search(r"\[([^\]]+)\]\s*$", rest)
            if category_match:
                category = category_match.group(1).strip() or "term"
                rest = rest[: category_match.start()].strip()
            entries.append(
                {
                    "source": source,
                    "target": rest,
                    "category": category,
                    "note": note,
                }
            )
        return entries
