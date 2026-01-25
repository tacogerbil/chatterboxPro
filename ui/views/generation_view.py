from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, 
                               QPushButton, QHBoxLayout, QMessageBox, QComboBox, 
                               QLineEdit, QSpinBox, QTextEdit)
from PySide6.QtCore import Qt
from core.state import AppState
from ui.components.q_labeled_slider import QLabeledSlider

class GenerationView(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setup_ui()
        
    def save_template(self):
        # Placeholder for now
        QMessageBox.information(self, "Save Template", "Template saving will be implemented in the polishing phase.")
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. Header (Engine, Model, etc)
        self.setup_header(layout)
        
        # 2. Sliders (Voice Parameters)
        self.setup_sliders(layout)
        
        # 3. Advanced Settings (Collapsible)
        self.setup_advanced(layout)
        
        # 4. Footer (Preview)
        self.setup_footer(layout)
        
        layout.addStretch()

    def setup_header(self, layout):
        # Title
        header = QLabel("TTS Generation Parameters")
        font = header.font(); font.setPointSize(14); font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)

        # Engine Config Frame
        engine_group = QGroupBox("Engine Configuration")
        form = QFormLayout(engine_group)
        
        # Engine Selector
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["chatterbox", "xtts", "f5"])
        self.engine_combo.setCurrentText(self.state.settings.tts_engine)
        self.engine_combo.currentTextChanged.connect(lambda t: setattr(self.state.settings, 'tts_engine', t))
        form.addRow("TTS Engine:", self.engine_combo)
        
        # Model Path (Mocked for parity)
        path_layout = QHBoxLayout()
        self.path_label = QLabel("Default (system cache)")
        self.path_label.setStyleSheet("color: gray;")
        self.set_path_btn = QPushButton("📁 Set Path")
        self.set_path_btn.clicked.connect(lambda: QMessageBox.information(self, "Info", "Path setting not yet implemented."))
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(self.set_path_btn)
        form.addRow("Model Path:", path_layout)
        
        # Save Template Button (Restored from previous step)
        self.save_tpl_btn = QPushButton("💾 Save as Template...")
        self.save_tpl_btn.clicked.connect(self.save_template)
        form.addRow("", self.save_tpl_btn)

        layout.addWidget(engine_group)

    def setup_sliders(self, layout):
        # Group: Voice Parameters
        voice_group = QGroupBox("Voice Settings")
        v_layout = QVBoxLayout(voice_group)
        
        self.exag_slider = QLabeledSlider("Exaggeration:", 0.0, 1.0, self.state.settings.exaggeration)
        self.exag_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'exaggeration', v))
        v_layout.addWidget(self.exag_slider)
        
        self.speed_slider = QLabeledSlider("Speed:", 0.5, 2.0, self.state.settings.speed)
        self.speed_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'speed', v))
        v_layout.addWidget(self.speed_slider)
        
        self.temp_slider = QLabeledSlider("Temperature:", 0.1, 1.5, self.state.settings.temperature)
        self.temp_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'temperature', v))
        v_layout.addWidget(self.temp_slider)
        
        layout.addWidget(voice_group)
        
        # Group: Voice Effects
        fx_group = QGroupBox("Voice Effects (Post-Process)")
        f_layout = QVBoxLayout(fx_group)
        
        self.pitch_slider = QLabeledSlider("Pitch Shift:", -12.0, 12.0, self.state.settings.pitch_shift, step=1.0)
        self.pitch_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'pitch_shift', v))
        f_layout.addWidget(self.pitch_slider)
        
        self.timbre_slider = QLabeledSlider("Timbre Shift:", -3.0, 3.0, self.state.settings.timbre_shift, step=0.1)
        self.timbre_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'timbre_shift', v))
        f_layout.addWidget(self.timbre_slider)
        
        layout.addWidget(fx_group)

    def setup_advanced(self, layout):
        # Toggle Button
        self.adv_btn = QPushButton("▶ Advanced Settings")
        self.adv_btn.setCheckable(True)
        self.adv_btn.setStyleSheet("text-align: left; font-weight: bold;")
        
        # Container
        self.adv_container = QWidget()
        a_layout = QFormLayout(self.adv_container)
        
        # Target Devices
        self.gpu_edit = QLineEdit(self.state.settings.target_gpus)
        self.gpu_edit.textChanged.connect(lambda t: setattr(self.state.settings, 'target_gpus', t))
        a_layout.addRow("Target Devs:", self.gpu_edit)
        
        # Seed
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 9999999)
        self.seed_spin.setValue(self.state.settings.master_seed)
        self.seed_spin.valueChanged.connect(lambda v: setattr(self.state.settings, 'master_seed', v))
        a_layout.addRow("Master Seed:", self.seed_spin)

        # Candidates
        self.cand_spin = QSpinBox()
        self.cand_spin.setRange(1, 10)
        self.cand_spin.setValue(self.state.settings.num_candidates)
        self.cand_spin.valueChanged.connect(lambda v: setattr(self.state.settings, 'num_candidates', v))
        a_layout.addRow("Candidates:", self.cand_spin)

        self.adv_container.hide() # Hidden by default
        self.adv_btn.toggled.connect(self.adv_container.setVisible)
        self.adv_btn.toggled.connect(lambda c: self.adv_btn.setText("▼ Advanced Settings" if c else "▶ Advanced Settings"))
        
        layout.addWidget(self.adv_btn)
        layout.addWidget(self.adv_container)

    def setup_footer(self, layout):
        preview_group = QGroupBox("Test Voice Settings")
        p_layout = QVBoxLayout(preview_group)
        
        self.sample_text = QTextEdit("Hello! This is a test of the voice settings. How does it sound?")
        self.sample_text.setMaximumHeight(60)
        p_layout.addWidget(self.sample_text)
        
        self.prev_btn = QPushButton("▶ Generate Preview")
        self.prev_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px;")
        self.prev_btn.clicked.connect(self.generate_preview)
        p_layout.addWidget(self.prev_btn)
        
        layout.addWidget(preview_group)
        
    def generate_preview(self):
        # Placeholder for connection
        text = self.sample_text.toPlainText()
        QMessageBox.information(self, "Preview", f"Simulating generation for: '{text}'")
