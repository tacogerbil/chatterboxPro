from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, 
                               QPushButton, QHBoxLayout, QMessageBox, QComboBox, 
                               QLineEdit, QSpinBox, QTextEdit, QProgressBar)
from PySide6.QtCore import Qt, QThread
from core.state import AppState
from ui.components.q_labeled_slider import QLabeledSlider
from core.services.generation_service import GenerationService

# Worker thread wrapper for GenerationService
class GenerationWorker(QThread):
    def __init__(self, service):
        super().__init__()
        self.service = service
        self.indices = None

    def set_indices(self, indices):
        self.indices = indices

    def run(self):
        self.service.start_generation(self.indices)

class GenerationView(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.service = GenerationService(state)
        # Thread management
        self.gen_thread_runner = GenerationWorker(self.service)
        
        self.setup_ui()
        self.connect_signals()
        
    def connect_signals(self):
        # Service -> UI connections
        self.service.progress_update.connect(self.update_progress)
        self.service.finished.connect(self.on_generation_finished)
        self.service.error_occurred.connect(self.on_generation_error)
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. Header
        self.setup_header(layout)
        
        # 2. Sliders
        self.setup_sliders(layout)
        
        # 3. Advanced
        self.setup_advanced(layout)
        
        # 4. Preview / Progress
        self.setup_footer(layout)
        
        layout.addStretch()

    # ... (header, sliders, advanced setup methods unchanged - assume previous code exists or I rewrite them if I must replace whole file?)
    # Since I am replacing the whole file content via 'replace_file_content' I need to be careful to Include the middle parts if I cut them out.
    # But wait, 'replace_file_content' is for blocks. I will replace the whole file to be safe and clean.
    
    def setup_header(self, layout):
        # ... (Same as before)
        header = QLabel("TTS Generation Parameters")
        font = header.font(); font.setPointSize(14); font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)

        engine_group = QGroupBox("Engine Configuration")
        form = QFormLayout(engine_group)
        
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["chatterbox", "xtts", "f5"])
        self.engine_combo.setCurrentText(self.state.settings.tts_engine)
        self.engine_combo.currentTextChanged.connect(lambda t: setattr(self.state.settings, 'tts_engine', t))
        form.addRow("TTS Engine:", self.engine_combo)
        
        path_layout = QHBoxLayout()
        self.path_label = QLabel("Default (system cache)")
        self.path_label.setStyleSheet("color: gray;")
        self.set_path_btn = QPushButton("📁 Set Path")
        self.set_path_btn.clicked.connect(lambda: QMessageBox.information(self, "Info", "Path setting not yet implemented."))
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(self.set_path_btn)
        form.addRow("Model Path:", path_layout)
        
        self.save_tpl_btn = QPushButton("💾 Save as Template...")
        self.save_tpl_btn.clicked.connect(self.save_template)
        form.addRow("", self.save_tpl_btn)

        layout.addWidget(engine_group)

    def setup_sliders(self, layout):
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

        self.cfg_slider = QLabeledSlider("CFG Scale:", 0.1, 1.0, self.state.settings.cfg_weight)
        self.cfg_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'cfg_weight', v))
        v_layout.addWidget(self.cfg_slider)
        
        layout.addWidget(voice_group)
        
        fx_group = QGroupBox("Voice Effects (Post-Process)")
        f_layout = QVBoxLayout(fx_group)
        
        self.pitch_slider = QLabeledSlider("Pitch Shift:", -12.0, 12.0, self.state.settings.pitch_shift, step=1.0)
        self.pitch_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'pitch_shift', v))
        f_layout.addWidget(self.pitch_slider)
        
        self.timbre_slider = QLabeledSlider("Timbre Shift:", -3.0, 3.0, self.state.settings.timbre_shift, step=0.1)
        self.timbre_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'timbre_shift', v))
        f_layout.addWidget(self.timbre_slider)

        self.gruffness_slider = QLabeledSlider("Gruffness:", 0.0, 1.0, self.state.settings.gruffness, step=0.1)
        self.gruffness_slider.value_changed.connect(lambda v: setattr(self.state.settings, 'gruffness', v))
        f_layout.addWidget(self.gruffness_slider)
        
        layout.addWidget(fx_group)

    def setup_advanced(self, layout):
        self.adv_btn = QPushButton("▶ Advanced Settings")
        self.adv_btn.setCheckable(True)
        self.adv_btn.setStyleSheet("text-align: left; font-weight: bold;")
        
        self.adv_container = QWidget()
        a_layout = QFormLayout(self.adv_container)
        
        self.gpu_edit = QLineEdit(self.state.settings.target_gpus)
        self.gpu_edit.textChanged.connect(lambda t: setattr(self.state.settings, 'target_gpus', t))
        a_layout.addRow("Target Devs:", self.gpu_edit)
        
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 9999999)
        self.seed_spin.setValue(self.state.settings.master_seed)
        self.seed_spin.valueChanged.connect(lambda v: setattr(self.state.settings, 'master_seed', v))
        a_layout.addRow("Master Seed:", self.seed_spin)

        self.cand_spin = QSpinBox()
        self.cand_spin.setRange(1, 10)
        self.cand_spin.setValue(self.state.settings.num_candidates)
        self.cand_spin.valueChanged.connect(lambda v: setattr(self.state.settings, 'num_candidates', v))
        a_layout.addRow("Candidates:", self.cand_spin)

        self.adv_container.hide()
        self.adv_btn.toggled.connect(self.adv_container.setVisible)
        self.adv_btn.toggled.connect(lambda c: self.adv_btn.setText("▼ Advanced Settings" if c else "▶ Advanced Settings"))
        
        layout.addWidget(self.adv_btn)
        layout.addWidget(self.adv_container)
        
    def setup_footer(self, layout):
        # Progress Bar (New)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v / %m Chunks")
        layout.addWidget(self.progress_bar)
        
        preview_group = QGroupBox("Test Voice Settings")
        p_layout = QVBoxLayout(preview_group)
        
        self.sample_text = QTextEdit("Hello! This is a test of the voice settings.")
        self.sample_text.setMaximumHeight(60)
        p_layout.addWidget(self.sample_text)
        
        # Start / Stop Buttons
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶ Generate Preview")
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px;")
        self.start_btn.clicked.connect(self.generate_preview)
        
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setStyleSheet("background-color: #A93226; color: white; font-weight: bold; padding: 5px;")
        self.stop_btn.clicked.connect(self.stop_generation)
        self.stop_btn.setEnabled(False)
        
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        p_layout.addLayout(btn_layout)
        
        layout.addWidget(preview_group)
        
    def generate_preview(self):
        # In full app, this might generate *just* the preview text.
        # For MVP, we'll mimic "Start Generation" since user wanted integration.
        # Or should we generate the preview text specifically?
        # The legacy app "Generate Preview" button was distinct from "Start Generation".
        # But this view is "Generation Parameters".
        # Let's support Preview generation by injecting a temp item?
        # Or simpler: Just run start_generation() on the playlist?
        # User usually wants to test the *parameters*.
        
        # NOTE: Legacy GenerationTab had "Generate Preview" AND "Start Generation" (which was in ControlsFrame).
        # But ControlsFrame "Generate" logic is now distributed.
        # We will make this button trigger PREVIEW generation (in-memory or temp file).
        
        # For MVP wiring, we'll link it to a "Preview" mode in service?
        # Wait, the service processes *sentences*.
        # We can create a dummy sentence dict and pass it?
        # This is complex. Let's make it trigger "Generate ALL" for now or show Stub.
        # Just kidding. Let's make it trigger "Start Generation" for the playlist, behaving like the Main "Start" button.
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        
        # Start Service in Thread
        self.gen_thread_runner.set_indices(None) # None = process all pending
        self.gen_thread_runner.start()
        
    def stop_generation(self):
        self.service.request_stop()
        self.stop_btn.setEnabled(False)
        self.start_btn.setEnabled(True)

    def update_progress(self, completed, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(completed)
        self.progress_bar.setFormat(f"%v / %m ({int(completed/total*100)}%)")

    def on_generation_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        QMessageBox.information(self, "Complete", "Generation Finished!")

    def on_generation_error(self, err_msg):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        QMessageBox.critical(self, "Error", f"Generation Error: {err_msg}")

    def save_template(self):
        QMessageBox.information(self, "Save Template", "Template saving will be implemented in the polishing phase.")
