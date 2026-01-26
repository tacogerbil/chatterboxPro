from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, 
    QPushButton, QHBoxLayout, QMessageBox, QComboBox, 
    QLineEdit, QSpinBox, QTextEdit
)
from PySide6.QtCore import Qt, QThread, Slot
from typing import Optional, List, Dict, Any
import uuid

from core.state import AppState
from ui.components.q_labeled_slider import QLabeledSlider
from core.services.generation_service import GenerationService
from core.services.template_service import TemplateService
from PySide6.QtWidgets import QInputDialog, QFileDialog

# Worker thread wrapper for GenerationService
class GenerationWorker(QThread):
    def __init__(self, service: GenerationService) -> None:
        super().__init__()
        self.service = service
        self.indices: Optional[List[int]] = None

    def set_indices(self, indices: Optional[List[int]]) -> None:
        self.indices = indices

    def run(self) -> None:
        self.service.start_generation(self.indices)

class GenerationView(QWidget):
    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self.service = GenerationService(state)
        self.template_service = TemplateService()
        # Thread management
        self.gen_thread_runner = GenerationWorker(self.service)
        
        self.setup_ui()
        self.connect_signals()
        
    def connect_signals(self) -> None:
        # Service -> UI connections
        pass
        
    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.setup_header(layout)
        self.setup_sliders(layout)
        self.setup_advanced(layout)
        self.setup_preview(layout)
        layout.addStretch()
    
    def setup_header(self, layout: QVBoxLayout) -> None:
        header = QLabel("TTS Generation Parameters")
        font = header.font()
        font.setPointSize(14)
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)

        engine_group = QGroupBox("Engine Configuration")
        form = QFormLayout(engine_group)
        
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["chatterbox", "xtts", "f5"])
        self.engine_combo.setCurrentText(self.state.settings.tts_engine)
        self.engine_combo.currentTextChanged.connect(
            lambda t: setattr(self.state.settings, 'tts_engine', t)
        )
        form.addRow("TTS Engine:", self.engine_combo)
        
        path_layout = QHBoxLayout()
        self.path_label = QLabel("Default (system cache)")
        self.path_label.setStyleSheet("color: gray;")
        self.set_path_btn = QPushButton("📁 Set Path")
        self.set_path_btn.clicked.connect(
            lambda: QMessageBox.information(self, "Info", "Path setting not yet implemented.")
        )
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(self.set_path_btn)
        form.addRow("Model Path:", path_layout)
        
        layout.addWidget(engine_group)

    def setup_sliders(self, layout: QVBoxLayout) -> None:
        voice_group = QGroupBox("Voice Settings")
        v_layout = QVBoxLayout(voice_group)
        
        # --- Source Inputs (New) ---
        src_form = QFormLayout()
        
        # Source Audio File
        self.ref_audio_edit = QLineEdit(self.state.ref_audio_path or "")
        self.ref_audio_edit.setPlaceholderText("Select a reference audio file...")
        self.ref_audio_edit.textChanged.connect(
            lambda t: setattr(self.state, 'ref_audio_path', t)
        )
        
        self.browse_ref_btn = QPushButton("Browse...")
        self.browse_ref_btn.clicked.connect(self.browse_ref_audio)
        
        ref_row = QHBoxLayout()
        ref_row.addWidget(self.ref_audio_edit)
        ref_row.addWidget(self.browse_ref_btn)
        src_form.addRow("Source Audio File:", ref_row)
        
        # Source Voice (Loader)
        self.voice_load_combo = QComboBox() 
        self.load_voice_btn = QPushButton("Load Voice")
        self.load_voice_btn.clicked.connect(self.load_voice_from_combo)
        
        voice_row = QHBoxLayout()
        voice_row.addWidget(self.voice_load_combo, stretch=1)
        voice_row.addWidget(self.load_voice_btn)
        src_form.addRow("Source Voice:", voice_row)
        
        v_layout.addLayout(src_form)
        
        # --- Sliders ---
        self.exag_slider = QLabeledSlider(
            "Exaggeration:", 0.0, 1.0, self.state.settings.exaggeration
        )
        self.exag_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'exaggeration', v)
        )
        v_layout.addWidget(self.exag_slider)
        
        self.speed_slider = QLabeledSlider(
            "Speed:", 0.5, 2.0, self.state.settings.speed
        )
        self.speed_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'speed', v)
        )
        v_layout.addWidget(self.speed_slider)
        
        self.temp_slider = QLabeledSlider(
            "Temperature:", 0.1, 1.5, self.state.settings.temperature
        )
        self.temp_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'temperature', v)
        )
        v_layout.addWidget(self.temp_slider)

        self.cfg_slider = QLabeledSlider(
            "CFG Scale:", 0.1, 1.0, self.state.settings.cfg_weight
        )
        self.cfg_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'cfg_weight', v)
        )
        v_layout.addWidget(self.cfg_slider)
        
        layout.addWidget(voice_group)
        
        fx_group = QGroupBox("Voice Effects (Post-Process)")
        f_layout = QVBoxLayout(fx_group)
        
        self.pitch_slider = QLabeledSlider(
            "Pitch Shift:", -12.0, 12.0, self.state.settings.pitch_shift, step=1.0
        )
        self.pitch_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'pitch_shift', v)
        )
        f_layout.addWidget(self.pitch_slider)
        
        self.timbre_slider = QLabeledSlider(
            "Timbre Shift:", -3.0, 3.0, self.state.settings.timbre_shift, step=0.1
        )
        self.timbre_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'timbre_shift', v)
        )
        f_layout.addWidget(self.timbre_slider)

        self.gruffness_slider = QLabeledSlider(
            "Gruffness:", 0.0, 1.0, self.state.settings.gruffness, step=0.1
        )
        self.gruffness_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'gruffness', v)
        )
        f_layout.addWidget(self.gruffness_slider)
        
        layout.addWidget(fx_group)

    def setup_advanced(self, layout: QVBoxLayout) -> None:
        self.adv_btn = QPushButton("▶ Advanced Settings")
        self.adv_btn.setCheckable(True)
        self.adv_btn.setStyleSheet("text-align: left; font-weight: bold; color: #27AE60;") 
        
        self.adv_container = QWidget()
        a_layout = QFormLayout(self.adv_container)
        
        self.gpu_edit = QLineEdit(self.state.settings.target_gpus)
        self.gpu_edit.textChanged.connect(
            lambda t: setattr(self.state.settings, 'target_gpus', t)
        )
        a_layout.addRow("Target Devs:", self.gpu_edit)
        
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 9999999)
        self.seed_spin.setValue(self.state.settings.master_seed)
        self.seed_spin.valueChanged.connect(
            lambda v: setattr(self.state.settings, 'master_seed', v)
        )
        a_layout.addRow("Master Seed:", self.seed_spin)

        self.cand_spin = QSpinBox()
        self.cand_spin.setRange(1, 10)
        self.cand_spin.setValue(self.state.settings.num_candidates)
        self.cand_spin.valueChanged.connect(
            lambda v: setattr(self.state.settings, 'num_candidates', v)
        )
        a_layout.addRow("Candidates:", self.cand_spin)

        self.adv_container.hide()
        self.adv_btn.toggled.connect(self.adv_container.setVisible)
        self.adv_btn.toggled.connect(
            lambda c: self.adv_btn.setText("▼ Advanced Settings" if c else "▶ Advanced Settings")
        )
        
        layout.addWidget(self.adv_btn)
        layout.addWidget(self.adv_container)
        
        # --- Voice Save Section (New) ---
        save_group = QGroupBox("Voice Save")
        s_layout = QHBoxLayout(save_group)
        
        self.voice_save_combo = QComboBox()
        self.voice_save_combo.setEditable(True)
        self.voice_save_combo.setPlaceholderText("Enter or Select Voice Name")
        self.voice_save_combo.setInsertPolicy(QComboBox.NoInsert)
        
        self.save_voice_btn = QPushButton("💾 Save as Voice")
        self.save_voice_btn.clicked.connect(self.save_voice_smart)
        
        s_layout.addWidget(QLabel("Voice Name"))
        s_layout.addWidget(self.voice_save_combo, stretch=1)
        s_layout.addWidget(self.save_voice_btn)
        
        layout.addWidget(save_group)
        self.populate_voices()

    def populate_voices(self) -> None:
        """Refreshes voice lists in both combos."""
        voices = self.template_service.list_templates()
        
        # Loader
        self.voice_load_combo.clear()
        self.voice_load_combo.addItems(voices if voices else ["No voices found"])
        
        # Saver
        current_text = self.voice_save_combo.currentText()
        self.voice_save_combo.clear()
        self.voice_save_combo.addItems(voices)
        self.voice_save_combo.setEditText(current_text) 

    def browse_ref_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Audio", "", "Audio (*.wav *.mp3 *.flac)"
        )
        if path:
            self.ref_audio_edit.setText(path)
            self.state.ref_audio_path = path

    def load_voice_from_combo(self) -> None:
        name = self.voice_load_combo.currentText()
        if not name or "found" in name: 
            return
        self.load_voice_by_name(name)

    def load_voice_by_name(self, name: str) -> None:
         data = self.template_service.load_template(name)
         if data:
             for key, value in data.items():
                 if hasattr(self.state.settings, key):
                     setattr(self.state.settings, key, value)
             self.refresh_values()
             QMessageBox.information(self, "Loaded", f"Voice '{name}' loaded.")
         else:
             QMessageBox.warning(self, "Error", f"Could not load '{name}'.")

    def save_voice_smart(self) -> None:
        name = self.voice_save_combo.currentText().strip()
        if not name:
             QMessageBox.warning(self, "Error", "Please enter a voice name.")
             return
             
        # Check overwrite
        voices = self.template_service.list_templates()
        if name in voices:
            if QMessageBox.question(self, "Overwrite?", f"Voice '{name}' exists. Overwrite?", 
                                  QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return

        import dataclasses
        data = dataclasses.asdict(self.state.settings)
        if self.template_service.save_template(name, data):
             QMessageBox.information(self, "Saved", f"Voice '{name}' saved.")
             self.populate_voices() 
        else:
             QMessageBox.critical(self, "Error", "Failed to save voice.")

    def setup_preview(self, layout: QVBoxLayout) -> None:
        preview_group = QGroupBox("Test Voice Settings")
        p_layout = QVBoxLayout(preview_group)
        
        # Sample Text
        p_layout.addWidget(QLabel("Sample Text:"))
        self.sample_text_edit = QTextEdit()
        self.sample_text_edit.setPlaceholderText("Enter text to preview voice...")
        self.sample_text_edit.setText("Hello! This is a test of the voice settings. How does it sound?")
        self.sample_text_edit.setMaximumHeight(60)
        p_layout.addWidget(self.sample_text_edit)
        
        # Preview Button
        self.preview_btn = QPushButton("▶ Generate Preview")
        self.preview_btn.setStyleSheet("background-color: #27AE60; color: white; font-weight: bold; padding: 10px;")
        self.preview_btn.clicked.connect(self.generate_preview)
        p_layout.addWidget(self.preview_btn)
        
        layout.addWidget(preview_group)

    def generate_preview(self) -> None:
        text = self.sample_text_edit.toPlainText()
        if not text: 
            return
        QMessageBox.information(self, "Preview", f"Preview generation not yet fully wired. \nText: {text}") 
        # TODO: Wire to Service.generate_preview(text)

    def refresh_values(self) -> None:
        """Updates UI elements to match current AppState settings."""
        s = self.state.settings
        
        self.engine_combo.blockSignals(True)
        self.engine_combo.setCurrentText(s.tts_engine)
        self.engine_combo.blockSignals(False)
        
        self.ref_audio_edit.blockSignals(True)
        self.ref_audio_edit.setText(self.state.ref_audio_path or "")
        self.ref_audio_edit.blockSignals(False)
        
        if hasattr(self, 'exag_slider'): self.exag_slider.set_value(s.exaggeration)
        if hasattr(self, 'speed_slider'): self.speed_slider.set_value(s.speed)
        if hasattr(self, 'temp_slider'): self.temp_slider.set_value(s.temperature)
        if hasattr(self, 'cfg_slider'): self.cfg_slider.set_value(s.cfg_weight)
        
        if hasattr(self, 'pitch_slider'): self.pitch_slider.set_value(s.pitch_shift)
        if hasattr(self, 'timbre_slider'): self.timbre_slider.set_value(s.timbre_shift)
        if hasattr(self, 'gruffness_slider'): self.gruffness_slider.set_value(s.gruffness)
        
        self.gpu_edit.setText(s.target_gpus)
        self.seed_spin.setValue(s.master_seed)
        self.cand_spin.setValue(s.num_candidates)



