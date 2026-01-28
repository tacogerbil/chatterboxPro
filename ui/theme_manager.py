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
            else:
                    # Check if it's a built-in theme name or path
                    apply_stylesheet(app, theme=theme_name, **extra)
                    
            print(f"[ThemeManager] Applied theme: {theme_name}")
                
        except Exception as e:
            logging.error(f"Failed to apply theme {theme_name}: {e}")
            raise e
