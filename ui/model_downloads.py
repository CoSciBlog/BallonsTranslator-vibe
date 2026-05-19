from typing import List, Tuple

from qtpy.QtCore import Qt, Signal, QThread
from qtpy.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from modules.prepare_local_files import (
    download_module_files,
    get_downloadable_model_entries,
)
from utils.logger import logger as LOGGER


CHECKED = Qt.CheckState.Checked if hasattr(Qt, "CheckState") else Qt.Checked
UNCHECKED = Qt.CheckState.Unchecked if hasattr(Qt, "CheckState") else Qt.Unchecked
USER_ROLE = Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole
ITEM_IS_USER_CHECKABLE = Qt.ItemFlag.ItemIsUserCheckable if hasattr(Qt, "ItemFlag") else Qt.ItemIsUserCheckable


class ModelDownloadWorker(QThread):
    status_changed = Signal(str)
    module_finished = Signal(str, str, bool)
    finished_all = Signal()

    def __init__(self, tasks: List[Tuple[str, str, type]], parent=None) -> None:
        super().__init__(parent)
        self.tasks = tasks

    def run(self) -> None:
        for category, key, module_class in self.tasks:
            label = f"{category}/{key}"
            self.status_changed.emit(f"Downloading {label} ...")
            try:
                ok = download_module_files(module_class)
            except Exception:
                LOGGER.exception("Model download failed for %s", label)
                ok = False
            self.module_finished.emit(category, key, ok)
        self.status_changed.emit("Model download task finished.")
        self.finished_all.emit()


class ModelDownloadWindow(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Model Downloads"))
        self.resize(680, 460)
        self.worker = None

        self.status_label = QLabel(self.tr("Select models to download."))
        self.list_widget = QListWidget(self)

        self.refresh_button = QPushButton(self.tr("Refresh"))
        self.download_selected_button = QPushButton(self.tr("Download Selected"))
        self.download_all_button = QPushButton(self.tr("Download All"))
        self.close_button = QPushButton(self.tr("Close"))

        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_button)
        buttons.addStretch(1)
        buttons.addWidget(self.download_selected_button)
        buttons.addWidget(self.download_all_button)
        buttons.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Available local models")))
        layout.addWidget(self.list_widget)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)

        self.refresh_button.clicked.connect(self.refresh)
        self.download_selected_button.clicked.connect(self.download_selected)
        self.download_all_button.clicked.connect(self.download_all)
        self.close_button.clicked.connect(self.close)
        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        for entry in get_downloadable_model_entries():
            state = self.tr("installed") if entry["ready"] else self.tr("missing")
            if not entry.get("downloadable", True):
                state = self.tr("runtime")
            optional = self.tr("optional") if entry["optional_startup"] else self.tr("startup")
            label = f"{entry['category']}/{entry['key']} - {state} - {optional}"
            if entry.get("note"):
                label = f"{label} - {entry['note']}"
            item = QListWidgetItem(label)
            if entry.get("downloadable", True):
                item.setCheckState(UNCHECKED if entry["ready"] else CHECKED)
            else:
                item.setFlags(item.flags() & ~ITEM_IS_USER_CHECKABLE)
            item.setData(USER_ROLE, entry)
            self.list_widget.addItem(item)

    def selected_tasks(self, include_installed: bool = False) -> List[Tuple[str, str, type]]:
        tasks = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.checkState() != CHECKED:
                continue
            entry = item.data(USER_ROLE)
            if not include_installed and entry["ready"]:
                continue
            if not entry.get("downloadable", True):
                continue
            tasks.append((entry["category"], entry["key"], entry["module_class"]))
        return tasks

    def download_selected(self) -> None:
        self.start_download(self.selected_tasks())

    def download_all(self) -> None:
        tasks = [
            (entry["category"], entry["key"], entry["module_class"])
            for entry in get_downloadable_model_entries()
            if entry.get("downloadable", True) and not entry["ready"]
        ]
        self.start_download(tasks)

    def start_download(self, tasks: List[Tuple[str, str, type]]) -> None:
        if not tasks:
            self.status_label.setText(self.tr("No missing selected models."))
            return
        self.set_buttons_enabled(False)
        self.worker = ModelDownloadWorker(tasks, self)
        self.worker.status_changed.connect(self.status_label.setText)
        self.worker.module_finished.connect(self.on_module_finished)
        self.worker.finished_all.connect(self.on_finished_all)
        self.worker.start()

    def on_module_finished(self, category: str, key: str, ok: bool) -> None:
        state = self.tr("downloaded") if ok else self.tr("failed")
        self.status_label.setText(f"{category}/{key}: {state}")

    def on_finished_all(self) -> None:
        self.set_buttons_enabled(True)
        self.refresh()

    def set_buttons_enabled(self, enabled: bool) -> None:
        self.refresh_button.setEnabled(enabled)
        self.download_selected_button.setEnabled(enabled)
        self.download_all_button.setEnabled(enabled)
        self.close_button.setEnabled(enabled)

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.status_label.setText(self.tr("Downloads are still running. Wait for them to finish before closing."))
            event.ignore()
            return
        super().closeEvent(event)
