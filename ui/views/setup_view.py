from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, 
    QFileDialog, QMessageBox, QLabel, QGroupBox, QComboBox, QCheckBox, QLayout
)
from PySide6.QtCore import Qt, Signal
from typing import Optional, List, Dict, Any
import os
import shutil
import dataclasses
import torch

from core.state import AppState
from utils.text_processor import TextPreprocessor
from core.services.project_service import ProjectService
from core.services.template_service import TemplateService

class SetupView(QWidget):
    template_loaded = Signal()
    session_updated = Signal() # New: Emitted when sentences/session data changes

    def __init__(self, app_state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = app_state
        self.processor = TextPreprocessor()
        self.project_service = ProjectService()
        self.template_service = TemplateService()
        
        self.setup_ui()
        self.populate_templates()
        self.check_system()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.setup_header(layout)
        self.setup_session_controls(layout)
        self.setup_processing_controls(layout)
        self.setup_key_params(layout) # Restored
        self.setup_voice_controls(layout)
        self.setup_main_controls(layout)
        self.setup_system_check(layout)
        layout.addStretch()

    def setup_header(self, layout: QVBoxLayout) -> None:
        # --- Session Header ---
        header_layout = QHBoxLayout()
        header = QLabel("Session & Source")
        font = header.font()
        font.setPointSize(14)
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)
        header_layout.addStretch()
        
        # Session Btns
        new_btn = QPushButton("New Session")
        new_btn.clicked.connect(self.new_session)
        load_btn = QPushButton("Load Session")
        load_btn.clicked.connect(self.load_session_dialog)
        header_layout.addWidget(new_btn)
        header_layout.addWidget(load_btn)
        layout.addLayout(header_layout)

    def setup_session_controls(self, layout: QVBoxLayout) -> None:
        form_layout = QFormLayout()
        
        # Session Name
        self.session_name_edit = QLineEdit()
        self.session_name_edit.setPlaceholderText("My Audiobook Project")
        self.session_name_edit.textChanged.connect(lambda t: setattr(self.state, 'session_name', t))
        form_layout.addRow("Session Name:", self.session_name_edit)
        
        # Source Text File
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_btn = QPushButton("Browse...")
        self.file_btn.clicked.connect(self.browse_file)
        
        file_layout = QHBoxLayout()
        file_layout.addWidget(self.file_path_edit)
        file_layout.addWidget(self.file_btn)
        form_layout.addRow("Source Text:", file_layout)
        
        layout.addLayout(form_layout)


    def setup_processing_controls(self, layout: QVBoxLayout) -> None:
        # Edit & Process Button (Consolidated Workflow)
        self.edit_btn = QPushButton("Edit Source Text")
        self.edit_btn.setToolTip("Opens file in external editor, then reloads")
        self.edit_btn.setStyleSheet("background-color: #2E86C1; color: white; padding: 10px; font-weight: bold;")
        self.edit_btn.clicked.connect(self.open_editor_and_process)
        layout.addWidget(self.edit_btn)
        
        # Aggro Clean Switch
        self.aggro_chk = QCheckBox("Remove all special characters on processing")
        self.aggro_chk.setChecked(self.state.aggro_clean_on_parse)
        self.aggro_chk.stateChanged.connect(
            lambda s: setattr(self.state, 'aggro_clean_on_parse', s == Qt.Checked or s == 2)
        )
        layout.addWidget(self.aggro_chk)
        
    def setup_key_params(self, layout: QVBoxLayout) -> None:
        """Restores the 'Key Parameters (Loaded)' display from Reference."""
        group = QGroupBox("Key Parameters (Summary)")
        f_layout = QFormLayout(group)
        
        self.lbl_ref_audio = QLabel("--")
        self.lbl_exaggeration = QLabel("--")
        self.lbl_temp = QLabel("--")
        
        f_layout.addRow("Reference Audio:", self.lbl_ref_audio)
        f_layout.addRow("Exaggeration:", self.lbl_exaggeration)
        f_layout.addRow("Temperature:", self.lbl_temp)
        
        # Edit Button to jump to Generation Tab? (Optional, kept simpler for now)
        layout.addWidget(group)
        
    def refresh_params_display(self) -> None:
        """Updates the Parameter labels from AppState."""
        # Ref Audio
        ref = self.state.ref_audio_path
        self.lbl_ref_audio.setText(os.path.basename(ref) if ref else "None")
        if ref: self.lbl_ref_audio.setToolTip(ref)
            
        # Settings
        s = self.state.settings
        self.lbl_exaggeration.setText(f"{s.exaggeration:.2f}")
        self.lbl_temp.setText(f"{s.temperature:.2f}")

    def showEvent(self, event) -> None:
        """Auto-refresh on tab show."""
        self.refresh_params_display()
        super().showEvent(event)

    def setup_voice_controls(self, layout: QVBoxLayout) -> None:
        tpl_group = QGroupBox("Generation Voices")
        t_layout = QHBoxLayout(tpl_group)
        self.template_combo = QComboBox()
        self.template_combo.addItems(["No voices found"]) 
        
        self.load_tpl_btn = QPushButton("Load Voice")
        self.load_tpl_btn.clicked.connect(self.load_template)
        
        self.del_tpl_btn = QPushButton("Delete Voice")
        self.del_tpl_btn.setStyleSheet("background-color: #A93226; color: white; font-weight: bold;")
        self.del_tpl_btn.clicked.connect(self.delete_template)
        
        t_layout.addWidget(QLabel("Select Voice:"))
        t_layout.addWidget(self.template_combo, stretch=1)
        t_layout.addWidget(self.load_tpl_btn)
        t_layout.addWidget(self.del_tpl_btn)
        layout.addWidget(tpl_group)

    def setup_main_controls(self, layout: QVBoxLayout) -> None:
        ctrl_group = QGroupBox("Main Controls")
        c_layout = QVBoxLayout(ctrl_group)
        
        # Auto Assemble
        self.auto_asm_chk = QCheckBox("Re-Assemble After Full Run")
        self.auto_asm_chk.setChecked(self.state.auto_assemble_after_run)
        self.auto_asm_chk.stateChanged.connect(
            lambda s: setattr(self.state, 'auto_assemble_after_run', s == Qt.Checked or s == 2)
        )
        c_layout.addWidget(self.auto_asm_chk)

        # Auto Regen
        self.auto_reg_chk = QCheckBox("Continue to Regenerate until all files pass")
        self.auto_reg_chk.setChecked(self.state.auto_regen_main)
        self.auto_reg_chk.stateChanged.connect(
            lambda s: setattr(self.state, 'auto_regen_main', s == Qt.Checked or s == 2)
        )
        c_layout.addWidget(self.auto_reg_chk)

        # Dual GPU Checkbox (Conditional)
        try:
             gpu_count = torch.cuda.device_count()
        except:
             gpu_count = 0
             
        if gpu_count >= 2:
            self.dual_gpu_chk = QCheckBox(f"Use Both GPUs ({gpu_count} detected)")
            is_dual = "," in self.state.settings.target_gpus
            self.dual_gpu_chk.setChecked(is_dual)
            self.dual_gpu_chk.stateChanged.connect(self.toggle_dual_gpu)
            c_layout.addWidget(self.dual_gpu_chk)

        self.start_btn = QPushButton("Start Generation")
        self.start_btn.setStyleSheet("background-color: #27AE60; color: white; font-size: 14px; font-weight: bold; padding: 10px;")
        self.start_btn.clicked.connect(self.toggle_generation)
        c_layout.addWidget(self.start_btn)
        
        layout.addWidget(ctrl_group)

    def setup_system_check(self, layout: QVBoxLayout) -> None:
        sys_group = QGroupBox("System Check")
        s_layout = QFormLayout(sys_group)
        self.lbl_ffmpeg = QLabel("Checking...")
        self.lbl_auto = QLabel("Checking...")
        self.lbl_gpu = QLabel("Checking...")
        
        s_layout.addRow("FFmpeg:", self.lbl_ffmpeg)
        s_layout.addRow("Auto-Editor:", self.lbl_auto)
        s_layout.addRow("GPU Mode:", self.lbl_gpu)
        
        layout.addWidget(sys_group)

    def check_system(self) -> None:
        ffmpeg = shutil.which('ffmpeg')
        self.lbl_ffmpeg.setText("Found" if ffmpeg else "Not Found (Required)")
        self.lbl_ffmpeg.setStyleSheet("color: green" if ffmpeg else "color: red")
        
        ae = shutil.which('auto-editor')
        self.lbl_auto.setText("Found" if ae else "Not Found (Optional)")
        self.lbl_auto.setStyleSheet("color: green" if ae else "color: orange")

        try:
            if torch.cuda.is_available():
                count = torch.cuda.device_count()
                name = torch.cuda.get_device_name(0)
                mode = "Dual GPU" if count > 1 and "cuda:0,cuda:1" in self.state.settings.target_gpus else "Single GPU"
                self.lbl_gpu.setText(f"{mode} ({count} devices) - {name}")
                self.lbl_gpu.setStyleSheet("color: green")
            else:
                self.lbl_gpu.setText("CPU Mode (No CUDA found)")
                self.lbl_gpu.setStyleSheet("color: orange")
        except:
             self.lbl_gpu.setText("Error Checking GPU")
             self.lbl_gpu.setStyleSheet("color: red")

    def toggle_dual_gpu(self, state: int) -> None:
        if state == Qt.Checked or state == 2:
            self.state.settings.target_gpus = "cuda:0,cuda:1"
        else:
            self.state.settings.target_gpus = "cuda:0"

    def browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Text Source", "", 
                                            "Text/Ebook (*.txt *.epub *.pdf *.docx *.mobi)")
        if path:
            self.file_path_edit.setText(path)
            self.state.source_file_path = path
            if not self.session_name_edit.text():
                name = os.path.splitext(os.path.basename(path))[0]
                self.session_name_edit.setText(name)
                self.state.session_name = name

    def open_editor_and_process(self) -> None:
        """
        Opens the internal source editor. 
        On save, writes back to disk and processes chunks.
        """
        if not self.state.source_file_path: 
            QMessageBox.warning(self, "No File", "Please select a source file first.")
            return
        
        try:
            # 1. Read File
            raw_text = self.processor.extract_text_from_file(self.state.source_file_path)
            if raw_text.startswith("Error"):
                QMessageBox.critical(self, "Error", raw_text)
                return
            
            # 2. Internal Editor (ReviewTextDialog)
            from ui.dialogs.review_text_dialog import ReviewTextDialog
            dlg = ReviewTextDialog(raw_text, self)
            
            if dlg.exec():
                final_text = dlg.result_text
                
                # 3. Save changes to source file
                try:
                    with open(self.state.source_file_path, 'w', encoding='utf-8') as f:
                        f.write(final_text)
                except Exception as e:
                    print(f"Warning: Could not save back to source file: {e}")

                self._perform_text_processing(final_text)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))



    def _perform_text_processing(self, text: str) -> None:
        """Helper to handle the logic of processing text after user review."""
        # Step 1: Preprocess (Split sentences + clean)
        sentences = self.processor.preprocess_text(
            text, 
            aggressive_clean=self.state.aggro_clean_on_parse
        )
        
        # Step 2: Chunking (if enabled)
        if self.state.settings.chunking_enabled:
            sentences = self.processor.group_sentences_into_chunks(
                sentences, 
                max_chars=self.state.settings.max_chunk_chars
            )
        
        self.state.sentences = sentences
        # Signal Global Update (Fixes Playlist not showing items)
        self.session_updated.emit()
        
        QMessageBox.information(self, "Success", f"Loaded {len(sentences)} chunks.")
        
        # Save Session
        self.project_service.save_session(self.state.session_name, {
            "source_file_path": self.state.source_file_path,
            "sentences": self.state.sentences,
            "generation_settings": dataclasses.asdict(self.state.settings)
        })

    def new_session(self) -> None:
        self.session_name_edit.clear()
        self.file_path_edit.clear()
        self.state.sentences = []
        
    def load_session_dialog(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "Select Session Folder", "Outputs_Pro")
        if dir_path:
            data = self.project_service.load_session(dir_path)
            if data:
                # Update State & UI
                self.state.session_name = data.get('session_name', '')
                self.session_name_edit.setText(self.state.session_name)
                
                self.state.sentences = data.get('sentences', [])
                
                src_path = data.get('source_file_path', '')
                self.state.source_file_path = src_path # FIX: Sync state
                self.file_path_edit.setText(src_path)
                
                if 'generation_settings' in data:
                     self.state.update_settings(**data['generation_settings'])
                
                self.session_updated.emit() # Refresh other views
                QMessageBox.information(self, "Loaded", f"Session loaded with {len(self.state.sentences)} chunks.")
            else:
                QMessageBox.warning(self, "Error", "Failed to load session.")

    def toggle_generation(self) -> None:
        QMessageBox.information(self, "Start", "Generation started! (Wiring pending in Phase 5)")

    def populate_templates(self) -> None:
        templates = self.template_service.list_templates()
        self.template_combo.clear()
        if templates:
            self.template_combo.addItems(templates)
        else:
            self.template_combo.addItem("No voices found")

    def load_template(self) -> None:
        name = self.template_combo.currentText()
        if not name or "found" in name: 
            return
        
        data = self.template_service.load_template(name)
        if data:
            try:
                for key, value in data.items():
                    if hasattr(self.state.settings, key):
                        setattr(self.state.settings, key, value)
                
                QMessageBox.information(self, "Success", f"Loaded voice '{name}'.")
                self.template_loaded.emit() 
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to apply voice: {e}")
        else:
            QMessageBox.warning(self, "Error", "Failed to load voice data.")

    def delete_template(self) -> None:
        name = self.template_combo.currentText()
        if not name or "found" in name: 
            return
        
        reply = QMessageBox.question(self, "Confirm Delete", 
                                   f"Are you sure you want to delete voice '{name}'?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            if self.template_service.delete_template(name):
                QMessageBox.information(self, "Deleted", f"Voice '{name}' deleted.")
                self.populate_templates()
            else:
                QMessageBox.critical(self, "Error", f"Failed to delete voice '{name}'.")
