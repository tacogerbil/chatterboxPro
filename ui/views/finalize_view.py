from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit, 
                               QPushButton, QCheckBox, QGroupBox, QLabel, QHBoxLayout, QMessageBox, QDoubleSpinBox, QFileDialog)
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
        
        proc_layout.addRow(norm_row)
        
        # Silence Removal (Auto-Editor)
        self.silence_chk = QCheckBox("Enable Silence Removal")
        self.silence_chk.setToolTip("Requires auto-editor installed")
        proc_layout.addRow(self.silence_chk)
        
        # Silence Params (Legacy restoration)
        sil_params_layout = QHBoxLayout()
        
        self.thresh_spin = QDoubleSpinBox(); self.thresh_spin.setRange(0.01, 1.0); self.thresh_spin.setSingleStep(0.01); self.thresh_spin.setValue(self.state.settings.silence_threshold)
        self.thresh_spin.valueChanged.connect(lambda v: setattr(self.state.settings, 'silence_threshold', v))
        sil_params_layout.addWidget(QLabel("Thresh:"))
        sil_params_layout.addWidget(self.thresh_spin)
        
        self.speed_spin = QDoubleSpinBox(); self.speed_spin.setRange(1.0, 99999.0); self.speed_spin.setValue(self.state.settings.silent_speed)
        self.speed_spin.valueChanged.connect(lambda v: setattr(self.state.settings, 'silent_speed', v))
        sil_params_layout.addWidget(QLabel("Speed:"))
        sil_params_layout.addWidget(self.speed_spin)
        
        self.margin_spin = QSpinBox(); self.margin_spin.setRange(0, 100); self.margin_spin.setValue(self.state.settings.frame_margin)
        self.margin_spin.valueChanged.connect(lambda v: setattr(self.state.settings, 'frame_margin', v))
        sil_params_layout.addWidget(QLabel("Margin:"))
        sil_params_layout.addWidget(self.margin_spin)
        
        proc_layout.addRow(sil_params_layout)
        
        # Formatting
        self.smart_chunk_chk = QCheckBox("Smart Chunking (Merge small files)")
        self.smart_chunk_chk.setChecked(True)
        proc_layout.addRow(self.smart_chunk_chk)
        
        # Fine Tuning
        from PySide6.QtWidgets import QSpinBox
        
        self.max_chars = QSpinBox(); self.max_chars.setRange(100, 5000); self.max_chars.setValue(self.state.settings.max_chunk_chars)
        self.max_chars.valueChanged.connect(lambda v: setattr(self.state.settings, 'max_chunk_chars', v))
        proc_layout.addRow("Max Chars per Chunk:", self.max_chars)
        
        self.sil_dur = QSpinBox(); self.sil_dur.setRange(0, 5000); self.sil_dur.setValue(self.state.settings.silence_duration)
        self.sil_dur.valueChanged.connect(lambda v: setattr(self.state.settings, 'silence_duration', v))
        proc_layout.addRow("Silence Duration (ms):", self.sil_dur)
        
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
        ffmpeg_loc = shutil.which('ffmpeg')
        if not ffmpeg_loc:
            self.norm_chk.setEnabled(False)
            self.norm_chk.setText("Normalization (FFmpeg Missing)")
            
        ae = shutil.which('auto-editor')
        if not ae:
            self.silence_chk.setEnabled(False)
            self.silence_chk.setText("Silence Removal (auto-editor Missing)")


    def set_audio_service(self, audio_service):
        self.audio_service = audio_service
        # Connect signals for UI feedback
        self.audio_service.assembly_progress.connect(self._on_progress)
        self.audio_service.assembly_finished.connect(self._on_finished)
        self.audio_service.assembly_error.connect(self._on_error)
        
    def _on_progress(self, msg):
        # We could show a STATUS BAR message or a Toast.
        # For now, print to console or update header?
        # A status bar in Main Window would be best.
        print(f"[Assembly] {msg}")

    def _on_finished(self, msg):
        QMessageBox.information(self, "Success", msg)
        self.btn_assemble.setEnabled(True)
        self.btn_assemble.setText("Assemble Single File")
        self.btn_export.setEnabled(True)

    def _on_error(self, msg):
        QMessageBox.critical(self, "Error", msg)
        self.btn_assemble.setEnabled(True)
        self.btn_assemble.setText("Assemble Single File")
        self.btn_export.setEnabled(True)

    def assemble(self):
        if not hasattr(self, 'audio_service'): return
        
        # Default name
        default_name = f"{self.state.session_name}_audiobook.mp3"
        
        path, _ = QFileDialog.getSaveFileName(self, "Assemble Audiobook", 
                                              default_name, 
                                              "MP3 Files (*.mp3);;WAV Files (*.wav)")
        if not path: return
        
        # Gather Metadata
        metadata = {
            "artist": self.artist_edit.text() or "Chatterbox Pro",
            "album": self.album_edit.text() or self.state.session_name,
            "title": self.title_edit.text() or self.state.session_name
        }
        
        # Sync Settings
        self.state.settings.norm_enabled = self.norm_chk.isChecked()
        self.state.settings.norm_level = self.norm_val.value()
        self.state.settings.silence_removal_enabled = self.silence_chk.isChecked()
        
        # Lock buttons
        self.btn_assemble.setEnabled(False); self.btn_assemble.setText("Assembling...")
        self.btn_export.setEnabled(False)
        
        # Call Service (Threaded)
        self.audio_service.assemble_audiobook(path, is_for_acx=False, metadata=metadata)
        
    def export_chapters(self):
        if not hasattr(self, 'audio_service'): return
        
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not path: return
        
        # Sync Settings
        self.state.settings.norm_enabled = self.norm_chk.isChecked()
        self.state.settings.norm_level = self.norm_val.value()
        self.state.settings.silence_removal_enabled = self.silence_chk.isChecked()

        # Lock buttons
        self.btn_assemble.setEnabled(False)
        self.btn_export.setEnabled(False); self.btn_export.setText("Exporting...")

        self.audio_service.export_chapters(path)
