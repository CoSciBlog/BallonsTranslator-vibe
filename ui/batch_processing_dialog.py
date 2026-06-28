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
    QDoubleSpinBox,
    QSpinBox,
    QVBoxLayout,
)

from modules import GET_VALID_INPAINTERS, GET_VALID_OCR, GET_VALID_TEXTDETECTORS, GET_VALID_TRANSLATORS
from modules.translators.base import LANGUAGE_ENGLISH_NAMES, lang_display_label, lang_display_to_key
from utils.batch_processing import collect_batch_project_dirs
from utils.batch_completion import (
    COMPLETION_ACTION_CUSTOM,
    COMPLETION_ACTION_HIBERNATE,
    COMPLETION_ACTION_NONE,
    COMPLETION_ACTION_RESTART,
    COMPLETION_ACTION_SHUTDOWN,
    COMPLETION_ACTION_SLEEP,
)
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
    skip_translated_pages: bool
    skip_finished_projects: bool
    upscale_enabled: bool
    upscale_factor: float
    upscale_max_long_edge: int
    upscale_skip_if_long_edge_above: int
    upscale_quality: str
    upscale_artifact_reduction: str
    source_language: str
    target_language: str
    ocr_fallback_enabled: bool
    ocr_fallback: str
    reinpaint_enabled: bool
    completion_action: str
    completion_command: str


class BatchProcessingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('Batch Processing'))
        self.setMinimumWidth(680)

        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText(self.tr('Enter one or more folders separated by semicolons or new lines.'))
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
        self.ocr_fallback_check = QCheckBox(self.tr('Fallback OCR when no text is recognized'))
        fallback_ocr = 'mit48px' if 'mit48px' in GET_VALID_OCR() else pcfg.module.ocr
        self.ocr_fallback_combo = self._combo(GET_VALID_OCR(), fallback_ocr)
        self.ocr_fallback_combo.setEnabled(False)
        self.ocr_fallback_check.toggled.connect(self.ocr_fallback_combo.setEnabled)

        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        for language in LANGUAGE_ENGLISH_NAMES:
            label = lang_display_label(language)
            self.source_combo.addItem(label, language)
            self.target_combo.addItem(label, language)
        self._set_language_combo(self.source_combo, pcfg.module.translate_source)
        self._set_language_combo(self.target_combo, pcfg.module.translate_target)

        self.skip_pages_check = QCheckBox(self.tr('Skip pages already processed by the pipeline'))
        self.skip_projects_check = QCheckBox(self.tr('Skip projects whose pages are already processed'))
        self.reinpaint_check = QCheckBox(self.tr('Re-run inpainting after each project'))
        self.reinpaint_check.setToolTip(self.tr(
            'After a project finishes, apply saved inpaint and censor masks again to the current inpainted pages. '
            'This can clean up remaining text edges before export, but adds another inpainting pass.'
        ))
        self.reinpaint_check.setChecked(False)
        self.reinpaint_check.setEnabled(self.inpaint_check.isChecked())
        self.inpaint_check.toggled.connect(self.reinpaint_check.setEnabled)
        self.inpaint_check.toggled.connect(lambda enabled: self.reinpaint_check.setChecked(False) if not enabled else None)

        self.upscale_check = QCheckBox(self.tr('Upscale and replace original pages before processing'))
        self.upscale_factor = QDoubleSpinBox()
        self.upscale_factor.setRange(1.0, 8.0)
        self.upscale_factor.setSingleStep(0.5)
        self.upscale_factor.setValue(float(pcfg.upscale_factor))
        self.upscale_quality = self._combo(['fast', 'balanced', 'quality', 'animesharp'], pcfg.upscale_quality)
        self.upscale_artifact_reduction = self._combo(
            ['off', 'light', 'medium', 'strong'], pcfg.upscale_artifact_reduction
        )
        self.upscale_max_edge = QSpinBox()
        self.upscale_max_edge.setRange(0, 100000)
        self.upscale_max_edge.setValue(int(pcfg.upscale_max_long_edge))
        self.upscale_skip_edge = QSpinBox()
        self.upscale_skip_edge.setRange(0, 100000)
        self.upscale_skip_edge.setValue(int(pcfg.upscale_skip_if_long_edge_above))
        upscale_widgets = [
            self.upscale_factor,
            self.upscale_quality,
            self.upscale_artifact_reduction,
            self.upscale_max_edge,
            self.upscale_skip_edge,
        ]
        for widget in upscale_widgets:
            widget.setEnabled(False)
        self.upscale_check.toggled.connect(lambda enabled: [widget.setEnabled(enabled) for widget in upscale_widgets])

        self.export_check = QCheckBox(self.tr('Export each finished project'))
        self.export_combo = QComboBox()
        self.export_combo.addItems(['.cbz', '.pdf'])
        self.export_combo.setEnabled(False)
        self.export_check.toggled.connect(self.export_combo.setEnabled)

        self.quit_check = QCheckBox(self.tr('Quit application when finished'))

        self.completion_action_combo = QComboBox()
        self.completion_action_combo.addItem(self.tr('Do nothing'), COMPLETION_ACTION_NONE)
        self.completion_action_combo.addItem(self.tr('Shut down PC'), COMPLETION_ACTION_SHUTDOWN)
        self.completion_action_combo.addItem(self.tr('Restart PC'), COMPLETION_ACTION_RESTART)
        self.completion_action_combo.addItem(self.tr('Hibernate'), COMPLETION_ACTION_HIBERNATE)
        self.completion_action_combo.addItem(self.tr('Sleep'), COMPLETION_ACTION_SLEEP)
        self.completion_action_combo.addItem(self.tr('Run custom command/program'), COMPLETION_ACTION_CUSTOM)
        self.completion_command_edit = QLineEdit()
        self.completion_command_edit.setPlaceholderText(
            self.tr('Program path or command to run after batch completion')
        )
        self.completion_command_edit.setEnabled(False)
        self.completion_action_combo.currentIndexChanged.connect(self._update_completion_command_state)

        form = QFormLayout()
        form.addRow(self.tr('Batch folder'), root_layout)
        form.addRow('', self.project_count_label)
        form.addRow(self.detect_check, self.textdet_combo)
        form.addRow(self.ocr_check, self.ocr_combo)
        form.addRow(self.ocr_fallback_check, self.ocr_fallback_combo)
        form.addRow(self.inpaint_check, self.inpaint_combo)
        form.addRow(self.translate_check, self.translator_combo)
        form.addRow(self.tr('Source language'), self.source_combo)
        form.addRow(self.tr('Target language'), self.target_combo)
        form.addRow('', self.skip_pages_check)
        form.addRow('', self.skip_projects_check)
        form.addRow('', self.reinpaint_check)
        form.addRow('', self.upscale_check)
        form.addRow(self.tr('Upscale factor'), self.upscale_factor)
        form.addRow(self.tr('Upscale quality'), self.upscale_quality)
        form.addRow(self.tr('Compression artifact cleanup'), self.upscale_artifact_reduction)
        form.addRow(self.tr('Maximum long edge after upscale (0 = unlimited)'), self.upscale_max_edge)
        form.addRow(self.tr('Skip upscale above long edge (0 = never)'), self.upscale_skip_edge)
        form.addRow(self.export_check, self.export_combo)
        form.addRow('', self.quit_check)
        form.addRow(self.tr('After batch finishes'), self.completion_action_combo)
        form.addRow(self.tr('Command/program'), self.completion_command_edit)

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

    def _set_language_combo(self, combo: QComboBox, language: str):
        index = combo.findData(language)
        if index < 0:
            index = combo.findText(lang_display_label(language))
        if index >= 0:
            combo.setCurrentIndex(index)

    def _update_completion_command_state(self):
        self.completion_command_edit.setEnabled(
            self.completion_action_combo.currentData() == COMPLETION_ACTION_CUSTOM
        )

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
            entered = self.root_edit.text().strip()
            self.root_edit.setText(f'{entered}; {selected}' if entered else selected)

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
                self.tr('Enter or select one or more folders containing source images before starting.')
            )
            return
        if (
            self.completion_action_combo.currentData() == COMPLETION_ACTION_CUSTOM
            and not self.completion_command_edit.text().strip()
        ):
            self.completion_command_edit.setFocus()
            self.completion_command_edit.setPlaceholderText(
                self.tr('Enter a command or program path before starting.')
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
            skip_translated_pages=self.skip_pages_check.isChecked(),
            skip_finished_projects=self.skip_projects_check.isChecked(),
            upscale_enabled=self.upscale_check.isChecked(),
            upscale_factor=self.upscale_factor.value(),
            upscale_max_long_edge=self.upscale_max_edge.value(),
            upscale_skip_if_long_edge_above=self.upscale_skip_edge.value(),
            upscale_quality=self.upscale_quality.currentText(),
            upscale_artifact_reduction=self.upscale_artifact_reduction.currentText(),
            source_language=lang_display_to_key(self.source_combo.currentText()),
            target_language=lang_display_to_key(self.target_combo.currentText()),
            ocr_fallback_enabled=self.ocr_fallback_check.isChecked(),
            ocr_fallback=self.ocr_fallback_combo.currentText(),
            reinpaint_enabled=self.reinpaint_check.isChecked(),
            completion_action=self.completion_action_combo.currentData(),
            completion_command=self.completion_command_edit.text().strip(),
        )
