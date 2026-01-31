import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional

class TemplateService:
    def __init__(self, templates_dir: str = None):
        """
        Initialize template service.
        
        Args:
            templates_dir: Path to templates directory. If None, uses project-relative default.
        """
        if templates_dir is None:
            # Get project root (parent of 'core' directory)
            project_root = Path(__file__).parent.parent
            templates_dir = project_root / "Templates"
        
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(exist_ok=True, parents=True)

    def list_templates(self) -> List[str]:
        """Returns a sorted list of template names (without extension)."""
        try:
            files = self.templates_dir.glob("*.json")
            return sorted([f.stem for f in files])
        except Exception as e:
            logging.error(f"Failed to list templates: {e}")
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
