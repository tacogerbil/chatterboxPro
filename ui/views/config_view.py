from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton, 
    QGroupBox, QFormLayout, QFileDialog, QMessageBox, QApplication
)
from PySide6.QtCore import QSettings, Qt
import logging
from typing import Optional

# MCCC: Helper for theme management
class ThemeManager:
    @staticmethod
    def get_available_themes() -> list[str]:
        try:
            from qt_material import list_themes
            return list_themes()
        except ImportError:
            return []

    @staticmethod
    def apply_theme(theme_name: str, custom_styles: dict = None, invert_secondary: bool = False):
        """Applies a theme globally to the QApplication instance."""
        try:
            from qt_material import apply_stylesheet
            app = QApplication.instance()
            if app:
                # 'invert_secondary' is sometimes needed for specific themes to look right
                extra = {'invert_secondary': invert_secondary} if invert_secondary else {}
                
                if theme_name.endswith('.xml'):
                     apply_stylesheet(app, theme=theme_name, **extra)
                else:
                     # Check if it's a built-in theme name or path
                     apply_stylesheet(app, theme=theme_name, **extra)
                     
                # Save to QSettings
                settings = QSettings("ChatterboxPro", "ThemeConfig")
                settings.setValue("current_theme", theme_name)
                settings.setValue("invert_desc", invert_secondary)
                
        except Exception as e:
            logging.error(f"Failed to apply theme {theme_name}: {e}")
            raise e

class ConfigView(QWidget):
    """
    Tab 5: Configuration
    Allows changing UI themes and global application settings.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = QSettings("ChatterboxPro", "ThemeConfig")
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
        
        # Load current setting
        current = self.settings.value("current_theme", "dark_teal.xml")
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
        layout.addStretch()
        
    def on_theme_changed(self, theme_name: str) -> None:
        """Apply theme immediately when combo changes."""
        try:
            # Some light themes might need inversion, for now default False
            # We could add a checkbox for 'Invert Secondary' if user wants granular control
            ThemeManager.apply_theme(theme_name)
            # QMessageBox.information(self, "Theme Applied", f"Switched to {theme_name}") 
            # (No popup needed, visual feedback is instant)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not apply theme: {e}")
            
    def import_theme(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Theme XML", "", "XML Files (*.xml);;All Files (*.*)"
        )
        if path:
            try:
                ThemeManager.apply_theme(path)
                # Add to combo just for display (optional)
                if self.theme_combo.findText(path) == -1:
                    self.theme_combo.addItem(path)
                self.theme_combo.setCurrentText(path)
                
                QMessageBox.information(self, "Success", f"Custom theme loaded from:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Import Failed", f"Invalid theme file:\n{e}")
