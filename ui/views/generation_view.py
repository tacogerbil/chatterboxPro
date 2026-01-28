from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, 
    QPushButton, QHBoxLayout, QMessageBox, QComboBox, 
    QLineEdit, QSpinBox, QPlainTextEdit, QScrollArea, QCheckBox
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
        self.service: Optional[GenerationService] = None
        self.audio_service: Optional[Any] = None
        self.template_service = TemplateService()
        
        self.setup_ui()
        # self.connect_signals() 

    def set_generation_service(self, service: GenerationService) -> None:
        self.service = service
        self.service.preview_ready.connect(self.on_preview_ready)
        self.service.preview_error.connect(self.on_preview_error)

    def on_preview_error(self, error_msg: str) -> None:
        print(f"[UI Debug] Preview Error signal received: {error_msg}", flush=True)
        QMessageBox.critical(self, "Preview Failed", f"Error generating preview:\n{error_msg}")

    def set_audio_service(self, service: Any) -> None:
        self.audio_service = service

    def connect_signals(self) -> None:
        pass
        
    def on_preview_ready(self, path: str) -> None:
        print(f"[UI Debug] Preview Ready signal received. Path: {path}", flush=True)
        if self.audio_service:
            # Auto-play without popup
            self.audio_service.play_file(path)
        else:
             print("[UI Debug] Audio Service not connected!", flush=True)
             QMessageBox.warning(self, "Error", "Audio Service not connected.")
        
    def setup_ui(self) -> None:
        # Wrap everything in a ScrollArea to handle small screens
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

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
        # Init Label with current state
        lbl_text = self.state.model_path if self.state.model_path else "Default (system cache)"
        self.path_label = QLabel(lbl_text)
        
        if self.state.model_path:
             self.path_label.setToolTip(self.state.model_path)
             self.path_label.setStyleSheet("color: #27AE60; font-weight: bold;")
        else:
             self.path_label.setStyleSheet("color: gray;")
             
        self.set_path_btn = QPushButton("📁 Set Path")
        self.set_path_btn.clicked.connect(self.browse_model_path)
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(self.set_path_btn)
        form.addRow("Model Path:", path_layout)
        
        layout.addWidget(engine_group)

    def browse_model_path(self) -> None:
        """Opens a directory picker for the model."""
        path = QFileDialog.getExistingDirectory(self, "Select Model Directory")
        if path:
            self.state.model_path = path # FIX: Use root AppState
            self.path_label.setText(path)
            # Make label tooltip show full path
            self.path_label.setToolTip(path)
            # Style: Green to indicate custom path set
            self.path_label.setStyleSheet("color: #27AE60; font-weight: bold;")
        else:
            pass

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
            "Exaggeration:", 0.0, 1.0, self.state.settings.exaggeration,
            left_label="Monotone", right_label="Expressive"
        )
        self.exag_slider.setToolTip("Emotional intensity. 0.0 = flat/monotone, 0.5 = neutral, 1.0 = very expressive")
        self.exag_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'exaggeration', v)
        )
        v_layout.addWidget(self.exag_slider)
        
        self.speed_slider = QLabeledSlider(
            "Speed:", 0.5, 2.0, self.state.settings.speed,
            left_label="0.5x Slower", right_label="2x Faster"
        )
        self.speed_slider.setToolTip("Speaking rate. 0.5 = half speed, 1.0 = normal, 2.0 = double speed.")
        self.speed_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'speed', v)
        )
        v_layout.addWidget(self.speed_slider)
        
        self.temp_slider = QLabeledSlider(
            "Temperature:", 0.1, 1.5, self.state.settings.temperature,
            left_label="Consistent", right_label="Varied"
        )
        self.temp_slider.setToolTip("Creativity/randomness. Lower = consistent/robotic, Higher = varied/natural.")
        self.temp_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'temperature', v)
        )
        v_layout.addWidget(self.temp_slider)

        self.cfg_slider = QLabeledSlider(
            "CFG Scale:", 0.1, 1.0, self.state.settings.cfg_weight,
            left_label="Creative", right_label="Exact Match"
        )
        self.cfg_slider.setToolTip("How closely to match the reference voice. Higher = stronger accent/tone.")
        self.cfg_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'cfg_weight', v)
        )
        v_layout.addWidget(self.cfg_slider)
        
        layout.addWidget(voice_group)
        
        fx_group = QGroupBox("Voice Effects (Post-Process)")
        f_layout = QVBoxLayout(fx_group)
        
        self.pitch_slider = QLabeledSlider(
            "Pitch Shift:", -12.0, 12.0, self.state.settings.pitch_shift, step=0.5,
            left_label="Deeper (-12)", right_label="Higher (+12)"
        )
        self.pitch_slider.setToolTip("Shift voice pitch in semitones. Negative = deeper voice, Positive = higher voice.")
        self.pitch_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'pitch_shift', v)
        )
        f_layout.addWidget(self.pitch_slider)
        
        self.timbre_slider = QLabeledSlider(
            "Timbre Shift:", -3.0, 3.0, self.state.settings.timbre_shift, step=0.1,
            left_label="Warmer/Darker", right_label="Brighter/Thinner"
        )
        self.timbre_slider.setToolTip("Adjust vocal character (formants). Negative = warmer/darker (boosts lows), Positive = brighter (boosts highs).")
        self.timbre_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'timbre_shift', v)
        )
        f_layout.addWidget(self.timbre_slider)

        self.gruffness_slider = QLabeledSlider(
            "Gruffness:", 0.0, 1.0, self.state.settings.gruffness, step=0.05,
            left_label="Clean", right_label="Gravelly"
        )
        self.gruffness_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'gruffness', v)
        )
        f_layout.addWidget(self.gruffness_slider)
        
        # New: Bass / Treble
        self.bass_slider = QLabeledSlider(
            "Bass Boost:", -12.0, 12.0, self.state.settings.bass_boost, step=0.5,
            left_label="Cut", right_label="Boost"
        )
        self.bass_slider.setToolTip("EQ: Adjust low frequencies (100Hz Shelf).")
        self.bass_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'bass_boost', v)
        )
        f_layout.addWidget(self.bass_slider)

        self.treble_slider = QLabeledSlider(
            "Treble Boost:", -12.0, 12.0, self.state.settings.treble_boost, step=0.5,
            left_label="Cut", right_label="Boost"
        )
        self.treble_slider.setToolTip("EQ: Adjust high frequencies (8kHz Shelf).")
        self.treble_slider.value_changed.connect(
            lambda v: setattr(self.state.settings, 'treble_boost', v)
        )
        f_layout.addWidget(self.treble_slider)
        
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
        
        self.order_combo = QComboBox()
        self.order_combo.addItems(["fastest", "sequential"])
        self.order_combo.setCurrentText(self.state.settings.generation_order)
        self.order_combo.currentTextChanged.connect(
            lambda t: setattr(self.state.settings, 'generation_order', t)
        )
        a_layout.addRow("Gen Order:", self.order_combo)
        
        self.order_combo = QComboBox()
        self.order_combo.addItems(["fastest", "sequential"])
        self.order_combo.setCurrentText(self.state.settings.generation_order)
        self.order_combo.currentTextChanged.connect(
            lambda t: setattr(self.state.settings, 'generation_order', t)
        )
        a_layout.addRow("Gen Order:", self.order_combo)
        
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

        # MCCC Audit Restoration:
        self.outputs_spin = QSpinBox()
        self.outputs_spin.setRange(1, 100)
        self.outputs_spin.setValue(self.state.settings.num_full_outputs)
        self.outputs_spin.valueChanged.connect(
            lambda v: setattr(self.state.settings, 'num_full_outputs', v)
        )
        a_layout.addRow("Full Outputs:", self.outputs_spin)
        
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 10)
        self.retries_spin.setValue(self.state.settings.max_attempts)
        self.retries_spin.valueChanged.connect(
            lambda v: setattr(self.state.settings, 'max_attempts', v)
        )
        a_layout.addRow("ASR Max Retries:", self.retries_spin)

        # Checkboxes/Switches
        chk_layout = QVBoxLayout()
        
        self.chk_asr = QGroupBox("ASR Validation")
        self.chk_asr.setCheckable(True)
        self.chk_asr.setChecked(self.state.settings.asr_validation_enabled)
        self.chk_asr.toggled.connect(
            lambda c: setattr(self.state.settings, 'asr_validation_enabled', c)
        )
        # ASR Threshold inside logic
        asr_l = QFormLayout(self.chk_asr)
        self.asr_thresh = QLabeledSlider("Threshold", 0.1, 1.0, self.state.settings.asr_threshold)
        self.asr_thresh.value_changed.connect(
             lambda v: setattr(self.state.settings, 'asr_threshold', v)
        )
        asr_l.addRow(self.asr_thresh)
        chk_layout.addWidget(self.chk_asr)
        
        self.chk_watermark = QCheckBox("Disable Perth Watermark")
        self.chk_watermark.setChecked(self.state.settings.disable_watermark)
        self.chk_watermark.stateChanged.connect(
             lambda s: setattr(self.state.settings, 'disable_watermark', s == Qt.Checked or s == 2)
        )
        chk_layout.addWidget(self.chk_watermark)
        
        a_layout.addRow(chk_layout)

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
             # 1. Load Settings
             for key, value in data.items():
                 if hasattr(self.state.settings, key):
                     setattr(self.state.settings, key, value)
             
             # 2. Load Ref Audio (if present)
             if 'ref_audio_path' in data and data['ref_audio_path']:
                 path = data['ref_audio_path']
                 self.state.ref_audio_path = path
                 self.ref_audio_edit.setText(path)
                 
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
        
        # Inject global state items that belong to a "Voice Profile"
        data['ref_audio_path'] = self.state.ref_audio_path
        
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
        self.sample_text_edit = QPlainTextEdit()
        self.sample_text_edit.setPlaceholderText("Enter text to preview voice...")
        self.sample_text_edit.setPlainText("Hello! This is a test of the voice settings. How does it sound?")
        self.sample_text_edit.setMaximumHeight(80)
        # Theme handled globally by qt-material
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
            
        if not self.service:
            QMessageBox.warning(self, "Error", "Generation Service not connected.")
            return

        self.service.generate_preview(text)

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
        if hasattr(self, 'bass_slider'): self.bass_slider.set_value(s.bass_boost)
        if hasattr(self, 'treble_slider'): self.treble_slider.set_value(s.treble_boost)
        
        if hasattr(self, 'order_combo'): self.order_combo.setCurrentText(s.generation_order)
        if hasattr(self, 'outputs_spin'): self.outputs_spin.setValue(s.num_full_outputs)
        if hasattr(self, 'retries_spin'): self.retries_spin.setValue(s.max_attempts)
        if hasattr(self, 'chk_asr'): self.chk_asr.setChecked(s.asr_validation_enabled)
        if hasattr(self, 'asr_thresh'): self.asr_thresh.set_value(s.asr_threshold)
        if hasattr(self, 'chk_watermark'): self.chk_watermark.setChecked(s.disable_watermark)
        if hasattr(self, 'timbre_slider'): self.timbre_slider.set_value(s.timbre_shift)
        if hasattr(self, 'gruffness_slider'): self.gruffness_slider.set_value(s.gruffness)
        if hasattr(self, 'bass_slider'): self.bass_slider.set_value(s.bass_boost)
        if hasattr(self, 'treble_slider'): self.treble_slider.set_value(s.treble_boost)
        
        self.gpu_edit.setText(s.target_gpus)
        self.seed_spin.setValue(s.master_seed)
        self.gpu_edit.setText(s.target_gpus)
        self.seed_spin.setValue(s.master_seed)
        self.cand_spin.setValue(s.num_candidates)
        
        # Restored
        if hasattr(self, 'outputs_spin'): self.outputs_spin.setValue(s.num_full_outputs)
        if hasattr(self, 'retries_spin'): self.retries_spin.setValue(s.max_attempts)
        if hasattr(self, 'chk_asr'): self.chk_asr.setChecked(s.asr_validation_enabled)
        if hasattr(self, 'asr_thresh'): self.asr_thresh.set_value(s.asr_threshold)
        if hasattr(self, 'chk_watermark'): self.chk_watermark.setChecked(s.disable_watermark)



