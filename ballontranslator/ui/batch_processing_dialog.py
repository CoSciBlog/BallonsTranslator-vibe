from __future__ import annotations

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
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ballontranslator.modules import (
    GET_VALID_INPAINTERS,
    GET_VALID_OCR,
    GET_VALID_TEXTDETECTORS,
    GET_VALID_TRANSLATORS,
)
from ballontranslator.utils.batch_processing import (
    BatchOptions,
    COMPLETION_CLOSE,
    COMPLETION_HIBERNATE,
    COMPLETION_NONE,
    COMPLETION_RESTART,
    COMPLETION_SHUTDOWN,
    GLOSSARY_GLOBAL,
    GLOSSARY_INDIVIDUAL,
    ORDER_PROJECT,
    ORDER_STAGED,
    collect_batch_project_dirs,
)
from ballontranslator.utils.config import pcfg
from ballontranslator.utils.llm_profiles import is_llm_text_translator


class BatchProcessingDialog(QDialog):
    """Collect a batch plan without loading projects or model modules.

    >>> BatchProcessingDialog.__name__
    'BatchProcessingDialog'
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr('Batch Processing'))
        self.setMinimumWidth(620)
        self._project_directories: list[str] = []
        self._scanned_directory: str | None = None

        root_layout = QVBoxLayout(self)
        self.folder_edit = QLineEdit(self)
        self.folder_edit.setClearButtonEnabled(True)
        self.folder_edit.setPlaceholderText(self.tr('Enter or paste a parent folder path'))
        folder_label = QLabel(self.tr('Select batch parent folder'), self)
        folder_label.setBuddy(self.folder_edit)
        root_layout.addWidget(folder_label)
        root_layout.addWidget(self.folder_edit)
        self.folder_button = QPushButton(self.tr('Select folder...'), self)
        self.folder_edit.setMinimumHeight(self.folder_button.sizeHint().height())
        self.folder_button.clicked.connect(self._select_folder)
        folder_layout = QHBoxLayout()
        self.project_count = QLabel(self.tr('No project folders selected.'), self)
        folder_layout.addWidget(self.project_count, 1)
        folder_layout.addWidget(self.folder_button)
        root_layout.addLayout(folder_layout)
        self.folder_edit.textChanged.connect(self._invalidate_project_directories)
        self.folder_edit.editingFinished.connect(self._update_project_directories)

        form = QFormLayout()
        self.detect_check, self.detect_combo = self._stage_row(
            self.tr('Text detector'), GET_VALID_TEXTDETECTORS(), pcfg.module.textdetector
        )
        form.addRow(self.detect_check, self.detect_combo)
        self.ocr_check, self.ocr_combo = self._stage_row(
            self.tr('OCR'), GET_VALID_OCR(), pcfg.module.ocr
        )
        form.addRow(self.ocr_check, self.ocr_combo)

        fallback_layout = QHBoxLayout()
        self.fallback_check = QCheckBox(self.tr('Use fallback OCR'), self)
        self.fallback_combo = QComboBox(self)
        self.fallback_combo.addItems(GET_VALID_OCR())
        fallback_layout.addWidget(self.fallback_check)
        fallback_layout.addWidget(self.fallback_combo, 1)
        self.fallback_check.toggled.connect(self.fallback_combo.setEnabled)
        self.fallback_combo.setEnabled(False)
        form.addRow(self.tr('OCR fallback'), fallback_layout)

        self.inpaint_check, self.inpaint_combo = self._stage_row(
            self.tr('Inpaint'), GET_VALID_INPAINTERS(), pcfg.module.inpainter
        )
        form.addRow(self.inpaint_check, self.inpaint_combo)
        self.reinpaint_check = QCheckBox(
            self.tr('Re-run inpainting for saved masks or maskless text regions'),
            self,
        )
        form.addRow(self.tr('Re-inpainting'), self.reinpaint_check)
        self.translate_check, self.translate_combo = self._stage_row(
            self.tr('Translation'), GET_VALID_TRANSLATORS(), pcfg.module.translator
        )
        form.addRow(self.translate_check, self.translate_combo)

        self.llm_profile_label = QLabel(self.tr('LLM profile'), self)
        self.llm_profile_combo = QComboBox(self)
        self.llm_profile_label.setBuddy(self.llm_profile_combo)
        for profile in pcfg.module.llm_profiles:
            if not profile.support_text:
                continue
            label = profile.name or profile.id
            if profile.model:
                label = f'{label} — {profile.model}'
            self.llm_profile_combo.addItem(label, profile.id)
        selected_profile = self.llm_profile_combo.findData(
            pcfg.module.translator_llm_id
        )
        if selected_profile >= 0:
            self.llm_profile_combo.setCurrentIndex(selected_profile)
        self.llm_profile_combo.setToolTip(self.tr(
            'LLM profile used for every translated project in this batch.'
        ))
        form.addRow(self.llm_profile_label, self.llm_profile_combo)
        self.translate_combo.currentTextChanged.connect(
            self._sync_llm_profile_row
        )
        self.translate_check.toggled.connect(self._sync_llm_profile_row)
        self._sync_llm_profile_row()

        self.glossary_combo = QComboBox(self)
        self.glossary_combo.addItem(self.tr('Individual glossary per project'), GLOSSARY_INDIVIDUAL)
        self.glossary_combo.addItem(self.tr('One global glossary for the batch'), GLOSSARY_GLOBAL)
        form.addRow(self.tr('Glossary'), self.glossary_combo)

        self.upscale_check = QCheckBox(self.tr('Upscale images 2x before processing'), self)
        form.addRow(self.tr('Upscaling'), self.upscale_check)

        self.order_combo = QComboBox(self)
        self.order_combo.addItem(
            self.tr('Complete every project before starting the next'),
            ORDER_PROJECT,
        )
        self.order_combo.addItem(
            self.tr('Local stages for all projects, then translation for all'),
            ORDER_STAGED,
        )
        form.addRow(self.tr('Processing order'), self.order_combo)

        self.resume_check = QCheckBox(
            self.tr('Continue saved progress after an interrupted batch'),
            self,
        )
        self.resume_check.setChecked(True)
        self.resume_check.setToolTip(self.tr(
            'Skip saved completed pages and completed batch tasks from a '
            'matching interrupted run. Disable this to process everything again.'
        ))
        form.addRow(self.tr('Resume'), self.resume_check)

        self.completion_combo = QComboBox(self)
        for label, value in (
            (self.tr('Do nothing'), COMPLETION_NONE),
            (self.tr('Hibernate computer'), COMPLETION_HIBERNATE),
            (self.tr('Shut down computer'), COMPLETION_SHUTDOWN),
            (self.tr('Restart computer'), COMPLETION_RESTART),
            (self.tr('Close BallonsTranslator'), COMPLETION_CLOSE),
        ):
            self.completion_combo.addItem(label, value)
        form.addRow(self.tr('After completion'), self.completion_combo)
        root_layout.addLayout(form)

        note = QLabel(
            self.tr(
                'Only direct child folders containing images are processed. '
                'Upscaling finishes for every project before other stages start. '
                'Ignored pages are upscaled but remain excluded from the pipeline.'
            ),
            self,
        )
        note.setWordWrap(True)
        root_layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr('Start batch'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root_layout.addWidget(buttons)

    def _stage_row(self, label: str, options, current: str):
        checker = QCheckBox(label, self)
        checker.setChecked(True)
        combo = QComboBox(self)
        combo.addItems(options)
        combo.setCurrentText(current)
        checker.toggled.connect(combo.setEnabled)
        return checker, combo

    def _sync_llm_profile_row(self, *_args) -> None:
        visible = (
            self.translate_check.isChecked()
            and is_llm_text_translator(self.translate_combo.currentText())
        )
        self.llm_profile_label.setVisible(visible)
        self.llm_profile_combo.setVisible(visible)
        self.llm_profile_combo.setEnabled(
            visible and self.llm_profile_combo.count() > 0
        )

    def _select_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            self.tr('Select batch parent folder'),
            self.folder_edit.text(),
        )
        if not directory:
            return
        self.folder_edit.setText(directory)
        self._update_project_directories()

    def _invalidate_project_directories(self) -> None:
        self._scanned_directory = None
        self._project_directories = []
        self.project_count.setText(self.tr('No project folders selected.'))

    def _update_project_directories(self) -> None:
        # Windows "Copy as path" adds quotes. Normalize only at commit time so
        # typing stays uninterrupted and invalid edits cannot reuse old projects.
        directory = self.folder_edit.text().strip().strip('"')
        self.folder_edit.setText(directory)
        if directory == self._scanned_directory:
            return
        self._project_directories = collect_batch_project_dirs(directory)
        self._scanned_directory = directory
        self.project_count.setText(
            self.tr('{count} direct project folder(s) found.').format(
                count=len(self._project_directories)
            )
        )

    def accept(self) -> None:
        self._update_project_directories()
        if not self._project_directories:
            QMessageBox.warning(
                self,
                self.tr('Batch Processing'),
                self.tr('Select a folder containing image-bearing project folders.'),
            )
            return
        if not any((
            self.detect_check.isChecked(),
            self.ocr_check.isChecked(),
            self.inpaint_check.isChecked(),
            self.translate_check.isChecked(),
            self.reinpaint_check.isChecked(),
        )):
            QMessageBox.warning(
                self,
                self.tr('Batch Processing'),
                self.tr('Enable at least one pipeline stage.'),
            )
            return
        if (
            self.translate_check.isChecked()
            and is_llm_text_translator(self.translate_combo.currentText())
            and not self.llm_profile_combo.currentData()
        ):
            QMessageBox.warning(
                self,
                self.tr('Batch Processing'),
                self.tr('Select an LLM profile for batch translation.'),
            )
            return
        if (
            self.fallback_check.isChecked()
            and self.fallback_combo.currentText() == self.ocr_combo.currentText()
        ):
            QMessageBox.warning(
                self,
                self.tr('Batch Processing'),
                self.tr('Fallback OCR must differ from the primary OCR module.'),
            )
            return
        super().accept()

    def options(self) -> BatchOptions:
        return BatchOptions(
            root_directory=self.folder_edit.text(),
            textdetector=self.detect_combo.currentText(),
            ocr=self.ocr_combo.currentText(),
            fallback_ocr=(
                self.fallback_combo.currentText()
                if self.fallback_check.isChecked() and self.ocr_check.isChecked()
                else ''
            ),
            inpainter=self.inpaint_combo.currentText(),
            translator=self.translate_combo.currentText(),
            translator_llm_id=(
                str(self.llm_profile_combo.currentData() or '')
                if self.translate_check.isChecked()
                and is_llm_text_translator(self.translate_combo.currentText())
                else ''
            ),
            enable_detect=self.detect_check.isChecked(),
            enable_ocr=self.ocr_check.isChecked(),
            enable_inpaint=self.inpaint_check.isChecked(),
            enable_translate=self.translate_check.isChecked(),
            glossary_mode=self.glossary_combo.currentData(),
            upscale_first=self.upscale_check.isChecked(),
            rerun_inpaint=self.reinpaint_check.isChecked(),
            order=self.order_combo.currentData(),
            completion_action=self.completion_combo.currentData(),
            resume=self.resume_check.isChecked(),
        )

    @property
    def project_directories(self) -> list[str]:
        return list(self._project_directories)
