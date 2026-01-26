# core/audio_manager.py
import logging
import subprocess
from pathlib import Path
import shutil
import os
from tkinter import filedialog, messagebox
import uuid

import ffmpeg
from pydub import AudioSegment

from chatterbox.models.s3gen import S3GEN_SR

class AudioManager:
    """Handles final audiobook assembly and post-processing."""
    def __init__(self, app_instance):
        self.app = app_instance

    def assemble_audiobook(self, auto_path=None, is_for_acx=False):
        app = self.app
        if not app.session_name.get():
            messagebox.showerror("Error", "No active session. Please create or load a session first.")
            return

        session_path = Path(app.OUTPUTS_DIR) / app.session_name.get()
        all_items_in_order = sorted(app.sentences, key=lambda s: int(s['sentence_number']))
        
        if not all_items_in_order:
            if not auto_path: messagebox.showerror("Error", "No text chunks to assemble.")
            return

        output_path_str = auto_path or filedialog.asksaveasfilename(
            defaultextension=".mp3", 
            filetypes=[("MP3", "*.mp3"), ("WAV", "*.wav")], 
            initialdir=session_path, 
            initialfile=f"{app.session_name.get()}_audiobook.mp3"
        )
        if not output_path_str:
            return

        output_path = Path(output_path_str)
        temp_dir = session_path / f"assembly_temp_{uuid.uuid4().hex}"
        # FIX: Force absolute path and create parent folders if missing
        temp_dir = temp_dir.resolve()
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            logging.info(f"Step 1: Creating file list for FFmpeg concat...")
            
            # Create concat file list for FFmpeg
            concat_list_path = temp_dir / "concat_list.txt"
            with open(concat_list_path, 'w', encoding='utf-8') as f:
                for s_data in all_items_in_order:
                    # Handle pauses
                    if s_data.get("is_pause"):
                        # Generate silent audio file for pause
                        pause_duration_ms = s_data.get("duration", 1000)
                        pause_file = temp_dir / f"pause_{s_data['uuid']}.wav"
                        AudioSegment.silent(duration=pause_duration_ms).export(pause_file, format="wav")
                        f.write(f"file '{pause_file.absolute()}'\n")
                        continue

                    # Add silence between chunks
                    if len([line for line in open(concat_list_path).readlines() if line.strip()]) > 0:
                        is_para = not app.chunking_enabled.get() and s_data.get('paragraph') == 'yes'
                        pause_duration = 750 if is_para else app.get_validated_int(app.silence_duration_str, 250)
                        silence_file = temp_dir / f"silence_{s_data['uuid']}.wav"
                        AudioSegment.silent(duration=pause_duration).export(silence_file, format="wav")
                        f.write(f"file '{silence_file.absolute()}'\n")

                    # Add chapter heading silence
                    if s_data.get("is_chapter_heading"):
                        chapter_silence = temp_dir / f"chapter_pre_{s_data['uuid']}.wav"
                        AudioSegment.silent(duration=1500).export(chapter_silence, format="wav")
                        f.write(f"file '{chapter_silence.absolute()}'\n")

                    # Add main audio file
                    f_path = session_path / "Sentence_wavs" / f"audio_{s_data['uuid']}.wav"
                    if f_path.exists():
                        f.write(f"file '{f_path.absolute()}'\n")
                    else:
                        logging.warning(f"Audio for sentence #{s_data['sentence_number']} not found, skipping.")

                    # Add chapter heading silence (post)
                    if s_data.get("is_chapter_heading"):
                        chapter_silence_post = temp_dir / f"chapter_post_{s_data['uuid']}.wav"
                        AudioSegment.silent(duration=1500).export(chapter_silence_post, format="wav")
                        f.write(f"file '{chapter_silence_post.absolute()}'\n")

            # Check if we have any files to concatenate
            with open(concat_list_path, 'r') as f:
                file_count = len([line for line in f if line.strip()])
            
            if file_count == 0:
                if not auto_path: messagebox.showerror("Error", "No valid audio files were found to assemble.")
                return

            # Add ACX silence if needed
            if is_for_acx:
                head_silence_file = temp_dir / "acx_head.wav"
                tail_silence_file = temp_dir / "acx_tail.wav"
                AudioSegment.silent(duration=1000).export(head_silence_file, format="wav")
                AudioSegment.silent(duration=2000).export(tail_silence_file, format="wav")
                
                # Prepend and append to concat list
                with open(concat_list_path, 'r') as f:
                    original_content = f.read()
                with open(concat_list_path, 'w') as f:
                    f.write(f"file '{head_silence_file.absolute()}'\n")
                    f.write(original_content)
                    f.write(f"file '{tail_silence_file.absolute()}'\n")

            # Use FFmpeg concat demuxer (memory-efficient streaming)
            raw_combined_path = temp_dir / "raw_combined_audio.wav"
            logging.info(f"Concatenating {file_count} audio segments using FFmpeg...")
            
            (
                ffmpeg.input(str(concat_list_path), format='concat', safe=0, protocol_whitelist='file,pipe')
                .output(str(raw_combined_path), acodec='pcm_s16le', ar=S3GEN_SR)
                .overwrite_output()
                .run(quiet=False, capture_stderr=True)
            )

            path_to_process = raw_combined_path
            
            if app.norm_enabled.get() and app.deps.ffmpeg_ok:
                logging.info("Step 2: Applying EBU R128 normalization...")
                normalized_path = temp_dir / "normalized_audio.wav"
                try:
                    peak_level = -3.0 if is_for_acx else -1.5
                    (
                        ffmpeg.input(str(path_to_process))
                              .output(str(normalized_path), af=f"loudnorm=I={float(app.norm_level_str.get())}:TP={peak_level}:LRA=11", ar=S3GEN_SR)
                              .overwrite_output().run(quiet=False, capture_stderr=True)
                    )
                    path_to_process = normalized_path
                    logging.info("Normalization successful.")
                except Exception as e:
                    logging.error(f"Normalization failed: {e}", exc_info=True)

            if app.silence_removal_enabled.get() and app.deps.auto_editor_path:
                logging.info("Step 3: Applying silence removal...")
                silence_removed_path = temp_dir / "silence_removed_audio.wav"
                try:
                    silent_speed = app.get_validated_int(app.silent_speed_str, 9999)
                    frame_margin = app.get_validated_int(app.frame_margin_str, 6)
                    silent_threshold = app.get_validated_float(app.silence_threshold, 0.04)
                    
                    cmd = [
                        app.deps.auto_editor_path, 
                        str(path_to_process),
                        '--silent-threshold', str(silent_threshold),
                        '--silent_speed', str(silent_speed), 
                        '--frame_margin', str(frame_margin),
                        '--no_open',
                        '-o', str(silence_removed_path)
                    ]
                    
                    # FIX: Run without check=True and verify the result to prevent crashes.
                    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')

                    if result.returncode == 0 and silence_removed_path.exists():
                        path_to_process = silence_removed_path
                        logging.info("Silence removal successful.")
                    else:
                        logging.warning(f"Silence removal did not complete successfully (exit code {result.returncode}). Continuing without it.")
                        logging.debug(f"auto-editor stderr: {result.stderr}")

                except Exception as e:
                    logging.error(f"An unexpected error occurred during silence removal: {e}", exc_info=True)

            logging.info(f"Step 4: Exporting final audiobook to {output_path}...")
            
            artist = app.metadata_artist_str.get()
            album = app.metadata_album_str.get() or app.session_name.get()
            title = app.metadata_title_str.get() or app.session_name.get()
            
            file_format = output_path.suffix.lstrip('.').lower()
            
            if file_format == 'mp3':
                output_options = {
                    'ar': '44100',
                    'ac': 1,
                    'b:a': '192k',
                    'metadata': [
                        f'title={title}',
                        f'artist={artist}',
                        f'album={album}'
                    ]
                }
                try:
                    (
                        ffmpeg.input(str(path_to_process))
                        .output(str(output_path), **output_options)
                        .overwrite_output().run(quiet=False, capture_stderr=True)
                    )
                except ffmpeg.Error as e:
                    # --- DEBUG FIX: PRINT THE REAL ERROR ---
                    print("\n" + "="*40)
                    print("!!! FFMPEG ERROR CAPTURED !!!")
                    print("="*40)
                    if e.stderr:
                        print(e.stderr.decode('utf8'))
                    else:
                        print("No stderr returned. Check file permissions or disk space.")
                    print("="*40 + "\n")
                    # ---------------------------------------
                    raise e
                except Exception as e:
                    logging.error(f"Final MP3 export failed: {e}", exc_info=True)
                    raise
            else:
                final_segment = AudioSegment.from_wav(path_to_process)
                final_segment.export(output_path, format=file_format)
            
            if not auto_path:
                messagebox.showinfo("Success", f"Audiobook assembled and saved to {output_path}")

        except Exception as e:
            logging.error(f"Failed to assemble audiobook: {e}", exc_info=True)
            if not auto_path:
                messagebox.showerror("Assembly Error", f"An error occurred: {e}")
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
                logging.info("Cleaned up temporary assembly directory.")

    def export_by_chapter(self):
        app = self.app
        if not app.session_name.get():
            messagebox.showerror("Error", "No active session. Please create or load a session first.")
            return
        
        output_dir_str = filedialog.askdirectory(
            title="Select Output Directory for Audible Chapters",
            initialdir=str(Path(app.OUTPUTS_DIR) / app.session_name.get())
        )
        if not output_dir_str:
            return

        output_dir = Path(output_dir_str)
        all_items_in_order = sorted([s for s in app.sentences], key=lambda s: int(s['sentence_number']))

        if not all_items_in_order:
            messagebox.showerror("Error", "No text chunks found to export.")
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

        if not chapters:
            messagebox.showerror("Error", "Could not group any items into chapters.")
            return
        
        logging.info(f"Found {len(chapters)} chapters. Starting export to {output_dir}...")
        exported_count = 0

        for i, chapter_items in enumerate(chapters):
            chapter_heading_item = next((item for item in chapter_items if item.get('is_chapter_heading')), None)
            chapter_name_raw = chapter_heading_item.get('original_sentence', f'Chapter_{i+1}').strip() if chapter_heading_item else f"{app.session_name.get()}_Chapter_{i+1}"
            
            chapter_filename_base = "".join([c for c in chapter_name_raw if c.isalnum() or c in ' ']).rstrip().replace(' ', '_')
            final_chapter_path = output_dir / f"{i+1:02d}_{chapter_filename_base}.mp3"
            
            logging.info(f"Assembling Chapter {i+1}: {chapter_filename_base}")
            
            original_sentences = app.sentences
            app.sentences = chapter_items
            
            self.assemble_audiobook(auto_path=str(final_chapter_path), is_for_acx=True)
            
            app.sentences = original_sentences
            exported_count += 1

        messagebox.showinfo("Export Complete", f"Successfully exported {exported_count} of {len(chapters)} chapter(s) to:\n{output_dir}")
