from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit, 
                               QPushButton, QCheckBox, QGroupBox, QLabel, QHBoxLayout, QMessageBox, QDoubleSpinBox)
from PySide6.QtCore import Qt
from core.state import AppState
import shutil

class FinalizeView(QWidget):
    """
    The Export Station: Assembly, Chapter Export, Metadata, Normalization.
    """
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.state = app_state
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Audiobook Finalization")
        font = header.font(); font.setPointSize(14); font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)
        
        # --- Metadata Section ---
        meta_group = QGroupBox("Metadata Tags")
        meta_layout = QFormLayout(meta_group)
        
        self.artist_edit = QLineEdit("Chatterbox Pro")
        self.album_edit = QLineEdit()
        self.album_edit.setPlaceholderText("Defaults to session name")
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Defaults to session name")
        
        # Bindings (Mocked or Real State)
        # Assuming State has these fields or we just use them on click
        
        meta_layout.addRow("Artist:", self.artist_edit)
        meta_layout.addRow("Album:", self.album_edit)
        meta_layout.addRow("Book Title:", self.title_edit)
        layout.addWidget(meta_group)
        
        # --- Audio Processing ---
        proc_group = QGroupBox("Audio Processing")
        proc_layout = QFormLayout(proc_group)
        
        # Normalization
        self.norm_chk = QCheckBox("Enable EBU R128 Normalization")
        self.norm_chk.setChecked(False)
        self.norm_val = QDoubleSpinBox(); self.norm_val.setValue(-23.0); self.norm_val.setRange(-50, 0)
        
        norm_row = QHBoxLayout()
        norm_row.addWidget(self.norm_chk)
        norm_row.addWidget(QLabel("Target LUFS:"))
        norm_row.addWidget(self.norm_val)
        layout.addWidget(proc_group) # Add group first then layout? No.
        
        proc_layout.addRow(norm_row)
        
        # Silence Removal (Auto-Editor)
        self.silence_chk = QCheckBox("Enable Silence Removal")
        self.silence_chk.setToolTip("Requires auto-editor installed")
        proc_layout.addRow(self.silence_chk)
        
        # Formatting
        self.smart_chunk_chk = QCheckBox("Smart Chunking (Merge small files)")
        self.smart_chunk_chk.setChecked(True)
        proc_layout.addRow(self.smart_chunk_chk)
        
        layout.addWidget(proc_group)
        
        # --- Actions ---
        btn_layout = QHBoxLayout()
        
        self.btn_assemble = QPushButton("Assemble Single File")
        self.btn_assemble.setStyleSheet("background-color: #1E8449; color: white; padding: 10px; font-weight: bold;")
        self.btn_assemble.clicked.connect(self.assemble)
        
        self.btn_export = QPushButton("Export by Chapter")
        self.btn_export.setStyleSheet("padding: 10px; font-weight: bold;")
        self.btn_export.clicked.connect(self.export_chapters)
        
        btn_layout.addWidget(self.btn_assemble)
        btn_layout.addWidget(self.btn_export)
        
        layout.addLayout(btn_layout)
        layout.addStretch()
        
        self.check_deps()

    def check_deps(self):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            self.norm_chk.setEnabled(False)
            self.norm_chk.setText("Normalization (FFmpeg Missing)")
            
        ae = shutil.which('auto-editor')
        if not ae:
            self.silence_chk.setEnabled(False)
            self.silence_chk.setText("Silence Removal (auto-editor Missing)")

    def assemble(self):
        QMessageBox.information(self, "Assemble", "Assembly logic pending Phase 5 wiring.\n(Metadata collected)")

    def export_chapters(self):
        QMessageBox.information(self, "Export", "Export logic pending Phase 5 wiring.")
