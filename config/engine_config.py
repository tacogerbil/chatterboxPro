# config/engine_config.py
"""
Engine configuration management.
Stores per-engine settings like model paths, parameters, etc.
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional

class EngineConfig:
    """Manages engine-specific configuration."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize engine configuration.
        
        Args:
            config_path: Path to config file. Defaults to 'config/engines.json'
        """
        if config_path is None:
            config_path = Path(__file__).parent / "engines.json"
        
        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Dict[str, Any]]:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load engine config: {e}")
                return self._get_default_config()
        else:
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Dict[str, Any]]:
        """Return default configuration."""
        return {
            'chatterbox': {
                'model_path': '',  # Uses project directory
                'enabled': True
            },
            'xtts': {
                'model_path': '',  # Uses default cache
                'enabled': True
            },
            'f5': {
                'model_path': '',  # Uses default cache
                'enabled': True
            }
        }
    
    def save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error: Failed to save engine config: {e}")
    
    def get_model_path(self, engine_name: str) -> str:
        """Get model path for specific engine."""
        return self.config.get(engine_name, {}).get('model_path', '')
    
    def set_model_path(self, engine_name: str, path: str):
        """Set model path for specific engine."""
        if engine_name not in self.config:
            self.config[engine_name] = {}
        
        self.config[engine_name]['model_path'] = path
        self.save_config()
    
    def is_engine_enabled(self, engine_name: str) -> bool:
        """Check if engine is enabled."""
        return self.config.get(engine_name, {}).get('enabled', True)
    
    def set_engine_enabled(self, engine_name: str, enabled: bool):
        """Enable/disable an engine."""
        if engine_name not in self.config:
            self.config[engine_name] = {}
        
        self.config[engine_name]['enabled'] = enabled
        self.save_config()
    
    def get_all_settings(self, engine_name: str) -> Dict[str, Any]:
        """Get all settings for an engine."""
        return self.config.get(engine_name, {})
    
    def update_settings(self, engine_name: str, settings: Dict[str, Any]):
        """Update multiple settings for an engine."""
        if engine_name not in self.config:
            self.config[engine_name] = {}
        
        self.config[engine_name].update(settings)
        self.save_config()

# Global config instance
_config_instance = None

def get_engine_config() -> EngineConfig:
    """Get global engine config instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = EngineConfig()
    return _config_instance
