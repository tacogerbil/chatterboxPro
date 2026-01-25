from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, 
                               QPushButton, QHBoxLayout, QMessageBox)
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
        
        # Header
        header = QLabel("TTS Generation Parameters")
        font = header.font()
        font.setBold(True)
        font.setPointSize(14)
        header.setFont(font)
        layout.addWidget(header)
        
        button_layout = QHBoxLayout()
        # Save Template Button
        self.save_tpl_btn = QPushButton("💾 Save as Template...")
        self.save_tpl_btn.clicked.connect(self.save_template)
        button_layout.addWidget(self.save_tpl_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Group: Voice Parameters
        voice_group = QGroupBox("Voice Settings")
        voice_layout = QVBoxLayout(voice_group)
        
        # Exaggeration
        self.exag_slider = QLabeledSlider("Exaggeration:", 0.0, 1.0, self.state.settings.exaggeration)
        self.exag_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'exaggeration', v))
        voice_layout.addWidget(self.exag_slider)
        
        # Speed
        self.speed_slider = QLabeledSlider("Speed:", 0.5, 2.0, self.state.settings.speed)
        self.speed_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'speed', v))
        voice_layout.addWidget(self.speed_slider)
        
        # Temperature
        self.temp_slider = QLabeledSlider("Temperature:", 0.1, 1.5, self.state.settings.temperature)
        self.temp_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'temperature', v))
        voice_layout.addWidget(self.temp_slider)
        
        layout.addWidget(voice_group)
        
        # Group: Voice Effects (The new stuff!)
        fx_group = QGroupBox("Voice Effects (Post-Process)")
        fx_layout = QVBoxLayout(fx_group)
        
        # Pitch
        self.pitch_slider = QLabeledSlider("Pitch Shift:", -12.0, 12.0, self.state.settings.pitch_shift, step=1.0)
        self.pitch_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'pitch_shift', v))
        fx_layout.addWidget(self.pitch_slider)
        
        # Timbre
        self.timbre_slider = QLabeledSlider("Timbre Shift:", -3.0, 3.0, self.state.settings.timbre_shift, step=0.1)
        self.timbre_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'timbre_shift', v))
        fx_layout.addWidget(self.timbre_slider)
        
        layout.addWidget(fx_group)
        
        layout.addStretch()
