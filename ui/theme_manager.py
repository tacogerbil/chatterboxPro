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
        MCCC Compliance: Synchronizes the QPalette with the qt-material config.
        Crucial for QStyledItemDelegates that read Palette instead of CSS.
        """
        try:
            from qt_material import get_theme
            from PySide6.QtGui import QPalette, QColor
            from PySide6.QtCore import Qt
            
            # Load theme config (returns dict of colors)
            theme_config = get_theme(theme_name, **extra)
            
            # Create Palette
            palette = QPalette()
            
            # Map Common Colors
            # Note: qt-material uses keys like 'primaryColor', 'secondaryColor', 'textColor', 'secondaryLightColor'
            
            bg_color = QColor(theme_config.get('primaryColor', '#000000')) # Usually dark in dark themes
            # Correct mapping might need inspection of qt-material dict keys.
            # Assuming 'textColor' exists.
            
            text_color_str = theme_config.get('textColor', '#ffffff')
            bg_color_str = theme_config.get('primaryColor', '#222222') # Often the base
            
            # Set Text Roles
            text_color = QColor(text_color_str)
            palette.setColor(QPalette.WindowText, text_color)
            palette.setColor(QPalette.Text, text_color)
            palette.setColor(QPalette.ButtonText, text_color)
            palette.setColor(QPalette.ToolTipText, text_color)
            
            # Set Background Roles?
            # Be careful not to break the CSS 'engine' by overriding too much, 
            # but setting specific roles helps Delegates.
            
            app.setPalette(palette)
            
        except Exception as e:
            logging.warning(f"[ThemeManager] Could not sync palette: {e}")
