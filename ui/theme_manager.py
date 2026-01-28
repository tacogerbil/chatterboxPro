from PySide6.QtWidgets import QApplication
import logging

class ThemeManager:
    @staticmethod
    def get_available_themes() -> list[str]:
        try:
            from qt_material import list_themes
            return list_themes()
        except ImportError:
            return []

    @staticmethod
    def apply_theme(app: QApplication, theme_name: str, invert_secondary: bool = False):
        """
        Applies a theme globally to the QApplication instance.
        PURE FUNCTION: Does not save state. State is managed by AppState/ConfigService.
        """
        try:
            from qt_material import apply_stylesheet
            from PySide6.QtWidgets import QStyleFactory
            
            # MCCC: Ensure Consistent Base Style (Fusion)
            # This provides correct native heuristics, disabled states, and contrast rules
            # before we apply our custom palette and spreadsheet.
            if "Fusion" in QStyleFactory.keys():
                app.setStyle("Fusion")
            
            # 'invert_secondary' is sometimes needed for specific themes to look right
            extra = {'invert_secondary': invert_secondary} if invert_secondary else {}
            
            if theme_name.endswith('.xml'):
                    apply_stylesheet(app, theme=theme_name, **extra)
                    ThemeManager._sync_palette(app, theme_name, extra)
            else:
                    # Check if it's a built-in theme name or path
                    apply_stylesheet(app, theme=theme_name, **extra)
                    ThemeManager._sync_palette(app, theme_name, extra)
                    
            print(f"[ThemeManager] Applied theme: {theme_name}")
                
        except Exception as e:
            logging.error(f"Failed to apply theme {theme_name}: {e}")
            # Do not raise, fallback to default? Or raise? User wants visible errors.
            raise e

    @staticmethod
    def _sync_palette(app: QApplication, theme_name: str, extra: dict):
        """
        MCCC Compliance: Synchronizes the QPalette with the qt-material config using Canonical Qt Roles.
        Crucial for QStyledItemDelegates, placeholders, and unstyled widgets.
        """
        try:
            from qt_material import get_theme
            from PySide6.QtGui import QPalette, QColor
            from PySide6.QtCore import Qt
            
            # Load theme config (returns dict of colors)
            theme_config = get_theme(theme_name, **extra)
            
            # 1. Start with Standard Fusion Palette (Canonical Base)
            palette = app.style().standardPalette()
            
            # 2. Extract Colors from Theme Config
            # qt-material keys: primaryColor (Accent), secondaryColor (Background), textColor
            primary_color = QColor(theme_config.get('primaryColor', '#2E86C1'))
            secondary_color = QColor(theme_config.get('secondaryColor', '#232629'))
            text_color = QColor(theme_config.get('textColor', '#ffffff'))
            
            # Derived Colors
            placeholder_color = QColor(text_color)
            placeholder_color.setAlpha(128) # 50% opacity
            
            # 3. Map to Canonical Roles (User Specified MCCC)
            
            # Window / Backgrounds
            palette.setColor(QPalette.Window, secondary_color)
            palette.setColor(QPalette.Base, secondary_color) # Or secondaryLightColor if available
            palette.setColor(QPalette.AlternateBase, primary_color) # Valid contrast? Or lighter bg?
            # Keeping Base == Window is safest for dark themes unless we strictly know the hierarchy.
            
            # Text / Foreground
            palette.setColor(QPalette.Text, text_color)
            palette.setColor(QPalette.WindowText, text_color)
            palette.setColor(QPalette.ButtonText, text_color)
            palette.setColor(QPalette.BrightText, Qt.red) # Warning/Error logic usually
            
            # Inputs
            palette.setColor(QPalette.PlaceholderText, placeholder_color)
            
            # Interactive / Accents
            palette.setColor(QPalette.Highlight, primary_color)
            palette.setColor(QPalette.HighlightedText, text_color) # Assuming text works on accent
            palette.setColor(QPalette.Link, primary_color) # Use accent for links
            palette.setColor(QPalette.LinkVisited, primary_color.darker())
            
            app.setPalette(palette)
            
        except Exception as e:
            logging.warning(f"[ThemeManager] Could not sync palette: {e}")
