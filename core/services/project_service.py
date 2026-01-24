import os
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

class ProjectService:
    """
    Handles project-level logical operations:
    - Resetting generation status
    - File management (deletion)
    - Session management
    """
    def __init__(self, outputs_dir: str = "Outputs_Pro"):
        self.outputs_dir = outputs_dir

    def get_audio_path(self, session_name: str, audio_filename: str) -> Path:
        """Construct the absolute path for an audio file."""
        return Path(self.outputs_dir) / session_name / "Sentence_wavs" / audio_filename

    def reset_generation_status(self, sentences: List[Dict[str, Any]], session_name: str) -> Dict[str, int]:
        """
        Resets generation status flags for all sentences and deletes associated audio files.
        Returns stats about the operation.
        """
        stats = {"reset_count": 0, "deleted_files": 0, "errors": 0}
        
        if not sentences:
            return stats

        # 1. Clear flags in data
        for item in sentences:
            if item.get('tts_generated'):
                item['tts_generated'] = None
                item['marked'] = False
                item.pop('error_message', None)
                item.pop('similarity_ratio', None)
                item.pop('generation_seed', None)
                stats["reset_count"] += 1

        # 2. Delete files
        if session_name:
            audio_dir = Path(self.outputs_dir) / session_name / "Sentence_wavs"
            if audio_dir.exists():
                for f in audio_dir.glob("audio_*.wav"):
                    try:
                        f.unlink()
                        stats["deleted_files"] += 1
                    except OSError as e:
                        logging.error(f"Failed to delete {f}: {e}")
                        stats["errors"] += 1
                        
        return stats

    def delete_audio_file(self, session_name: str, uuid_str: str) -> bool:
        """
        Deletes a specific audio file for a sentence item.
        """
        if not session_name or not uuid_str:
            return False
            
        f_path = Path(self.outputs_dir) / session_name / "Sentence_wavs" / f"audio_{uuid_str}.wav"
        
        if f_path.exists():
            try:
                os.remove(f_path)
                logging.info(f"Deleted orphaned audio file: {f_path.name}")
                return True
            except OSError as e:
                logging.error(f"Failed to delete audio file {f_path}: {e}")
                return False
        return False
