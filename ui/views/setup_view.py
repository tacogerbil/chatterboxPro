from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit, 
                               QPushButton, QHBoxLayout, QFileDialog, QMessageBox, QLabel, QGroupBox, QGridLayout)
from PySide6.QtCore import Qt
from core.state import AppState
from utils.text_processor import TextPreprocessor
from core.services.project_service import ProjectService
from core.services.template_service import TemplateService
import os
import shutil
import dataclasses

class SetupView(QWidget):
    template_loaded = Signal()

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.state = app_state
        self.processor = TextPreprocessor()
        self.project_service = ProjectService()
        self.template_service = TemplateService()
        self.setup_ui()
        self.populate_templates() # Load templates on init
        self.check_system() # Run system check on init
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Session Header ---
        header_layout = QHBoxLayout()
        header = QLabel("Session & Source")
        font = header.font(); font.setPointSize(14); font.setBold(True)
        header.setFont(font)
        header_layout.addWidget(header)
        header_layout.addStretch()
        
        # Session Btns
        new_btn = QPushButton("New Session")
        new_btn.clicked.connect(self.new_session)
        load_btn = QPushButton("Load Session")
        load_btn.clicked.connect(self.load_session_dialog)
        header_layout.addWidget(new_btn)
        header_layout.addWidget(load_btn)
        layout.addLayout(header_layout)
        
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
        
        layout.addLayout(form_layout)
        
        # --- Templates ---
        tpl_group = QGroupBox("Generation Templates")
        t_layout = QHBoxLayout(tpl_group)
        self.template_combo = QComboBox()
        self.template_combo.addItems(["No templates found"]) # Placeholder
        self.load_tpl_btn = QPushButton("Load Template")
        # Logic to be wired later or inline? We need a service for templates.
        self.load_tpl_btn.clicked.connect(self.load_template)
        
        t_layout.addWidget(QLabel("Select Template:"))
        t_layout.addWidget(self.template_combo, stretch=1)
        t_layout.addWidget(self.load_tpl_btn)
        layout.addWidget(tpl_group)

        # Load/Process Button
        self.load_btn = QPushButton("Process Text & Create Session")
        self.load_btn.setStyleSheet("background-color: #2E86C1; color: white; padding: 10px; font-weight: bold;")
        self.load_btn.clicked.connect(self.process_text)
        layout.addWidget(self.load_btn)
        
        # Aggro Clean Switch
        self.aggro_chk = QCheckBox("Remove all special characters on processing")
        self.aggro_chk.setChecked(self.state.aggro_clean_on_parse)
        self.aggro_chk.stateChanged.connect(lambda s: setattr(self.state, 'aggro_clean_on_parse', s == Qt.Checked))
        layout.addWidget(self.aggro_chk)
        
        # --- Main Controls ---
        ctrl_group = QGroupBox("Main Controls")
        c_layout = QVBoxLayout(ctrl_group)
        
        # Auto Assemble
        self.auto_asm_chk = QCheckBox("Re-Assemble After Full Run")
        self.auto_asm_chk.setChecked(self.state.auto_assemble_after_run)
        self.auto_asm_chk.stateChanged.connect(lambda s: setattr(self.state, 'auto_assemble_after_run', s == Qt.Checked))
        c_layout.addWidget(self.auto_asm_chk)

        # Auto Regen
        self.auto_reg_chk = QCheckBox("Continue to Regenerate until all files pass")
        self.auto_reg_chk.setChecked(self.state.auto_regen_main)
        self.auto_reg_chk.stateChanged.connect(lambda s: setattr(self.state, 'auto_regen_main', s == Qt.Checked))
        c_layout.addWidget(self.auto_reg_chk)

        self.start_btn = QPushButton("Start Generation")
        self.start_btn.setStyleSheet("background-color: #27AE60; color: white; font-size: 14px; font-weight: bold; padding: 10px;")
        self.start_btn.clicked.connect(self.toggle_generation)
        c_layout.addWidget(self.start_btn)
        
        layout.addWidget(ctrl_group)
        
        # --- System Check ---
        sys_group = QGroupBox("System Check")
        s_layout = QFormLayout(sys_group)
        self.lbl_ffmpeg = QLabel("Checking...")
        self.lbl_auto = QLabel("Checking...")
        s_layout.addRow("FFmpeg:", self.lbl_ffmpeg)
        s_layout.addRow("Auto-Editor:", self.lbl_auto)
        layout.addWidget(sys_group)
        
        layout.addStretch()

    def check_system(self):
        ffmpeg = shutil.which('ffmpeg')
        self.lbl_ffmpeg.setText("Found" if ffmpeg else "Not Found (Required)")
        self.lbl_ffmpeg.setStyleSheet("color: green" if ffmpeg else "color: red")
        
        # Auto-editor check (mocked or check pip)
        # In reality, we'd check if 'auto-editor' command exists
        ae = shutil.which('auto-editor')
        self.lbl_auto.setText("Found" if ae else "Not Found (Optional)")
        self.lbl_auto.setStyleSheet("color: green" if ae else "color: orange")

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Text Source", "", 
                                            "Text/Ebook (*.txt *.epub *.pdf *.docx *.mobi)")
        if path:
            self.file_path_edit.setText(path)
            self.state.source_file_path = path
            if not self.session_name_edit.text():
                name = os.path.splitext(os.path.basename(path))[0]
                self.session_name_edit.setText(name)
                self.state.session_name = name

    def process_text(self):
        # ... logic unchanged except for using self.processor.extract_text_from_file if logic moved ...
        # For now, keeping the simplified logic but adding file reading support
        if not self.state.source_file_path: return
        
        try:
            # Use new extraction logic
            raw_text = self.processor.extract_text_from_file(self.state.source_file_path)
            if raw_text.startswith("Error"):
                QMessageBox.critical(self, "Error", raw_text)
                return
            
            # --- REVIEW DIALOG ---
            from ui.dialogs.review_text_dialog import ReviewTextDialog
            dlg = ReviewTextDialog(raw_text, self)
            if dlg.exec():
                raw_text = dlg.result_text
            else:
                return # User cancelled
                
            sentences = self.processor.preprocess_text(
                raw_text, 
                max_chars=self.state.settings.max_chunk_chars
            )
            
            self.state.sentences = sentences
            QMessageBox.information(self, "Success", f"Loaded {len(sentences)} chunks.")
            
            # Save Session
            self.project_service.save_session(self.state.session_name, {
                "source_file_path": self.state.source_file_path,
                "sentences": self.state.sentences,
                "generation_settings": {} # ToDo: Serialize settings
            })
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def new_session(self):
        # Reset state logic
        self.session_name_edit.clear()
        self.file_path_edit.clear()
        self.state.sentences = []
        # Signal a refresh?
        
    def load_session_dialog(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Session Folder", "Outputs_Pro")
        if dir_path:
            data = self.project_service.load_session(dir_path)
            if data:
                self.state.session_name = data.get('session_name', '')
                self.session_name_edit.setText(self.state.session_name)
                self.state.sentences = data.get('sentences', [])
                self.file_path_edit.setText(data.get('source_file_path', ''))
                QMessageBox.information(self, "Loaded", f"Session loaded with {len(self.state.sentences)} chunks.")
            else:
                QMessageBox.warning(self, "Error", "Failed to load session.")

    def toggle_generation(self):
        QMessageBox.information(self, "Start", "Generation started! (Wiring pending in Phase 5)")

    def populate_templates(self):
        templates = self.template_service.list_templates()
        self.template_combo.clear()
        if templates:
            self.template_combo.addItems(templates)
        else:
            self.template_combo.addItem("No templates found")

    def load_template(self):
        name = self.template_combo.currentText()
        if not name or "found" in name: return
        
        data = self.template_service.load_template(name)
        if data:
            # Update state settings
            try:
                # We iterate keys to ensure safety
                for key, value in data.items():
                    if hasattr(self.state.settings, key):
                        # Handle potential type mismatches if needed, but assuming JSON types match
                        setattr(self.state.settings, key, value)
                
                QMessageBox.information(self, "Success", f"Loaded template '{name}'.")
                self.template_loaded.emit() # Signal other views to refresh
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to apply template: {e}")
        else:
            QMessageBox.warning(self, "Error", "Failed to load template data.")
