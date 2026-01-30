# core/services/assembly_service.py
import logging
import subprocess
from pathlib import Path
import shutil
import uuid
import ffmpeg
from pydub import AudioSegment
from PySide6.QtCore import QObject, Signal, Slot
from chatterbox.models.s3gen import S3GEN_SR
from core.state import AppState

class AssemblyService(QObject):
    """
    Handles final audiobook assembly and post-processing.
    Refactored to be headless (no UI calls).
    """
    assembly_started = Signal()
    assembly_finished = Signal(str) # output_path
    assembly_error = Signal(str)
    
    def __init__(self, app_state: AppState):
        super().__init__()
        self.state = app_state
    
    def _validate_settings(self) -> tuple[bool, str]:
        """
        Validates assembly settings before processing.
        
        Returns:
            (is_valid, error_message) tuple
        """
        from core.constants import (
            MIN_LUFS, MAX_LUFS,
            MIN_SILENCE_THRESHOLD, MAX_SILENCE_THRESHOLD,
            MIN_FRAME_MARGIN, MAX_FRAME_MARGIN,
            MIN_SILENT_SPEED, MAX_SILENT_SPEED
        )
        
        s = self.state.settings
        
        # Validate normalization settings
        if s.norm_enabled:
            if s.norm_level is None:
                return False, "Normalization enabled but target LUFS not set"
            if not (MIN_LUFS <= s.norm_level <= MAX_LUFS):
                return False, f"Target LUFS must be between {MIN_LUFS} and {MAX_LUFS} dB"
        
        # Validate silence removal settings
        if s.silence_removal_enabled:
            if s.silence_threshold is None:
                return False, "Silence removal enabled but threshold not set"
            if not (MIN_SILENCE_THRESHOLD <= s.silence_threshold <= MAX_SILENCE_THRESHOLD):
                return False, f"Silence threshold must be between {MIN_SILENCE_THRESHOLD} and {MAX_SILENCE_THRESHOLD}"
            
            if s.frame_margin is None or s.frame_margin < MIN_FRAME_MARGIN:
                return False, f"Frame margin must be at least {MIN_FRAME_MARGIN}"
            
            if s.silent_speed is None or not (MIN_SILENT_SPEED <= s.silent_speed <= MAX_SILENT_SPEED):
                return False, f"Silent speed must be between {MIN_SILENT_SPEED} and {MAX_SILENT_SPEED}"
        
        return True, ""

    def assemble_audiobook(self, output_path_str: str, is_for_acx=False, metadata=None):
        if not output_path_str: 
            return
            
        self.assembly_started.emit()
        app = self.state # Alias for easier porting
        
        # MCCC: Validate settings before processing
        is_valid, error_msg = self._validate_settings()
        if not is_valid:
            self.assembly_error.emit(f"Invalid settings: {error_msg}")
            return
        
        # Metadata override if provided
        if metadata:
            self.state.settings.metadata_artist = metadata.get("artist", "")
            self.state.settings.metadata_album = metadata.get("album", "")
            self.state.settings.metadata_title = metadata.get("title", "")

        session_name = app.session_name
        if not session_name:
            self.assembly_error.emit("No active session.")
            return

        session_path = Path("Outputs_Pro") / session_name 
        
        all_items_in_order = sorted(app.sentences, key=lambda s: int(s['sentence_number']))
        if not all_items_in_order:
             self.assembly_error.emit("No text chunks to assemble.")
             return

        output_path = Path(output_path_str)
        temp_dir = session_path / f"assembly_temp_{uuid.uuid4().hex}"
        try:
            temp_dir.resolve().mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.assembly_error.emit(f"Failed to create temp dir: {e}")
            return

        try:
            logging.info(f"Step 1: Creating file list for FFmpeg concat...")
            concat_list_path = temp_dir / "concat_list.txt"
            
            with open(concat_list_path, 'w', encoding='utf-8') as f:
                for s_data in all_items_in_order:
                    # Handle pauses
                    if s_data.get("is_pause"):
                        pause_duration_ms = s_data.get("duration", 1000)
                        pause_file = temp_dir / f"pause_{s_data['uuid']}.wav"
                        AudioSegment.silent(duration=int(pause_duration_ms)).export(pause_file, format="wav")
                        f.write(f"file '{pause_file.absolute()}'\n")
                        continue

                    # Silence between chunks
                    if len(app.sentences) > 1: 
                         pause_duration = app.settings.silence_duration
                         silence_file = temp_dir / f"silence_{s_data['uuid']}.wav"
                         AudioSegment.silent(duration=pause_duration).export(silence_file, format="wav")
                         f.write(f"file '{silence_file.absolute()}'\n")

                    # Chapter Heading Silence (Pre) - REMOVED per user request (handled by Auto-Pause)
                    # if s_data.get("is_chapter_heading"):
                    #    chapter_silence = temp_dir / f"chapter_pre_{s_data['uuid']}.wav"
                    #    AudioSegment.silent(duration=1500).export(chapter_silence, format="wav")
                    #    f.write(f"file '{chapter_silence.absolute()}'\n")

                    # Main Audio
                    f_path = session_path / "Sentence_wavs" / f"audio_{s_data['uuid']}.wav"
                    if f_path.exists():
                        f.write(f"file '{f_path.absolute()}'\n")
                    else:
                        logging.warning(f"Audio for {s_data['uuid']} not found.")
            
            # Check file count
            with open(concat_list_path, 'r') as f:
                lines = f.readlines()
            if not lines:
                raise Exception("No audio files found to assemble.")

            # Concat
            raw_combined_path = temp_dir / "raw_combined_audio.wav"
            (
                ffmpeg.input(str(concat_list_path), format='concat', safe=0, protocol_whitelist='file,pipe')
                .output(str(raw_combined_path), acodec='pcm_s16le', ar=S3GEN_SR)
                .overwrite_output()
                .run(quiet=False, capture_stderr=True)
            )
            
            # --- POST-PROCESSING CHAIN ---
            path_to_process = raw_combined_path
            
            # 1. Silence Removal (Auto-Editor)
            if app.settings.silence_removal_enabled:
                logging.info("Step 2: Running Auto-Editor for silence removal...")
                
                # MCCC: Unique filename to prevent conflicts
                unique_id = uuid.uuid4().hex[:8]
                ae_out = temp_dir / f"silence_removed_{unique_id}.wav"
                
                try:
                    cmd = [
                        "auto-editor", str(path_to_process),
                        "--export", str(ae_out),
                        "--margin", f"{app.settings.frame_margin}fps",
                        "--silent-speed", str(app.settings.silent_speed),
                        "--silent-threshold", str(app.settings.silence_threshold),
                        "--no-open"
                    ]
                    
                    logging.info(f"Command: {' '.join(cmd)}")
                    result = subprocess.run(
                        cmd, 
                        check=True, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    if ae_out.exists():
                        path_to_process = ae_out
                        logging.info("Silence removal complete.")
                    else:
                        error_msg = "Auto-Editor finished but output file missing"
                        logging.warning(error_msg)
                        self.assembly_error.emit(f"Warning: {error_msg}. Using original audio.")
                        
                except subprocess.CalledProcessError as e:
                    error_msg = f"Auto-Editor failed: {e.stderr if e.stderr else str(e)}"
                    logging.error(error_msg)
                    self.assembly_error.emit(f"Silence removal failed: {error_msg}")
                    # Continue with original file
                except FileNotFoundError:
                    error_msg = "auto-editor not found. Please install it: pip install auto-editor"
                    logging.error(error_msg)
                    self.assembly_error.emit(error_msg)
            
            # 2. Normalization (EBU R128 / Loudnorm)
            if app.settings.norm_enabled:
                logging.info(f"Step 3: Normalizing to {app.settings.norm_level} LUFS...")
                
                # MCCC: Unique filename to prevent conflicts
                unique_id = uuid.uuid4().hex[:8]
                norm_out = temp_dir / f"normalized_{unique_id}.wav"
                
                try:
                    # MCCC: Use constants for magic numbers
                    from core.constants import EBU_R128_TRUE_PEAK_MAX, EBU_R128_LOUDNESS_RANGE, DEFAULT_SAMPLE_RATE
                    
                    target_i = app.settings.norm_level
                    
                    (
                        ffmpeg.input(str(path_to_process))
                        .filter('loudnorm', I=target_i, TP=EBU_R128_TRUE_PEAK_MAX, LRA=EBU_R128_LOUDNESS_RANGE)
                        .output(str(norm_out), ar=DEFAULT_SAMPLE_RATE)
                        .overwrite_output()
                        .run(quiet=False, capture_stderr=True)
                    )
                    
                    if norm_out.exists():
                        path_to_process = norm_out
                        logging.info("Normalization complete.")
                    else:
                        error_msg = "Normalization output file missing"
                        logging.warning(error_msg)
                        self.assembly_error.emit(f"Warning: {error_msg}. Using previous audio.")
                        
                except ffmpeg.Error as e:
                    error_msg = f"Normalization failed: {e.stderr.decode() if e.stderr else str(e)}"
                    logging.error(error_msg)
                    self.assembly_error.emit(error_msg)
            
            # Export Final
            logging.info(f"Step 4: Final Export to {output_path}...")
            file_format = output_path.suffix.lstrip('.').lower()
            if file_format == 'mp3':
                 output_options = {
                    'ar': '44100',
                    'ac': 1,
                    'b:a': '192k',
                    'metadata': [
                        f'title={app.settings.metadata_title}',
                        f'artist={app.settings.metadata_artist}',
                        f'album={app.settings.metadata_album}'
                    ]
                 }
                 (
                    ffmpeg.input(str(path_to_process))
                    .output(str(output_path), **output_options)
                    .overwrite_output().run(quiet=False, capture_stderr=True)
                 )
            else:
                 # Copy or Convert if not MP3
                 if str(path_to_process) != str(output_path):
                    if file_format == 'wav':
                        shutil.copy2(path_to_process, output_path)
                    else:
                        AudioSegment.from_wav(path_to_process).export(output_path, format=file_format)

            self.assembly_finished.emit(str(output_path))
            
        except Exception as e:
            logging.error(f"Assembly failed: {e}", exc_info=True)
            self.assembly_error.emit(str(e))
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def export_by_chapter(self, output_dir_str):
        if not output_dir_str: return
        
        output_dir = Path(output_dir_str)
        app = self.state
        
        all_items_in_order = sorted([s for s in app.sentences], key=lambda s: int(s['sentence_number']))
        if not all_items_in_order:
            self.assembly_error.emit("No text chunks found.")
            return

        chapters = []
        current_chapter_items = []
        if not any(item.get("is_chapter_heading") for item in all_items_in_order):
            chapters.append(all_items_in_order)
        else:
            for item in all_items_in_order:
                if item.get("is_chapter_heading") and current_chapter_items:
                    chapters.append(current_chapter_items)
                    current_chapter_items = [item]
                else:
                    current_chapter_items.append(item)
            if current_chapter_items:
                chapters.append(current_chapter_items)

        exported_count = 0
        original_sentences = app.sentences
        
        try:
             for i, chapter_items in enumerate(chapters):
                chapter_heading_item = next((item for item in chapter_items if item.get('is_chapter_heading')), None)
                chapter_name_raw = chapter_heading_item.get('original_sentence', f'Chapter_{i+1}').strip() if chapter_heading_item else f"{app.session_name}_Chapter_{i+1}"
                
                chapter_filename_base = "".join([c for c in chapter_name_raw if c.isalnum() or c in ' ']).rstrip().replace(' ', '_')
                final_chapter_path = output_dir / f"{i+1:02d}_{chapter_filename_base}.mp3"
                
                app.sentences = chapter_items
                self.assemble_audiobook(str(final_chapter_path), is_for_acx=True)
                exported_count += 1
             
             self.assembly_finished.emit(f"Exported {exported_count} chapters to {output_dir}")
             
        except Exception as e:
             self.assembly_error.emit(str(e))
        finally:
             app.sentences = original_sentences
