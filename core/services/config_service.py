import json
import logging
from pathlib import Path
from dataclasses import asdict
from typing import Dict, Any

from core.state import AppState

class ConfigService:
    """
    Manages persistent application configuration.
    Follows MCCC:
    - Separation of Concerns: Isolated I/O for settings.
    - Explicit Interface: load_state / save_state.
    """
    def __init__(self, config_dir: str = "config", filename: str = "last_session.json"):
        self.config_dir = Path(config_dir)
        self.config_path = self.config_dir / filename
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self, app_state: AppState) -> None:
        """Loads persistent settings into the provided AppState object."""
        if not self.config_path.exists():
            logging.info("No previous session config found. Using defaults.")
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 1. Restore Generation Settings
            if 'settings' in data:
                settings_data = data['settings']
                # MCCC: Robust Typed Loading
                # Inspect dataclass fields to convert JSON types (e.g. str -> float) if necessary
                from dataclasses import fields
                type_map = {f.name: f.type for f in fields(app_state.settings)}
                
                for key, value in settings_data.items():
                    if hasattr(app_state.settings, key):
                        # Attempt to cast if type is known
                        target_type = type_map.get(key)
                        
                        try:
                            # Handle simple primitives
                            if target_type == float and isinstance(value, (str, int)):
                                value = float(value)
                            elif target_type == int and isinstance(value, (str, float)):
                                value = int(value)
                            elif target_type == bool and isinstance(value, str):
                                value = value.lower() == "true"
                        except (ValueError, TypeError):
                            # Fallback: keep original value but log warning
                            logging.warning(f"Config type mismatch for {key}: expected {target_type}, got {type(value)}")
                            
                        setattr(app_state.settings, key, value)
            
            # 2. Restore Global State (Paths, etc.)
            # Whitelist of safe fields to restore
            safe_globals = {
                'session_name', 'source_file_path', 'ref_audio_path', 
                'model_path', # Added for custom model path persistence
                'auto_regen_main', 'auto_regen_sub', 
                'auto_assemble_after_run', 'aggro_clean_on_parse',
                'theme_name', 'theme_invert'
            }
            
            for key in safe_globals:
                if key in data:
                    setattr(app_state, key, data[key])
                    
            logging.info(f"Session state loaded from {self.config_path}")
            
        except Exception as e:
            logging.error(f"Failed to load session config: {e}")

    def save_state(self, app_state: AppState) -> None:
        """Saves the current AppState to disk."""
        try:
            # 1. Serialize Generation Settings
            settings_dict = asdict(app_state.settings)
            
            # 2. Serialize Safe Global Fields
            global_data = {
                'session_name': app_state.session_name,
                'source_file_path': app_state.source_file_path,
                'ref_audio_path': app_state.ref_audio_path,
                'model_path': app_state.model_path,
                'auto_regen_main': app_state.auto_regen_main,
                'auto_regen_sub': app_state.auto_regen_sub,
                'auto_assemble_after_run': app_state.auto_assemble_after_run,
                'aggro_clean_on_parse': app_state.aggro_clean_on_parse,
                'theme_name': app_state.theme_name,
                'theme_invert': app_state.theme_invert
            }
            
            # Combine
            export_data = {
                'version': '1.0', # Future migration support
                'settings': settings_dict,
                **global_data
            }
             
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=4)
                
            logging.info(f"Session state saved to {self.config_path}")
            
        except Exception as e:
            logging.error(f"Failed to save session config: {e}")
