from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton, 
    QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton, 
    QGroupBox, QFormLayout, QFileDialog, QMessageBox, QApplication, QSpinBox,
    QLineEdit, QCheckBox
)
from PySide6.QtCore import QSettings, Qt
from ui.components.q_labeled_slider import QLabeledSlider # Custom Component
import logging
from typing import Optional

from ui.theme_manager import ThemeManager

class ConfigView(QWidget):
    """
    Tab 5: Configuration
    Allows changing UI themes and global application settings.
    """
    def __init__(self, parent: Optional[QWidget] = None, app_state = None) -> None:
        super().__init__(parent)
        self.state = app_state
        self.setup_ui()

    # MCCC FIX: Removed showEvent() handler that was blocking main thread on tab switches
    # UI refreshes should be signal-driven, not event-driven
    
    def refresh_ui(self) -> None:
        """Updates all widgets to match current AppState."""
        s = self.state.settings
        
        # Block signals to prevent feedback loops during update
        self.spin_buf_before.blockSignals(True)
        self.spin_buf_after.blockSignals(True)
        self.gpu_edit.blockSignals(True)
        self.order_combo.blockSignals(True)
        self.seed_spin.blockSignals(True)
        self.outputs_spin.blockSignals(True)
        self.retries_spin.blockSignals(True)
        self.chk_asr.blockSignals(True)
        self.asr_thresh.blockSignals(True)
        self.chk_watermark.blockSignals(True)
        
        try:
            self.spin_buf_before.setValue(s.chapter_buffer_before_ms)
            self.spin_buf_after.setValue(s.chapter_buffer_after_ms)
            self.gpu_edit.setText(s.target_gpus)
            self.order_combo.setCurrentText(s.generation_order)
            self.seed_spin.setValue(s.master_seed)
            self.outputs_spin.setValue(s.num_full_outputs)
            self.retries_spin.setValue(s.max_attempts)
            self.chk_asr.setChecked(s.asr_validation_enabled)
            self.asr_thresh.set_value(s.asr_threshold)
            self.chk_watermark.setChecked(s.disable_watermark)
        finally:
            self.spin_buf_before.blockSignals(False)
            self.spin_buf_after.blockSignals(False)
            self.gpu_edit.blockSignals(False)
            self.order_combo.blockSignals(False)
            self.seed_spin.blockSignals(False)
            self.outputs_spin.blockSignals(False)
            self.retries_spin.blockSignals(False)
            self.chk_asr.blockSignals(False)
            self.asr_thresh.blockSignals(False)
            self.chk_watermark.blockSignals(False)
        
    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        
        # --- Header ---
        header = QLabel("Application Configuration")
        font = header.font()
        font.setPointSize(14)
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)
        
        # --- Theme Settings ---
        theme_group = QGroupBox("Interface Personalization")
        t_layout = QFormLayout(theme_group)
        
        # Theme Selector
        self.theme_combo = QComboBox()
        themes = ThemeManager.get_available_themes()
        self.theme_combo.addItems(themes)
        
        # Load setting from AppState (Source of Truth)
        current = self.state.theme_name if hasattr(self.state, 'theme_name') else "dark_teal.xml"
        self.theme_combo.setCurrentText(current)
        
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        t_layout.addRow("Select Theme:", self.theme_combo)
        
        # Import Button
        btn_layout = QVBoxLayout()
        self.import_btn = QPushButton("📂 Import Custom Theme (.xml)")
        self.import_btn.clicked.connect(self.import_theme)
        btn_layout.addWidget(self.import_btn)
        
        t_layout.addRow("Custom Theme:", btn_layout)
        
        layout.addWidget(theme_group)
        
        # --- Group 2: Generation Defaults ---
        gen_group = QGroupBox("Generation Defaults")
        g_layout = QFormLayout(gen_group)
        
        self.spin_buf_before = QSpinBox()
        self.spin_buf_before.setRange(0, 10000)
        self.spin_buf_before.setSingleStep(100)
        self.spin_buf_before.setSuffix(" ms")
        self.spin_buf_before.setValue(self.state.settings.chapter_buffer_before_ms)
        self.spin_buf_before.valueChanged.connect(lambda v: self.update_setting('chapter_buffer_before_ms', v))
        
        self.spin_buf_after = QSpinBox()
        self.spin_buf_after.setRange(0, 10000)
        self.spin_buf_after.setSingleStep(100)
        self.spin_buf_after.setSuffix(" ms")
        self.spin_buf_after.setValue(self.state.settings.chapter_buffer_after_ms)
        self.spin_buf_after.valueChanged.connect(lambda v: self.update_setting('chapter_buffer_after_ms', v))
        
        g_layout.addRow("Buffer BEFORE Chapter:", self.spin_buf_before)
        g_layout.addRow("Buffer AFTER Chapter:", self.spin_buf_after)
        
        layout.addWidget(gen_group)
        
        # --- Group 3: Advanced Generation Configuration (Was in Gen View) ---
        adv_group = QGroupBox("Advanced Engine Configuration")
        a_layout = QFormLayout(adv_group)

        # GPU Device Handling (Dynamic Checkboxes)
        import torch
        self.gpu_checkboxes = []
        gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
        
        if gpu_count > 0:
            gpu_group = QGroupBox("Target GPUs")
            gpu_layout = QVBoxLayout(gpu_group)
            
            # Parse existing setting (e.g. "cuda:0,cuda:1")
            current_gpus = [g.strip() for g in self.state.settings.target_gpus.split(',')]
            
            for i in range(gpu_count):
                gpu_name = f"cuda:{i}"
                prop_name = torch.cuda.get_device_name(i)
                chk = QCheckBox(f"{gpu_name} ({prop_name})")
                
                # Check it if it's in the current settings string
                if gpu_name in current_gpus:
                    chk.setChecked(True)
                
                # Connect signal to update the settings string whenever a box is checked/unchecked
                chk.stateChanged.connect(self._update_gpu_setting)
                self.gpu_checkboxes.append((gpu_name, chk))
                gpu_layout.addWidget(chk)
                
            a_layout.addRow(gpu_group)
        else:
            # Fallback for CPU-only systems
            self.gpu_edit = QLineEdit("cpu")
            self.gpu_edit.setReadOnly(True)
            a_layout.addRow("Goal Device(s):", self.gpu_edit)
            
        # Gen Order
        self.order_combo = QComboBox()
        self.order_combo.addItems(["linear", "random", "interleaved"])
        self.order_combo.setCurrentText(self.state.settings.generation_order)
        self.order_combo.currentTextChanged.connect(
            lambda t: setattr(self.state.settings, 'generation_order', t)
        )
        a_layout.addRow("Order:", self.order_combo)

        # Seeds
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(-1, 2147483647)
        self.seed_spin.setSpecialValueText("Random (-1)")
        self.seed_spin.setValue(self.state.settings.master_seed)
        self.seed_spin.valueChanged.connect(
            lambda v: setattr(self.state.settings, 'master_seed', v)
        )
        a_layout.addRow("Base Seed:", self.seed_spin)

        # Full Outputs
        self.outputs_spin = QSpinBox()
        self.outputs_spin.setRange(1, 100)
        self.outputs_spin.setValue(self.state.settings.num_full_outputs)
        self.outputs_spin.valueChanged.connect(
            lambda v: setattr(self.state.settings, 'num_full_outputs', v)
        )
        a_layout.addRow("Full Outputs:", self.outputs_spin)
        
        # Max Retries
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 50)
        self.retries_spin.setValue(self.state.settings.max_attempts)
        self.retries_spin.valueChanged.connect(
            lambda v: setattr(self.state.settings, 'max_attempts', v)
        )
        a_layout.addRow("ASR Max Retries:", self.retries_spin)

        # ASR/Watermark Container
        chk_layout = QVBoxLayout()
        
        self.chk_asr = QGroupBox("ASR Validation")
        self.chk_asr.setCheckable(True)
        self.chk_asr.setChecked(self.state.settings.asr_validation_enabled)
        self.chk_asr.toggled.connect(
            lambda c: setattr(self.state.settings, 'asr_validation_enabled', c)
        )
        # ASR Threshold inside logic
        asr_l = QFormLayout(self.chk_asr)
        self.asr_thresh = QLabeledSlider("Acceptance Threshold", 0.1, 1.0, self.state.settings.asr_threshold)
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
        
        layout.addWidget(adv_group)
        layout.addStretch()
        
    def on_theme_changed(self, theme_name: str) -> None:
        """Apply theme immediately when combo changes."""
        try:
            # Update State
            if hasattr(self.state, 'theme_name'):
                self.state.theme_name = theme_name
                # self.state.theme_invert = ... (if implemented)
            
            # Apply Visuals
            app = QApplication.instance()
            if app:
                ThemeManager.apply_theme(app, theme_name)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not apply theme: {e}")

    def _update_gpu_setting(self) -> None:
        """Called when a GPU checkbox is toggled to rebuild the comma-separated string."""
        selected_gpus = []
        # Support dynamic checkboxes if they exist, otherwise fallback
        if hasattr(self, 'gpu_checkboxes'):
            for gpu_name, chk in self.gpu_checkboxes:
                if chk.isChecked():
                    selected_gpus.append(gpu_name)
                    
        # Update the state string (e.g., "cuda:0,cuda:1")
        # If none selected, fallback to cpu to avoid breaking workers
        final_str = ",".join(selected_gpus) if selected_gpus else "cpu"
        setattr(self.state.settings, 'target_gpus', final_str)

    def update_setting(self, key: str, value: int) -> None:
        """Generic update for integer settings."""
        if hasattr(self.state.settings, key):
            setattr(self.state.settings, key, value)
            
    def import_theme(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Theme XML", "", "XML Files (*.xml);;All Files (*.*)"
        )
        if path:
            try:
                # Update UI
                if self.theme_combo.findText(path) == -1:
                    self.theme_combo.addItem(path)
                self.theme_combo.setCurrentText(path)
                
                QMessageBox.information(self, "Success", f"Custom theme loaded from:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Import Failed", f"Invalid theme file:\n{e}")
