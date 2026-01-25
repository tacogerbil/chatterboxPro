from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit, 
                               QPushButton, QHBoxLayout, QFileDialog, QMessageBox, QLabel, QGroupBox, QGridLayout)
from PySide6.QtCore import Qt
from core.state import AppState
from utils.text_processor import TextPreprocessor
from core.services.project_service import ProjectService
import os
import shutil

class SetupView(QWidget):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.state = app_state
        self.processor = TextPreprocessor()
        self.project_service = ProjectService()
        self.setup_ui()
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
        
        # Load/Process Button
        self.load_btn = QPushButton("Process Text & Create Session")
        self.load_btn.setStyleSheet("background-color: #2E86C1; color: white; padding: 10px; font-weight: bold;")
        self.load_btn.clicked.connect(self.process_text)
        layout.addWidget(self.load_btn)
        
        # --- Main Controls ---
        ctrl_group = QGroupBox("Main Controls")
        c_layout = QVBoxLayout(ctrl_group)
        
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
