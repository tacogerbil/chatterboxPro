import logging
import subprocess
from pathlib import Path
import shutil
import uuid
import ffmpeg
from pydub import AudioSegment
from PySide6.QtCore import QObject, Signal
import pygame

from chatterbox.models.s3gen import S3GEN_SR
from core.state import AppState

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

            self.current_sound = pygame.mixer.Sound(str(target_path))
            self.current_sound.play()
            self.playback_started.emit(uuid_str)
            
            # Note: Pygame doesn't easily emit 'finished' event without polling.
            # For this MVP we won't poll, just fire-and-forget play.
            
        except Exception as e:
            logging.error(f"Playback failed: {e}")

    def stop_playback(self):
        if self.current_sound:
            self.current_sound.stop()
            self.current_sound = None
        pygame.mixer.stop()
        self.playback_stopped.emit()

    def assemble_audiobook(self, output_path_str: str, is_for_acx=False, auto_mode=False):
        """Assembles the audiobook from chunks."""
        # Logic ported from legacy AudioManager
        # Assuming output_path_str is provided by UI (FileDialog)
        
        if not self.state.session_name:
            self.assembly_error.emit("No active session.")
            return

        session_path = Path("Outputs_Pro") / self.state.session_name
        # Use state sentences
        all_items_in_order = sorted(self.state.sentences, key=lambda s: int(s.get('sentence_number', 0)))
        
        if not all_items_in_order:
            self.assembly_error.emit("No text chunks found.")
            return

        output_path = Path(output_path_str)
        temp_dir = session_path / f"assembly_temp_{uuid.uuid4().hex}"
        temp_dir.resolve().mkdir(parents=True, exist_ok=True)
        
        try:
            self.assembly_progress.emit("Creating file list...")
            concat_list_path = temp_dir / "concat_list.txt"
            
            with open(concat_list_path, 'w', encoding='utf-8') as f:
                for s_data in all_items_in_order:
                    # Pauses
                    if s_data.get("is_pause"):
                        dur = s_data.get("duration", 1000)
                        pause_file = temp_dir / f"pause_{s_data['uuid']}.wav"
                        AudioSegment.silent(duration=dur).export(pause_file, format="wav")
                        f.write(f"file '{pause_file.absolute()}'\n")
                        continue
                        
                    # Silence between chunks
                    # Check if previous write existed (simplified: assume yes if not first)
                    # Logic: if file not empty?
                    
                    is_para = not self.state.settings.chunking_enabled and s_data.get('paragraph') == 'yes'
                    pause_dur = 750 if is_para else self.state.settings.silence_duration
                    silence_file = temp_dir / f"silence_{s_data['uuid']}.wav"
                    AudioSegment.silent(duration=pause_dur).export(silence_file, format="wav")
                    f.write(f"file '{silence_file.absolute()}'\n")
                    
                    # Chapter Pre-Silence
                    if s_data.get("is_chapter_heading"):
                         chap_silence = temp_dir / f"chap_pre_{s_data['uuid']}.wav"
                         AudioSegment.silent(duration=1500).export(chap_silence, format="wav")
                         f.write(f"file '{chap_silence.absolute()}'\n")

                    # Main Audio
                    audio_path = session_path / "Sentence_wavs" / f"audio_{s_data['uuid']}.wav"
                    if audio_path.exists():
                        f.write(f"file '{audio_path.absolute()}'\n")
                    
                    # Chapter Post-Silence
                    if s_data.get("is_chapter_heading"):
                         chap_silence_post = temp_dir / f"chap_post_{s_data['uuid']}.wav"
                         AudioSegment.silent(duration=1500).export(chap_silence_post, format="wav")
                         f.write(f"file '{chap_silence_post.absolute()}'\n")

            # Check files
            with open(concat_list_path, 'r') as f:
                 if not any(line.strip() for line in f):
                     self.assembly_error.emit("No valid audio files generated yet.")
                     return

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
            self.assembly_progress.emit("Concatenating audio...")
            raw_combined = temp_dir / "raw_combined.wav"
            (
                ffmpeg.input(str(concat_list_path), format='concat', safe=0, protocol_whitelist='file,pipe')
                .output(str(raw_combined), acodec='pcm_s16le', ar=S3GEN_SR)
                .overwrite_output()
                .run(quiet=False, capture_stderr=True)
            )
            
            path_to_process = raw_combined
            
            # Normalization
            if self.state.settings.norm_enabled:
                 self.assembly_progress.emit("Normalizing audio (EBU R128)...")
                 norm_path = temp_dir / "normalized.wav"
                 try:
                     peak = -3.0 if is_for_acx else -1.5
                     target_lufs = self.state.settings.norm_level
                     (
                         ffmpeg.input(str(path_to_process))
                         .output(str(norm_path), af=f"loudnorm=I={target_lufs}:TP={peak}:LRA=11", ar=S3GEN_SR)
                         .overwrite_output().run(quiet=False, capture_stderr=True)
                     )
                     path_to_process = norm_path
                 except Exception as e:
                     logging.error(f"Normalization failed: {e}")
            
            # Silence Removal
            if self.state.settings.silence_removal_enabled:
                # TODO: Check dependency path from somewhere? Using 'auto-editor' from path for now.
                self.assembly_progress.emit("Removing silence...")
                sr_path = temp_dir / "silence_removed.wav"
                try:
                    cmd = [
                        "auto-editor", str(path_to_process),
                        "--silent_threshold", str(self.state.settings.silence_threshold),
                        "--margin", "0.2s", # Simplified
                        "--no_open",
                        "-o", str(sr_path)
                    ]
                    subprocess.run(cmd, check=True, capture_output=True)
                    if sr_path.exists():
                        path_to_process = sr_path
                except Exception as e:
                    logging.error(f"Silence removal failed: {e}")

            # Export
            self.assembly_progress.emit("Exporting final file...")
            fmt = output_path.suffix.lstrip('.').lower()
            
            if fmt == 'mp3':
                (
                    ffmpeg.input(str(path_to_process))
                    .output(str(output_path), ar='44100', ac=1, audio_bitrate='192k')
                    .overwrite_output().run(quiet=False, capture_stderr=True)
                )
            else:
                shutil.copy(path_to_process, output_path)
                
            self.assembly_finished.emit(str(output_path))
            
        except Exception as e:
            logging.error(f"Assembly failed: {e}", exc_info=True)
            self.assembly_error.emit(str(e))
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def export_chapters(self, output_dir_str: str):
        """Exports audio split by chapters."""
        if not self.state.session_name:
            self.assembly_error.emit("No active session.")
            return
            
        output_dir = Path(output_dir_str)
        # Use simple list comprehension
        all_items = sorted(self.state.sentences, key=lambda s: int(s.get('sentence_number', 0)))
        
        if not all_items:
            self.assembly_error.emit("No text chunks found.")
            return
            
        # Group by chapters
        chapters = []
        current_chap = []
        
        # Check if first item is chapter
        if not any(i.get("is_chapter_heading") for i in all_items):
            chapters.append(all_items)
        else:
            for item in all_items:
                if item.get("is_chapter_heading") and current_chap:
                    chapters.append(current_chap)
                    current_chap = [item]
                else:
                    current_chap.append(item)
            if current_chap: chapters.append(current_chap)
            
        if not chapters:
            self.assembly_error.emit("Could not group chapters.")
            return

        self.assembly_progress.emit(f"Found {len(chapters)} chapters. Starting export...")
        
        # We cheat a bit: We use assemble_audiobook by temporarily mutating state.sentences
        # ideally we should refactor assemble_audiobook to take a list of items.
        # But for MVP parity and safety (since assemble uses state.sentences), we will patch state.
        
        original_sentences = self.state.sentences
        
        try:
            for i, chap_items in enumerate(chapters):
                # Determine Name
                head = next((x for x in chap_items if x.get('is_chapter_heading')), None)
                raw_name = head.get('original_sentence', f"Chapter_{i+1}").strip() if head else f"Chapter_{i+1}"
                safe_name = "".join([c for c in raw_name if c.isalnum() or c in ' ']).rstrip().replace(' ', '_')
                
                out_path = output_dir / f"{i+1:02d}_{safe_name}.mp3"
                
                self.assembly_progress.emit(f"Exporting Chapter {i+1}: {safe_name}")
                
                # Patch state
                self.state.sentences = chap_items
                
                # Assemble (Blocking)
                # We need to suppress 'assembly_finished' signal for intermediate steps? 
                # Or just let it emit.
                # assemble_audiobook calls emit('assembly_finished'). view might pop up msgbox multiple times.
                # This is a UX flow flaw in legacy too maybe?
                # We'll run it.
                self.assemble_audiobook(str(out_path), is_for_acx=True)
                
        finally:
            self.state.sentences = original_sentences
            self.assembly_finished.emit(f"All chapters exported to {output_dir}")
