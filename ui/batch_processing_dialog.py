import os.path as osp
from dataclasses import dataclass

from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from modules import GET_VALID_INPAINTERS, GET_VALID_OCR, GET_VALID_TEXTDETECTORS, GET_VALID_TRANSLATORS
from utils.batch_processing import collect_batch_project_dirs
from utils.config import pcfg


@dataclass
class BatchProcessingOptions:
    root_dir: str
    project_dirs: list
    textdetector: str
    ocr: str
    inpainter: str
    translator: str
    enable_detect: bool
    enable_ocr: bool
    enable_inpaint: bool
    enable_translate: bool
    export_enabled: bool
    export_ext: str
    quit_when_finished: bool


class BatchProcessingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('Batch Processing'))
        self.setMinimumWidth(560)

        self.root_edit = QLineEdit()
        self.root_edit.setReadOnly(True)
        self.root_edit.textChanged.connect(self.update_project_count)
        browse_btn = QPushButton(self.tr('Select Folder...'))
        browse_btn.clicked.connect(self.select_root_dir)

        root_layout = QHBoxLayout()
        root_layout.addWidget(self.root_edit)
        root_layout.addWidget(browse_btn)

        self.project_count_label = QLabel(self.tr('No batch folder selected.'))

        self.detect_check = QCheckBox(self.tr('Text detection'))
        self.ocr_check = QCheckBox(self.tr('OCR'))
        self.inpaint_check = QCheckBox(self.tr('Inpainting'))
        self.translate_check = QCheckBox(self.tr('Translation'))
        self.detect_check.setChecked(pcfg.module.enable_detect)
        self.ocr_check.setChecked(pcfg.module.enable_ocr)
        self.inpaint_check.setChecked(pcfg.module.enable_inpaint)
        self.translate_check.setChecked(pcfg.module.enable_translate)

        self.textdet_combo = self._combo(GET_VALID_TEXTDETECTORS(), pcfg.module.textdetector)
        self.ocr_combo = self._combo(GET_VALID_OCR(), pcfg.module.ocr)
        self.inpaint_combo = self._combo(GET_VALID_INPAINTERS(), pcfg.module.inpainter)
        self.translator_combo = self._combo(GET_VALID_TRANSLATORS(), pcfg.module.translator)

        self.export_check = QCheckBox(self.tr('Export each finished project'))
        self.export_combo = QComboBox()
        self.export_combo.addItems(['.cbz', '.pdf'])
        self.export_combo.setEnabled(False)
        self.export_check.toggled.connect(self.export_combo.setEnabled)

        self.quit_check = QCheckBox(self.tr('Quit application when finished'))

        form = QFormLayout()
        form.addRow(self.tr('Batch folder'), root_layout)
        form.addRow('', self.project_count_label)
        form.addRow(self.detect_check, self.textdet_combo)
        form.addRow(self.ocr_check, self.ocr_combo)
        form.addRow(self.inpaint_check, self.inpaint_combo)
        form.addRow(self.translate_check, self.translator_combo)
        form.addRow(self.export_check, self.export_combo)
        form.addRow('', self.quit_check)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    def _combo(self, values, current):
        combo = QComboBox()
        combo.addItems(values)
        if current in values:
            combo.setCurrentText(current)
        return combo

    def select_root_dir(self):
        start_dir = self.root_edit.text()
        if not osp.isdir(start_dir):
            recent = getattr(pcfg, 'recent_proj_list', [])
            start_dir = ''
            for path in recent:
                if osp.isdir(path):
                    start_dir = osp.dirname(path)
                    break
        selected = QFileDialog.getExistingDirectory(self, self.tr('Select Batch Folder'), start_dir)
        if selected:
            self.root_edit.setText(selected)

    def update_project_count(self):
        project_dirs = collect_batch_project_dirs(self.root_edit.text())
        if project_dirs:
            self.project_count_label.setText(
                self.tr('{count} project folders will be processed.').format(count=len(project_dirs))
            )
        else:
            self.project_count_label.setText(
                self.tr('No project folders with images found. Generated folders are ignored.')
            )

    def accept(self):
        if not self.options().project_dirs:
            self.project_count_label.setText(
                self.tr('Select a folder containing image project subfolders before starting.')
            )
            return
        super().accept()

    def options(self) -> BatchProcessingOptions:
        root_dir = self.root_edit.text()
        return BatchProcessingOptions(
            root_dir=root_dir,
            project_dirs=collect_batch_project_dirs(root_dir),
            textdetector=self.textdet_combo.currentText(),
            ocr=self.ocr_combo.currentText(),
            inpainter=self.inpaint_combo.currentText(),
            translator=self.translator_combo.currentText(),
            enable_detect=self.detect_check.isChecked(),
            enable_ocr=self.ocr_check.isChecked(),
            enable_inpaint=self.inpaint_check.isChecked(),
            enable_translate=self.translate_check.isChecked(),
            export_enabled=self.export_check.isChecked(),
            export_ext=self.export_combo.currentText(),
            quit_when_finished=self.quit_check.isChecked(),
        )
