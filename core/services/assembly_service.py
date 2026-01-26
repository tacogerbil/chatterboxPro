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

    def assemble_audiobook(self, output_path_str: str, is_for_acx=False, metadata=None):
        if not output_path_str: 
            return
            
        self.assembly_started.emit()
        app = self.state # Alias for easier porting
        
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

                    # Chapter Heading Silence (Pre)
                    if s_data.get("is_chapter_heading"):
                        chapter_silence = temp_dir / f"chapter_pre_{s_data['uuid']}.wav"
                        AudioSegment.silent(duration=1500).export(chapter_silence, format="wav")
                        f.write(f"file '{chapter_silence.absolute()}'\n")

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
            
            path_to_process = raw_combined_path
            
            # Export Final
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
