import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional

class TemplateService:
    def __init__(self, templates_dir: str = "Templates"):
        """
        Initialize template service.
        
        Args:
            templates_dir: Path to templates directory relative to working directory.
        """
        target = Path(templates_dir)
        if not target.is_absolute():
            # to survive QFileDialog CWD manipulation on Windows
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.templates_dir = base_dir / target
        else:
            self.templates_dir = target
            
        self.templates_dir.mkdir(exist_ok=True, parents=True)

    def list_templates(self) -> List[str]:
        """Returns a sorted list of template names (without extension)."""
        try:
            logging.debug(f"Looking for templates in: {self.templates_dir}")
            files = list(self.templates_dir.glob("*.json"))
            logging.debug(f"Found {len(files)} template files: {[f.name for f in files]}")
            result = sorted([f.stem for f in files])
            logging.debug(f"Returning template names: {result}")
            return result
        except Exception as e:
            logging.error(f"Failed to list templates: {e}", exc_info=True)
            return []

    def load_template(self, name: str) -> Optional[Dict]:
        """Loads a template by name."""
        try:
            path = self.templates_dir / f"{name}.json"
            if not path.exists():
                return None
            
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load template '{name}': {e}")
            return None

    def save_template(self, name: str, settings: Dict) -> bool:
        """Saves settings to a template file."""
        try:
            path = self.templates_dir / f"{name}.json"
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            return True
        except Exception as e:
            logging.error(f"Failed to save template '{name}': {e}")
            return False

    def delete_template(self, name: str) -> bool:
        """Deletes a template file."""
        try:
            path = self.templates_dir / f"{name}.json"
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception as e:
            logging.error(f"Failed to delete template '{name}': {e}")
            return False
