import logging
import subprocess
from pathlib import Path
import shutil
import uuid
import ffmpeg
from pydub import AudioSegment
from PySide6.QtCore import QObject, Signal, QThread, Slot
import pygame

from chatterbox.models.s3gen import S3GEN_SR
from core.state import AppState

class AudioWorker(QThread):
    """
    Background worker for Audiobook Assembly and Export.
    Handles FFmpeg operations without blocking the UI.
    """
    progress_update = Signal(str) # status message
    finished = Signal(str) # output path or success message
    error_occurred = Signal(str)

    def __init__(self, job_type: str, data: dict, settings: dict, session_path: Path):
        super().__init__()
        self.job_type = job_type # 'assemble_single' or 'export_chapters'
        self.data = data # dict containing 'items', 'output_path', 'metadata' etc
        self.settings = settings
        self.session_path = session_path
        self.stop_requested = False

    def run(self):
        try:
            if self.job_type == 'assemble_single':
                self._assemble_single(
                    self.data['items'], 
                    self.data['output_path'], 
                    self.data.get('is_for_acx', False),
                    self.data.get('metadata', None)
                )
            elif self.job_type == 'export_chapters':
                self._export_chapters(
                    self.data['to_export'], # List of (items, path, metadata) tuples
                    self.data['output_dir']
                )
        except Exception as e:
            logging.error(f"AudioWorker failed: {e}", exc_info=True)
            self.error_occurred.emit(str(e))

    def _assemble_single(self, items, output_path_str, is_for_acx, metadata):
        output_path = Path(output_path_str)
        temp_dir = self.session_path / f"assembly_temp_{uuid.uuid4().hex}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            self.progress_update.emit("Creating file list...")
            concat_list_path = temp_dir / "concat_list.txt"
            
            # --- VALIDATION ---
            valid_items_count = 0
            
            with open(concat_list_path, 'w', encoding='utf-8') as f:
                for s_data in items:
                    # Pauses
                    if s_data.get("is_pause"):
                        dur = s_data.get("duration", 1000)
                        pause_file = temp_dir / f"pause_{s_data['uuid']}.wav"
                        AudioSegment.silent(duration=dur).export(pause_file, format="wav")
                        f.write(f"file '{pause_file.absolute()}'\n")
                        valid_items_count += 1
                        continue
                        
                    # Silence between chunks
                    is_para = not self.settings.chunking_enabled and s_data.get('paragraph') == 'yes'
                    pause_dur = 750 if is_para else self.settings.silence_duration
                    silence_file = temp_dir / f"silence_{s_data['uuid']}.wav"
                    AudioSegment.silent(duration=pause_dur).export(silence_file, format="wav")
                    f.write(f"file '{silence_file.absolute()}'\n")
                    
                    # Chapter Pre-Silence
                    if s_data.get("is_chapter_heading"):
                         chap_silence = temp_dir / f"chap_pre_{s_data['uuid']}.wav"
                         AudioSegment.silent(duration=1500).export(chap_silence, format="wav")
                         f.write(f"file '{chap_silence.absolute()}'\n")

                    # Main Audio
                    audio_path = self.session_path / "Sentence_wavs" / f"audio_{s_data['uuid']}.wav"
                    if audio_path.exists():
                        f.write(f"file '{audio_path.absolute()}'\n")
                        valid_items_count += 1
                    
                    # Chapter Post-Silence
                    if s_data.get("is_chapter_heading"):
                         chap_silence_post = temp_dir / f"chap_post_{s_data['uuid']}.wav"
                         AudioSegment.silent(duration=1500).export(chap_silence_post, format="wav")
                         f.write(f"file '{chap_silence_post.absolute()}'\n")

            if valid_items_count == 0:
                raise ValueError("No valid audio files found to assemble.")

            # ACX Padding
            if is_for_acx:
                head = temp_dir / "acx_head.wav"
                tail = temp_dir / "acx_tail.wav"
                AudioSegment.silent(duration=1000).export(head, format="wav")
                AudioSegment.silent(duration=2000).export(tail, format="wav")
                
                with open(concat_list_path, 'r') as f: original = f.read()
                with open(concat_list_path, 'w') as f:
                    f.write(f"file '{head.absolute()}'\n")
                    f.write(original)
                    f.write(f"file '{tail.absolute()}'\n")
            
            # FFmpeg Concat
            self.progress_update.emit("Concatenating audio...")
            raw_combined = temp_dir / "raw_combined.wav"
            (
                ffmpeg.input(str(concat_list_path), format='concat', safe=0, protocol_whitelist='file,pipe')
                .output(str(raw_combined), acodec='pcm_s16le', ar=S3GEN_SR)
                .overwrite_output()
                .run(quiet=False, capture_stderr=True)
            )
            
            path_to_process = raw_combined
            
            # Normalization
            if self.settings.norm_enabled:
                 self.progress_update.emit("Normalizing audio (EBU R128)...")
                 norm_path = temp_dir / "normalized.wav"
                 try:
                     peak = -3.0 if is_for_acx else -1.5
                     target_lufs = self.settings.norm_level
                     (
                         ffmpeg.input(str(path_to_process))
                         .output(str(norm_path), af=f"loudnorm=I={target_lufs}:TP={peak}:LRA=11", ar=S3GEN_SR)
                         .overwrite_output().run(quiet=False, capture_stderr=True)
                     )
                     path_to_process = norm_path
                 except Exception as e:
                     logging.error(f"Normalization failed: {e}")
            
            # Silence Removal
            if self.settings.silence_removal_enabled:
                self.progress_update.emit("Removing silence...")
                sr_path = temp_dir / "silence_removed.wav"
                try:
                    # Using auto-editor from PATH
                    cmd = [
                        "auto-editor", str(path_to_process),
                        "--silent_threshold", str(self.settings.silence_threshold),
                        "--margin", "0.2s",
                        "--no_open",
                        "-o", str(sr_path)
                    ]
                    subprocess.run(cmd, check=True, capture_output=True)
                    if sr_path.exists():
                        path_to_process = sr_path
                except Exception as e:
                    logging.error(f"Silence removal failed: {e}")

            # Export
            self.progress_update.emit(f"Exporting to {output_path.name}...")
            fmt = output_path.suffix.lstrip('.').lower()
            
            if fmt == 'mp3':
                output_args = {'ar': '44100', 'ac': 1, 'audio_bitrate': '192k'}
                if metadata:
                    output_args['metadata'] = [
                        f"title={metadata.get('title', '')}",
                        f"artist={metadata.get('artist', '')}",
                        f"album={metadata.get('album', '')}"
                    ]
                
                (
                    ffmpeg.input(str(path_to_process))
                    .output(str(output_path), **output_args)
                    .overwrite_output().run(quiet=False, capture_stderr=True)
                )
            else:
                shutil.copy(path_to_process, output_path)
                
            self.finished.emit(str(output_path))
            
        finally:
            if temp_dir.exists():
                try: shutil.rmtree(temp_dir, ignore_errors=True)
                except: pass

    def _export_chapters(self, job_list, output_dir):
        """Sequential export of multiple chapters to avoid disk I/O thrashing."""
        total = len(job_list)
        for i, (items, path, metadata) in enumerate(job_list):
            self.progress_update.emit(f"Exporting Chapter {i+1}/{total}: {Path(path).name}")
            # Reuse _assemble_single logic but catch errors so one failure doesn't stop all?
            # Or simplified inline logic?
            # We can re-use _assemble_single but we need to suppress its 'finished' signal emission 
            # if we want to emit one big 'finished' at end.
            # But the 'finished' signal takes a string.
            # We will refactor _assemble_single slightly or just call it and ignoring signal?
            # Signals are emitted by `self`, calling the method directly executes it in THIS thread.
            # So `emit` will happen. 
            # That's fine, the UI might get multiple "Finished" updates or we can differentiate JOB TYPE in connection.
            # For now, let's just run it.
            self._assemble_single(items, path, True, metadata)
            
        self.finished.emit(f"All {total} chapters exported to {output_dir}")

class AudioService(QObject):
    """
    Handles audio playback and audiobook assembly.
    Decoupled from UI widgets.
    """
    # Signals
    playback_started = Signal(str) # uuid or 'preview'
    playback_stopped = Signal()
    playback_finished = Signal()
    assembly_progress = Signal(str) # status message
    assembly_finished = Signal(str) # output path
    assembly_error = Signal(str)
    
    def __init__(self, app_state: AppState):
        super().__init__()
        self.state = app_state
        pygame.mixer.init()
        self.current_sound = None
        self.worker_thread = None
        
    def play_audio(self, uuid_str: str, file_path: str = None):
        """Plays the audio for a given chunk or specific file."""
        if self.current_sound:
            self.stop_playback()
            
        try:
            target_path = file_path
            if not target_path:
                # Default to session path logic
                session_path = Path("Outputs_Pro") / self.state.session_name
                target_path = session_path / "Sentence_wavs" / f"audio_{uuid_str}.wav"
            
            target_path = Path(target_path)
            if not target_path.exists():
                logging.warning(f"Audio file not found: {target_path}")
                return
            
            # Re-init mixer if needed? (Legacy fix)
            # pygame.mixer.quit(); pygame.mixer.init() 
            # Not doing it aggressively unless needed.

            self.current_sound = pygame.mixer.Sound(str(target_path))
            self.current_sound.play()
            self.playback_started.emit(uuid_str)
            
        except Exception as e:
            logging.error(f"Playback failed: {e}")
            self.stop_playback()

    def stop_playback(self):
        if self.current_sound:
            self.current_sound.stop()
            self.current_sound = None
        # pygame.mixer.stop() # Stops all
        self.playback_stopped.emit()

    def assemble_audiobook(self, output_path_str: str, is_for_acx=False, metadata=None):
        """Starts background assembly worker."""
        if self.worker_thread and self.worker_thread.isRunning():
            self.assembly_error.emit("Assembly already in progress.")
            return

        if not self.state.session_name:
            self.assembly_error.emit("No active session.")
            return

        items = sorted(self.state.sentences, key=lambda s: int(s.get('sentence_number', 0)))
        if not items:
            self.assembly_error.emit("No text chunks.")
            return

        session_path = Path("Outputs_Pro") / self.state.session_name
        
        # Prepare Metadata
        if metadata is None:
            metadata = {
                "title": self.state.session_name,
                "artist": "Chatterbox Pro",
                "album": self.state.session_name
            }
        
        # Snapshot settings relative to assembly
        settings_snapshot = self.state.settings # Copy dataclass ideally

        data = {
            "items": items,
            "output_path": output_path_str,
            "is_for_acx": is_for_acx,
            "metadata": metadata
        }
        
        self.worker_thread = AudioWorker('assemble_single', data, settings_snapshot, session_path)
        self._connect_worker_signals()
        self.worker_thread.start()

    def export_chapters(self, output_dir_str: str):
        """Starts background chapter export."""
        if self.worker_thread and self.worker_thread.isRunning():
            self.assembly_error.emit("Job already in progress.")
            return

        output_dir = Path(output_dir_str)
        items = sorted(self.state.sentences, key=lambda s: int(s.get('sentence_number', 0)))
        
        # Group Chapters
        chapters = []
        current_chap = []
        if not any(i.get("is_chapter_heading") for i in items):
            chapters.append(items)
        else:
            for item in items:
                if item.get("is_chapter_heading") and current_chap:
                    chapters.append(current_chap)
                    current_chap = [item]
                else:
                    current_chap.append(item)
            if current_chap: chapters.append(current_chap)

        # Prepare Jobs
        to_export = []
        session_path = Path("Outputs_Pro") / self.state.session_name
        
        for i, chap_items in enumerate(chapters):
            head = next((x for x in chap_items if x.get('is_chapter_heading')), None)
            raw_name = head.get('original_sentence', f"Chapter_{i+1}").strip() if head else f"Chapter_{i+1}"
            safe_name = "".join([c for c in raw_name if c.isalnum() or c in ' ']).rstrip().replace(' ', '_')
            out_path = output_dir / f"{i+1:02d}_{safe_name}.mp3"
            
            meta = {
                "title": raw_name,
                "artist": "Chatterbox Pro",
                "album": self.state.session_name
            }
            to_export.append((chap_items, str(out_path), meta))
            
        data = {
            "to_export": to_export,
            "output_dir": output_dir_str
        }
        
        self.worker_thread = AudioWorker('export_chapters', data, self.state.settings, session_path)
        self._connect_worker_signals()
        self.worker_thread.start()

    def _connect_worker_signals(self):
        self.worker_thread.progress_update.connect(self.assembly_progress)
        self.worker_thread.finished.connect(self._on_worker_finished)
        self.worker_thread.error_occurred.connect(self.assembly_error)
        
    @Slot(str)
    def _on_worker_finished(self, msg):
        self.assembly_finished.emit(msg)
        self.worker_thread = None
