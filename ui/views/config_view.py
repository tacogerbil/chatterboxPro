from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton, 
    QGroupBox, QFormLayout, QFileDialog, QMessageBox, QApplication, QSpinBox
)
from PySide6.QtCore import QSettings, Qt
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
        # self.settings = QSettings("ChatterboxPro", "ThemeConfig") # REMOVED MCCC Violation
        self.setup_ui()
        
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
        
        t_layout.addRow("Custom Theme:", btn_layout)
        
        layout.addWidget(theme_group)
        
        # --- Group 2: Generation Defaults ---
        gen_group = QGroupBox("Generation Defaults")
        g_layout = QFormLayout(gen_group)
        
        self.spin_chap_buf = QSpinBox()
        self.spin_chap_buf.setRange(0, 10000)
        self.spin_chap_buf.setSingleStep(100)
        self.spin_chap_buf.setSuffix(" ms")
        self.spin_chap_buf.setValue(self.state.settings.chapter_buffer_ms)
        self.spin_chap_buf.valueChanged.connect(self.on_buffer_changed)
        
        g_layout.addRow("Chapter Auto-Pause Buffer:", self.spin_chap_buf)
        
        layout.addWidget(gen_group)
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

    def on_buffer_changed(self, value: int) -> None:
        """Update buffer setting in state."""
        self.state.settings.chapter_buffer_ms = value
            
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
