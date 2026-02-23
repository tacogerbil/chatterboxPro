import os
import shutil
import logging
import json
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
        target = Path(outputs_dir)
        if not target.is_absolute():
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.outputs_dir = base_dir / target
        else:
            self.outputs_dir = target
            
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

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

    def save_session(self, session_name: str, data: Dict[str, Any]) -> bool:
        """
        Saves session data to JSON.
        Data dict should contain: 'source_file_path', 'sentences', 'generation_settings'.
        """
        if not session_name:
            logging.error("Cannot save session: No session name provided.")
            return False
            
        session_path = Path(self.outputs_dir) / session_name
        try:
            session_path.resolve().mkdir(parents=True, exist_ok=True)
            
            json_path = session_path / f"{session_name}_session.json"
            
            # Create Backup if exists
            if json_path.exists():
                try:
                    backup_path = session_path / f"{session_name}_session.bak"
                    shutil.copy2(json_path, backup_path)
                    logging.info(f"Created backup: {backup_path}")
                except Exception as e:
                    logging.warning(f"Failed to create backup: {e}")
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
                
            logging.info(f"Session '{session_name}' saved to {json_path}")
            return True
        except Exception as e:
            logging.error(f"Failed to save session '{session_name}': {e}")
            return False

    def save_current_session(self, app_state: Any) -> bool:
        """
        Convenience method to save the currently active session in AppState.
        """
        if not app_state.session_name:
            # Cannot save unnamed session
            return False
            
        import dataclasses
        data = {
            "source_file_path": app_state.source_file_path,
            "sentences": app_state.sentences,
            "generation_settings": dataclasses.asdict(app_state.settings),
            "ref_audio_path": app_state.ref_audio_path,
            "voice_preset": getattr(app_state.settings, 'voice_preset', 'Custom')
        }
        return self.save_session(app_state.session_name, data)

    def load_session(self, session_dir_path: str) -> Optional[Dict[str, Any]]:
        """
        Loads session data from a directory.
        Returns a dict with 'session_name', 'source_file_path', 'sentences', 'generation_settings', etc.
        """
        path = Path(session_dir_path)
        if not path.exists():
            logging.error(f"Session path not found: {path}")
            return None
            
        json_path = path / f"{path.name}_session.json"
        
        # Fallback: try finding any json if naming convention differs
        if not json_path.exists():
             jsons = list(path.glob("*_session.json"))
             if jsons:
                 json_path = jsons[0]
        
        if not json_path.exists():
            logging.error(f"Session JSON not found in {path}")
            return None
            
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Enrich with determined name
            data['session_name'] = path.name
            return data
        except Exception as e:
            logging.error(f"Failed to load session from {json_path}: {e}")
            return None

    def get_progress_journal_path(self, session_name: str) -> Path:
        """Returns the path to the crash-safe progress journal for a given session."""
        return Path(self.outputs_dir) / session_name / "generation_progress.jsonl"

    def recover_from_journal(self, app_state: Any) -> Dict[str, int]:
        """
        Re-links session sentences to their WAV files by reading the crash-safe
        progress journal. Only entries with status 'success' are marked as done.
        Failed placeholder entries are explicitly kept as failed so they get re-queued.

        Returns stats: matched, already_linked, failed_kept, no_entry.
        """
        stats = {"matched": 0, "already_linked": 0, "failed_kept": 0, "no_entry": 0}

        if not app_state.session_name or not app_state.sentences:
            logging.warning("recover_from_journal: No active session or empty sentence list.")
            return stats

        journal_path = self.get_progress_journal_path(app_state.session_name)
        if not journal_path.exists():
            logging.warning(f"No progress journal found at: {journal_path}")
            return stats

        # Parse journal into a uuid -> record dict (last entry wins on UUID collision)
        journal: Dict[str, Dict] = {}
        with open(journal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    uid = record.get("uuid")
                    if uid:
                        journal[uid] = record
                except json.JSONDecodeError:
                    pass  # Skip malformed lines written during a crash

        logging.info(f"Journal loaded: {len(journal)} entries for session '{app_state.session_name}'.")

        # Back up session JSON before modifying
        self.save_current_session(app_state)

        for sentence in app_state.sentences:
            if sentence.get("is_pause") or sentence.get("is_chapter_heading"):
                continue

            uid = sentence.get("uuid", "")
            if not uid:
                continue

            # If already correctly linked, skip
            if sentence.get("tts_generated") == "yes":
                existing = sentence.get("audio_path", "")
                if existing and Path(existing).exists():
                    stats["already_linked"] += 1
                    continue

            record = journal.get(uid)
            if not record:
                stats["no_entry"] += 1
                continue

            status = record.get("status", "")
            wav_path = record.get("path", "")

            if status == "success" and wav_path and Path(wav_path).exists():
                sentence["tts_generated"] = "yes"
                sentence["audio_path"] = wav_path
                sentence["marked"] = False
                stats["matched"] += 1
            else:
                # Explicit failure or missing file — keep as failed so it reruns
                sentence["tts_generated"] = "failed"
                sentence["marked"] = True
                stats["failed_kept"] += 1

        logging.info(
            f"Recovery complete: matched={stats['matched']}, "
            f"already_linked={stats['already_linked']}, "
            f"failed_kept={stats['failed_kept']}, no_entry={stats['no_entry']}"
        )
        return stats
