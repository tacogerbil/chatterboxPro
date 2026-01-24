from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit, 
                               QPushButton, QHBoxLayout, QFileDialog, QMessageBox, QLabel)
from PySide6.QtCore import Qt
from core.state import AppState
from utils.text_processor import TextPreprocessor
import os

class SetupView(QWidget):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.state = app_state
        self.processor = TextPreprocessor()
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Session Setup")
        font = header.font(); font.setPointSize(14); font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)
        
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
        
        # Reference Audio
        self.ref_path_edit = QLineEdit()
        self.ref_path_edit.setReadOnly(True)
        self.ref_btn = QPushButton("Browse...")
        self.ref_btn.clicked.connect(self.browse_ref)
        
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(self.ref_path_edit)
        ref_layout.addWidget(self.ref_btn)
        form_layout.addRow("Reference Audio:", ref_layout)
        
        layout.addLayout(form_layout)
        
        # Load Button
        self.load_btn = QPushButton("Process Text & Create Session")
        self.load_btn.setStyleSheet("background-color: #2E86C1; color: white; padding: 10px; font-weight: bold;")
        self.load_btn.clicked.connect(self.process_text)
        layout.addWidget(self.load_btn)
        
        layout.addStretch()

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Text Source", "", 
                                            "Text/Ebook (*.txt *.epub *.pdf *.docx *.mobi)")
        if path:
            self.file_path_edit.setText(path)
            self.state.source_file_path = path
            
            # Auto-suggest session name if empty
            if not self.session_name_edit.text():
                name = os.path.splitext(os.path.basename(path))[0]
                self.session_name_edit.setText(name)
                self.state.session_name = name

    def browse_ref(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Reference Audio", "", "Audio (*.wav *.mp3 *.flac)")
        if path:
            self.ref_path_edit.setText(path)
            self.state.ref_audio_path = path

    def process_text(self):
        if not self.state.session_name:
            QMessageBox.warning(self, "Missing Info", "Please enter a Session Name.")
            return
        if not self.state.source_file_path:
            QMessageBox.warning(self, "Missing Info", "Please select a Source Text file.")
            return
            
        try:
            # Process using the existing utility logic
            # Note: We are mocking the 'app' dependency or need to adapt TextPreprocessor if it depends on 'self.app' 
            # Looking at imports, TextPreprocessor seems independent.
            
            sentences = self.processor.preprocess_text(
                self.state.source_file_path, 
                max_chars=self.state.settings.max_chunk_chars
            )
            
            if not sentences:
                QMessageBox.warning(self, "Empty", "No text content found in file.")
                return
                
            # Update State
            self.state.sentences = sentences
            
            QMessageBox.information(self, "Success", 
                                  f"Loaded {len(sentences)} text chunks.\n"
                                  f"You can now go to the Chapters or Generation tab.")
                                  
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to process text:\n{str(e)}")
