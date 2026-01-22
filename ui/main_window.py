# ui/main_window.py
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import pygame
import os
import gc
import json
import logging
import re
from pathlib import Path
import shutil
import threading
import torch
import time
import uuid 

from ui.playlist import PlaylistFrame
from ui.controls_frame import ControlsFrame
from ui.tabs.setup_tab import SetupTab
from ui.tabs.generation_tab import GenerationTab
from ui.tabs.finalize_tab import FinalizeTab
from ui.tabs.advanced_tab import AdvancedTab
from ui.tabs.chapters_tab import ChaptersTab

from core.orchestrator import GenerationOrchestrator
from core.audio_manager import AudioManager
from utils.text_processor import TextPreprocessor

try: from bs4 import BeautifulSoup
except ImportError: BeautifulSoup = None
try: from pdftextract import XPdf
except ImportError: XPdf = None
try: import ebooklib; from ebooklib import epub
except ImportError: ebooklib, epub = None, None
try: import pypandoc
except ImportError: pypandoc = None

class ChatterboxProGUI(ctk.CTk):
    """The main application window class."""
    def __init__(self, dependency_manager):
        super().__init__()
        self.deps = dependency_manager
        self.title("Chatterbox Pro Audiobook Generator")
        self.geometry("1600x900")

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.text_color = "#101010"
        self.colors = {
            "frame_bg": "#F9F9F9", "tab_bg": "#EAEAEA", "selection": "#3A7EBF",
            "marked": "#FFDCDC", "failed": "#A40000", "chapter": "#D5F5E3"
        }
        self.button_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
        self.button_hover_color = ctk.ThemeManager.theme["CTkButton"]["hover_color"]

        pygame.mixer.init()

        try:
            self.iconbitmap("assets/icon.ico")
        except tk.TclError:
            logging.warning("assets/icon.ico not found.")

        self.orchestrator = GenerationOrchestrator(self)
        self.audio_manager = AudioManager(self)
        self.text_processor = TextPreprocessor()
        self.OUTPUTS_DIR = "Outputs_Pro"
        self.TEMPLATES_DIR = "Templates"
        os.makedirs(self.TEMPLATES_DIR, exist_ok=True)
        
        self.session_name, self.source_file_path, self.sentences = ctk.StringVar(), "", []
        self.generation_thread, self.stop_flag = None, threading.Event()
        self.assembly_thread = None # Thread for background assembly
        self.is_playlist_playing, self.current_playing_sound, self.playlist_index = False, None, 0

        # --- State Variables ---
        self.ref_audio_path = ctk.StringVar()
        self.ref_audio_path_display = ctk.StringVar(value="No file selected.") # For display
        self.exaggeration = ctk.DoubleVar(value=0.5)
        self.cfg_weight = ctk.DoubleVar(value=0.7)
        self.temperature = ctk.DoubleVar(value=0.8)
        self.speed = ctk.DoubleVar(value=1.0)
        self.items_per_page_str = ctk.StringVar(value="15")
        self.target_gpus_str = ctk.StringVar(value=",".join([f"cuda:{i}" for i in range(torch.cuda.device_count())]) if torch.cuda.is_available() else "cpu")
        self.num_full_outputs_str = ctk.StringVar(value="1")
        self.master_seed_str = ctk.StringVar(value="0")
        self.num_candidates_str = ctk.StringVar(value="1")
        self.max_attempts_str = ctk.StringVar(value="3")
        self.asr_validation_enabled = ctk.BooleanVar(value=True)
        self.asr_threshold_str = ctk.StringVar(value="0.85")
        self.disable_watermark = ctk.BooleanVar(value=True)
        self.generation_order = ctk.StringVar(value="Fastest First")
        self.chunking_enabled = ctk.BooleanVar(value=True)
        self.max_chunk_chars_str = ctk.StringVar(value="290")
        self.silence_duration_str = ctk.StringVar(value="250")
        self.norm_enabled = ctk.BooleanVar(value=False)
        self.silence_removal_enabled = ctk.BooleanVar(value=False)
        self.norm_level_str = ctk.StringVar(value="-23.0")
        self.silence_threshold = ctk.StringVar(value="0.04")
        self.silent_speed_str = ctk.StringVar(value="9999")
        self.frame_margin_str = ctk.StringVar(value="6")
        self.metadata_artist_str = ctk.StringVar(value="Chatterbox Pro")
        self.metadata_album_str = ctk.StringVar(value="")
        self.metadata_title_str = ctk.StringVar(value="")
        self.llm_api_url = ctk.StringVar(value="http://127.0.0.1:5000/v1/chat/completions")
        self.llm_enabled = ctk.BooleanVar(value=False)
        self.selected_template_str = ctk.StringVar()
        self.reassemble_after_regen = ctk.BooleanVar(value=False)
        self.aggro_clean_on_parse = ctk.BooleanVar(value=False)
        self.apply_fix_to_all_failed = ctk.BooleanVar(value=False)
        self.auto_assemble_after_run = ctk.BooleanVar(value=True)
        
        # Auto-Regeneration Control Variables
        self.auto_regen_main = ctk.BooleanVar(value=False)
        self.auto_regen_sub = ctk.BooleanVar(value=False)
        self.auto_fix_stage = "NONE"  # NONE, MAIN_INITIAL, MAIN_RETRY_1, MAIN_SPLIT, MAIN_LOOP, SUB_LOOP
        
        # Dual-GPU detection and control
        self.gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
        self.use_dual_gpu = ctk.BooleanVar(value=False)  # Default to single GPU

        self.setup_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.after(100, self.show_dependency_warnings)
        self.populate_template_dropdown()

    def show_dependency_warnings(self):
        warnings = []
        if not self.deps.pandoc_ok: warnings.append("- Pandoc not found. DOCX and MOBI file support is disabled.")
        if not self.deps.ffmpeg_ok: warnings.append("- FFmpeg not found. Audio normalization will be disabled.")
        if not self.deps.auto_editor_ok: warnings.append("- auto-editor not found. Silence removal will be disabled.")
        if warnings: messagebox.showwarning("Dependency Warning", "Some features are disabled due to missing dependencies:\n\n" + "\n".join(warnings))

    def get_validated_int(self, var, default_val):
        try: return int(var.get())
        except (ValueError, tk.TclError): return default_val

    def get_validated_float(self, var, default_val):
        try: return float(var.get())
        except (ValueError, tk.TclError): return default_val

    def _delete_audio_file_for_item(self, item_data):
        uuid_to_delete = item_data.get('uuid')
        if not self.session_name.get() or not uuid_to_delete:
            return
            
        f_path = Path(self.OUTPUTS_DIR) / self.session_name.get() / "Sentence_wavs" / f"audio_{uuid_to_delete}.wav"
        if f_path.exists():
            try:
                os.remove(f_path)
                logging.info(f"Deleted orphaned audio file: {f_path.name}")
            except OSError as e:
                logging.error(f"Failed to delete audio file {f_path}: {e}")

    def on_closing(self):
        if not messagebox.askokcancel("Quit", "Do you want to quit? This will stop any ongoing processes."):
            return

        # Platform-specific window disable (Windows only)
        if sys.platform == "win32":
            try:
                self.attributes("-disabled", True)
            except Exception:
                pass  # Fallback if attribute not supported
        
        self.start_stop_button.configure(text="Shutting down...", state="disabled")
        
        logging.info("Shutdown signal received. Waiting for background processes to finish.")
        self.stop_flag.set()
        self.stop_playback()
        self.save_session()
        
        self.after(100, self._check_shutdown)

    def _check_shutdown(self):
        """Periodically checks if background threads have completed."""
        gen_alive = self.generation_thread and self.generation_thread.is_alive()
        asm_alive = self.assembly_thread and self.assembly_thread.is_alive()

        if gen_alive or asm_alive:
            self.after(200, self._check_shutdown)
        else:
            logging.info("Background processes finished. Exiting application.")
            self.destroy()

    def reinit_audio_player(self):
        """Shuts down and restarts the pygame mixer to resolve hardware conflicts after multiprocessing."""
        logging.info("Re-initializing audio playback system...")
        try:
            pygame.mixer.quit()
            pygame.mixer.init()
            logging.info("Audio playback system re-initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to re-initialize pygame mixer: {e}", exc_info=True)
            messagebox.showerror("Audio Error", "Could not re-initialize the audio player. You may need to restart the application to restore playback.")

    def toggle_generation_main(self):
        if self.generation_thread and self.generation_thread.is_alive():
            self.stop_generation()
        else:
            # Initialize Auto-Fix State
            if self.auto_regen_main.get():
                self.auto_fix_stage = "MAIN_INITIAL"
            else:
                self.auto_fix_stage = "NONE"
            self.start_generation_orchestrator()
            
    # --- Background Task Management ---
    def start_assembly_in_background(self):
        if self.assembly_thread and self.assembly_thread.is_alive():
            messagebox.showwarning("Busy", "An assembly process is already running.")
            return

        for button in self.finalize_tab.assembly_buttons:
            button.configure(state="disabled", text="Assembling...")
        
        self.assembly_thread = threading.Thread(target=self.audio_manager.assemble_audiobook, daemon=True)
        self.assembly_thread.start()
        self.after(100, self._check_background_thread, self.assembly_thread, self.finalize_tab.assembly_buttons, ["Assemble as Single File", "Export by Chapter..."])

    def start_chapter_export_in_background(self):
        if self.assembly_thread and self.assembly_thread.is_alive():
            messagebox.showwarning("Busy", "An assembly process is already running.")
            return

        for button in self.finalize_tab.assembly_buttons:
            button.configure(state="disabled")
        self.finalize_tab.export_button.configure(text="Exporting...")

        self.assembly_thread = threading.Thread(target=self.audio_manager.export_by_chapter, daemon=True)
        self.assembly_thread.start()
        self.after(100, self._check_background_thread, self.assembly_thread, self.finalize_tab.assembly_buttons, ["Assemble as Single File", "Export by Chapter..."])

    def _check_background_thread(self, thread, buttons, original_texts):
        if thread.is_alive():
            self.after(100, self._check_background_thread, thread, buttons, original_texts)
        else:
            for i, button in enumerate(buttons):
                button.configure(state="normal", text=original_texts[i])

    def start_generation_orchestrator(self, indices_to_process=None):
        if not self.sentences: return messagebox.showerror("Error", "No sentences to generate.")
        if not self.ref_audio_path.get() or not os.path.exists(self.ref_audio_path.get()): return messagebox.showerror("Error", "Please provide a valid reference audio file.")
        self.stop_flag.clear()
        self.start_stop_button.configure(text="Stop Generation", fg_color="#D22B2B", hover_color="#B02525")
        self.generation_thread = threading.Thread(target=self.orchestrator.run, args=(indices_to_process,), daemon=True)
        self.generation_thread.start()
        self.after(1000, self._monitor_generation_completion)

    def _monitor_generation_completion(self):
        """Monitors the generation thread and triggers auto-fix logic upon completion."""
        if self.generation_thread and self.generation_thread.is_alive():
            self.after(500, self._monitor_generation_completion)
        else:
            # Generation finished
            if self.stop_flag.is_set():
                self.auto_fix_stage = "NONE" # User stopped manually
            else:
                self.after(100, self._auto_fix_logic)

    def _auto_fix_logic(self):
        """State machine for auto-regeneration loops."""
        failed_indices = [i for i, s in enumerate(self.sentences) if s.get('tts_generated') == 'failed']
        
        if not failed_indices:
            self.auto_fix_stage = "NONE"
            logging.info("Auto-Fix: All clear. Generation complete.")
            # Trigger assembly if enabled
            if self.auto_assemble_after_run.get():
                self.start_assembly_in_background()
            else:
                self.start_stop_button.configure(text="Start Generation", fg_color=None, hover_color=None, state="normal")
            return

        # We have failures. Check Stage.
        if self.auto_fix_stage == "MAIN_INITIAL":
            logging.info(f"Auto-Fix: Initial run has {len(failed_indices)} failures. Triggering Retry 1 (Regenerate Marked)...")
            self.auto_fix_stage = "MAIN_RETRY_1"
            # We must manually clear any previous 'marked' status and mark only failed ones?
            # regenerate_marked_sentences picks up all 'marked'.
            # Failures are marked automatically by the orchestrator usually?
            # Actually, let's ensure failed ones are marked.
            for idx in failed_indices: self.sentences[idx]['marked'] = True
            
            self.start_generation_orchestrator(failed_indices)

        elif self.auto_fix_stage == "MAIN_RETRY_1":
            logging.info(f"Auto-Fix: Retry 1 has {len(failed_indices)} failures. Splitting all failed chunks...")
            self.auto_fix_stage = "MAIN_SPLIT"
            self.split_all_failed_chunks(confirm=False) # Helper modification needed to skip confirm dialog?
            # After splitting, we need to regenerate the new pieces.
            # Splitting updates self.sentences. We need to find the new failed/marked chunks.
            new_failed = [i for i, s in enumerate(self.sentences) if s.get('marked')]
            self.start_generation_orchestrator(new_failed)

        elif self.auto_fix_stage == "MAIN_SPLIT":
            logging.info(f"Auto-Fix: Post-Split run finished. {len(failed_indices)} failures remain. Entering Infinite Loop...")
            self.auto_fix_stage = "MAIN_LOOP"
            self.start_generation_orchestrator(failed_indices)

        elif self.auto_fix_stage == "MAIN_LOOP":
            logging.info(f"Auto-Fix (Loop): {len(failed_indices)} failures remain. Retrying...")
            self.start_generation_orchestrator(failed_indices)

        elif self.auto_fix_stage == "SUB_LOOP":
             logging.info(f"Auto-Fix (Sub-Loop): {len(failed_indices)} failures remain. Retrying...")
             self.start_generation_orchestrator(failed_indices)
        
        else:
             # No auto-fix active, just update button
             self.start_stop_button.configure(text="Start Generation", fg_color=None, hover_color=None, state="normal")
             messagebox.showinfo("Done", f"Generation complete. {len(failed_indices)} failed chunks.")

    def stop_generation(self):
        if self.generation_thread and self.generation_thread.is_alive():
            self.stop_flag.set()
            self.start_stop_button.configure(text="Stopping...", state="disabled")
            logging.info("Stop signal sent.")

    def new_session(self):
        name = ctk.CTkInputDialog(text="Enter session name:", title="New Session").get_input()
        if name and re.match("^[a-zA-Z0-9_-]*$", name):
            session_path = Path(self.OUTPUTS_DIR) / name
            if session_path.exists():
                if not messagebox.askyesno("Overwrite?", f"Session '{name}' exists. Delete and create anew?"): return
                shutil.rmtree(session_path)
            session_path.mkdir(parents=True)
            self.session_name.set(name)
            self.source_file_path, self.sentences = "", []
            self.source_file_label.configure(text="No file selected.")
            self.playlist_frame.load_data(self.sentences)
            self.update_progress_display(0,0,0)
            self.save_session()
        elif name:
            messagebox.showerror("Invalid Name", "Use only letters, numbers, underscores, hyphens.")

    def load_session(self):
        path_str = filedialog.askdirectory(initialdir=self.OUTPUTS_DIR, title="Select Session Folder")
        if path_str:
            session_path = Path(path_str)
            json_path = session_path / f"{session_path.name}_session.json"
            if not json_path.exists(): return messagebox.showerror("Error", "Session file not found.")
            with open(json_path, 'r', encoding='utf-8') as f: data = json.load(f)
            
            self.session_name.set(session_path.name)
            self.source_file_path = data.get("source_file_path", "")
            self.source_file_label.configure(text=os.path.basename(self.source_file_path) or "No file selected.")
            self.sentences = data.get("sentences", [])
            
            if any('uuid' not in s for s in self.sentences):
                for s in self.sentences: s.setdefault('uuid', uuid.uuid4().hex)
                self.save_session()
            
            if "generation_settings" in data:
                self._apply_generation_settings(data["generation_settings"])

            self.ref_audio_path_display.set(os.path.basename(self.ref_audio_path.get()) or "No file selected.")
            self.playlist_frame.load_data(self.sentences)
            gen_count = sum(1 for s in self.sentences if s.get("tts_generated") == "yes")
            total = len([s for s in self.sentences if not s.get('is_pause')])
            self.update_progress_display(gen_count/total if total > 0 else 0, gen_count, total)
            logging.info(f"Loaded session: {session_path.name}")

    def save_session(self):
        if not self.session_name.get(): return
        session_path = Path(self.OUTPUTS_DIR) / self.session_name.get()
        #session_path.mkdir(exist_ok=True)
        # FIX: Force absolute path and create parents
        session_path = session_path.resolve()
        session_path.mkdir(parents=True, exist_ok=True)
        session_data = {
            "source_file_path": self.source_file_path,
            "sentences": self.sentences,
            "generation_settings": self._get_generation_settings()
        }
        with open(session_path / f"{self.session_name.get()}_session.json", 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=4)
        logging.info(f"Session '{self.session_name.get()}' saved.")

    def select_source_file(self):
        file_types = [("All Supported", "*.txt *.pdf *.epub")]
        if self.deps.pandoc_ok:
            file_types[0] = ("All Supported", "*.txt *.pdf *.epub *.docx *.mobi")
            file_types.extend([("Word", "*.docx"), ("MOBI", "*.mobi")])
        path = filedialog.askopenfilename(filetypes=file_types)
        if path:
            self.source_file_path = path
            self.source_file_label.configure(text=os.path.basename(path))

    def process_file_content(self):
        if not self.source_file_path or not self.session_name.get():
            messagebox.showerror("Error", "Please create/load a session and select a source file first.")
            return
        
        if self.sentences and not messagebox.askyesno("Confirm Deletion", "This will discard your current playlist and all its generated audio files. Are you sure you want to re-process the source file?"):
            return
        
        for item in self.sentences:
            self._delete_audio_file_for_item(item)

        self.process_button.configure(state="disabled", text="Processing...")
        threading.Thread(target=self._process_file_content_threaded, daemon=True).start()

    def _process_file_content_threaded(self):
        try:
            ext = Path(self.source_file_path).suffix.lower()
            text = ""
            if ext == '.txt':
                with open(self.source_file_path, 'r', encoding='utf-8', errors='ignore') as f: text = f.read()
            elif ext == '.pdf' and XPdf:
                text = XPdf(self.source_file_path).to_text()
            elif ext == '.epub' and ebooklib and BeautifulSoup:
                book = epub.read_epub(self.source_file_path)
                html_content = "".join([item.get_body_content().decode('utf-8', 'ignore') for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)])
                soup = BeautifulSoup(html_content, 'html.parser')
                text = soup.get_text("\n\n", strip=True)
            elif ext in ['.docx', '.mobi'] and self.deps.pandoc_ok and pypandoc:
                text = pypandoc.convert_file(self.source_file_path, 'plain', encoding='utf-8')

            if not text:
                self.after(0, lambda: messagebox.showerror("Error", f"Could not extract text from file '{ext}'. Check if it's empty."))
                return
            self.after(0, self.show_editor_window, text, self.aggro_clean_on_parse.get())
        except Exception as e:
            logging.error(f"Error processing file: {e}", exc_info=True)
            self.after(0, lambda: messagebox.showerror("Error", f"Failed to process file: {e}"))
        finally:
            self.after(0, lambda: self.process_button.configure(state="normal", text="Process Text File"))

    def show_editor_window(self, text, aggressive_clean):
        editor = ctk.CTkToplevel(self)
        editor.title("Review and Edit Text")
        editor.geometry("800x600")
        
        # FIX: Wait for window to be visible before grabbing focus
        editor.wait_visibility() 
        editor.grab_set()
        textbox = ctk.CTkTextbox(editor, wrap="word"); textbox.pack(fill="both", expand=True, padx=10, pady=10); textbox.insert("1.0", text)
        def on_confirm():
            logging.info("Editor confirmed. Processing text...")
            processed_sentences = self.text_processor.preprocess_text(
                textbox.get("1.0", "end-1c"), 
                is_edited_text=True,
                aggressive_clean=aggressive_clean
            )
            
            if self.chunking_enabled.get():
                self.sentences = self.text_processor.group_sentences_into_chunks(processed_sentences, self.get_validated_int(self.max_chunk_chars_str, 290))
            else:
                self.sentences = processed_sentences
            
            for item in self.sentences:
                item.setdefault('uuid', uuid.uuid4().hex)

            self._renumber_sentences()
            self.playlist_frame.load_data(self.sentences)
            self.save_session()
            editor.destroy()
            
        ctk.CTkButton(editor, text="Confirm and Process Sentences", command=on_confirm).pack(pady=10)

    def update_progress_display(self, progress, completed, total):
        self.progress_bar.set(progress)
        self.progress_label.configure(text=f"{completed}/{total} ({progress:.2%})")

    def play_selected_sentence(self, index=None):
        indices = [index] if index is not None else self.playlist_frame.get_selected_indices()
        if not indices: return
        self.stop_playback()
        self._play_audio_at_index(indices[0])

    def stop_playback(self):
        pygame.mixer.stop()
        self.is_playlist_playing = False
        if self.current_playing_sound:
            self.current_playing_sound = None; gc.collect()

    def mark_current_sentence(self, event=None):
        for idx in self.playlist_frame.get_selected_indices():
            if 0 <= idx < len(self.sentences):
                self.sentences[idx]['marked'] = not self.sentences[idx].get('marked', False)
                self.playlist_frame.update_item(idx)
        self.save_session()

    def mark_as_passed(self):
        indices = self.playlist_frame.get_selected_indices()
        if not indices: return
        for idx in indices:
            if 0 <= idx < len(self.sentences):
                item = self.sentences[idx]
                if item.get('tts_generated') == 'failed':
                    item['tts_generated'] = 'yes'
                    item['marked'] = False
                    self.playlist_frame.update_item(idx)
        self.save_session()
    
    def play_from_selection(self):
        if not self.sentences: return
        self.stop_playback()
        selected_indices = self.playlist_frame.get_selected_indices()
        start_index = selected_indices[0] if selected_indices else 0
        self.playlist_index = start_index
        self.is_playlist_playing = True
        self._check_and_play_next()

    def _check_and_play_next(self):
        if not self.is_playlist_playing or self.stop_flag.is_set(): return self.stop_playback()
        if not pygame.mixer.get_busy():
            if self.playlist_index < len(self.sentences):
                items_per_page = self.playlist_frame.items_per_page
                if self.playlist_index // items_per_page != self.playlist_frame.current_page:
                    self.playlist_frame.display_page(self.playlist_index // items_per_page)
                self.playlist_frame.selected_indices = {self.playlist_index}
                self.playlist_frame._update_all_visuals()
                duration_s = self._play_audio_at_index(self.playlist_index)
                self.playlist_index += 1
                self.after(int(duration_s * 1000) if duration_s > 0 else 100, self._check_and_play_next)
            else: self.stop_playback()
        else: self.after(100, self._check_and_play_next)

    def _play_audio_at_index(self, index):
        if index >= len(self.sentences): return 0
        item = self.sentences[index]
        if item.get("is_pause"): return item.get("duration", 1000) / 1000.0
        wav_path = Path(self.OUTPUTS_DIR) / self.session_name.get() / "Sentence_wavs" / f"audio_{item['uuid']}.wav"
        if wav_path.exists():
            try:
                if self.current_playing_sound: self.current_playing_sound.stop()
                self.current_playing_sound = pygame.mixer.Sound(str(wav_path))
                self.current_playing_sound.play()
                return self.current_playing_sound.get_length()
            except Exception as e:
                logging.error(f"Error playing sound: {e}")
        return 0

    def edit_selected_sentence(self):
        indices = self.playlist_frame.get_selected_indices()
        if len(indices) != 1:
            return messagebox.showinfo("Info", "Please select exactly one item to edit.")
        idx = indices[0]
        
        if self.sentences[idx].get("is_pause"):
            return messagebox.showinfo("Info", "Cannot edit a pause marker.")
            
        original_text = self.sentences[idx].get('original_sentence', '')
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("Edit Text")
        dialog.geometry("600x250")
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(0, weight=1)
        
        textbox = ctk.CTkTextbox(dialog, wrap="word", height=150)
        textbox.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        textbox.insert("1.0", original_text)
        
        result = {"text": None}
        def on_ok():
            result["text"] = textbox.get("1.0", "end-1c")
            dialog.destroy()
            
        def on_cancel():
            dialog.destroy()
            
        ok_button = ctk.CTkButton(dialog, text="OK", command=on_ok)
        ok_button.grid(row=1, column=0, padx=10, pady=10, sticky="e")
        cancel_button = ctk.CTkButton(dialog, text="Cancel", command=on_cancel, fg_color="gray")
        cancel_button.grid(row=1, column=1, padx=10, pady=10, sticky="w")
        
        self.wait_window(dialog)
        
        new_text = result.get("text")
        
        if new_text is not None and new_text.strip() and new_text != original_text:
            self.sentences[idx]['original_sentence'] = new_text
            self.sentences[idx]['tts_generated'] = 'no'
            self.sentences[idx]['marked'] = True
            self.playlist_frame.update_item(idx)
            self.save_session()

    def split_selected_chunk(self):
        indices = self.playlist_frame.get_selected_indices()
        if len(indices) != 1: return messagebox.showinfo("Info", "Select one item to split.")
        
        idx = indices[0]
        item = self.sentences[idx]

        if item.get("tts_generated") == "yes" and not messagebox.askyesno("Confirm Deletion", "Splitting this chunk will delete its existing audio file and require regeneration. Continue?"):
            return

        self._delete_audio_file_for_item(item)

        original_text = item.get('original_sentence', '')
        if not original_text: return

        split_sentences = self.text_processor.splitter.split(original_text)
        if len(split_sentences) <= 1: return messagebox.showinfo("Info", "Cannot split this chunk further.")

        new_items = [{
            "uuid": uuid.uuid4().hex, "original_sentence": s.strip(), "paragraph": "no",
            "tts_generated": "no", "marked": True,
            "is_chapter_heading": bool(self.text_processor.chapter_regex.match(s.strip()))
        } for s in split_sentences if s.strip()]
        
        current_page = self.playlist_frame.current_page
        self.sentences[idx:idx+1] = new_items
        self._renumber_sentences()
        self.playlist_frame.load_data(self.sentences, page_to_display=current_page)
        self.save_session()
        messagebox.showinfo("Success", f"Split chunk into {len(new_items)} sentences.")

    def split_all_failed_chunks(self, confirm=True):
        failed_indices = [i for i, s in enumerate(self.sentences) if s.get('tts_generated') == 'failed']
        if not failed_indices:
            if confirm: messagebox.showinfo("Info", "No failed chunks found to split.")
            return
        
        if confirm and not messagebox.askyesno("Confirm Deletion", f"This will attempt to split {len(failed_indices)} failed chunks, deleting their current audio. This cannot be undone. Continue?"):
            return

        current_page = self.playlist_frame.current_page
        split_count = 0

        for idx in sorted(failed_indices, reverse=True):
            item = self.sentences[idx]
            self._delete_audio_file_for_item(item)
            original_text = item.get('original_sentence', '')
            
            split_sentences = self.text_processor.splitter.split(original_text)
            if len(split_sentences) > 1:
                new_items = [{
                    "uuid": uuid.uuid4().hex, "original_sentence": s.strip(), "paragraph": "no",
                    "tts_generated": "no", "marked": True,
                    "is_chapter_heading": bool(self.text_processor.chapter_regex.match(s.strip()))
                } for s in split_sentences if s.strip()]
                
                self.sentences[idx:idx+1] = new_items
                split_count += 1
        
        if split_count > 0:
            self._renumber_sentences()
            self.playlist_frame.load_data(self.sentences, page_to_display=current_page)
            self.save_session()
            messagebox.showinfo("Success", f"Successfully split {split_count} failed chunks.")
        else:
            messagebox.showinfo("Info", "No splittable failed chunks were found (all were single sentences).")

    def regenerate_marked_sentences(self):
        # Auto-Fix Sub Loop Logic
        if self.auto_regen_sub.get() and self.auto_fix_stage == "NONE":
            self.auto_fix_stage = "SUB_LOOP"

        indices = [i for i, s in enumerate(self.sentences) if s.get('marked')]
        if not indices: return messagebox.showinfo("Info", "No sentences marked for regeneration.")
        self.start_generation_orchestrator(indices)

    def _renumber_sentences(self):
        for i, item in enumerate(self.sentences):
            item['sentence_number'] = str(i + 1)

    def insert_pause(self):
        idx = self.playlist_frame.get_selected_indices()
        insert_index = idx[0] if idx else len(self.sentences)
        dialog = ctk.CTkInputDialog(text="Pause duration in milliseconds:", title="Insert Pause")
        duration_str = dialog.get_input()
        if duration_str and duration_str.isdigit():
            current_page = self.playlist_frame.current_page
            pause_item = {"uuid": uuid.uuid4().hex, "original_sentence": f"--- PAUSE ({duration_str}ms) ---", "is_pause": True, "duration": int(duration_str), "tts_generated": "n/a"}
            self.sentences.insert(insert_index, pause_item)
            self._renumber_sentences()
            self.playlist_frame.load_data(self.sentences, page_to_display=current_page)
            self.save_session()

    def insert_chapter_marker(self):
        """Manually inserts a chapter heading item."""
        idx = self.playlist_frame.get_selected_indices()
        insert_index = idx[0] if idx else len(self.sentences)
        
        dialog = ctk.CTkInputDialog(text="Enter Chapter Name (e.g., 'Chapter 5'):", title="Insert Chapter")
        chapter_name = dialog.get_input()
        
        if chapter_name and chapter_name.strip():
            current_page = self.playlist_frame.current_page
            # Create a manual chapter item.
            # We set is_chapter_heading=True so the export logic sees it as a split point.
            # We also set marked=True so the user can choose to generate audio for the title itself if they want (TTS reading "Chapter 5")
            new_item = {
                "uuid": uuid.uuid4().hex, 
                "original_sentence": chapter_name.strip(), 
                "paragraph": "no", 
                "tts_generated": "no", 
                "marked": True, 
                "is_chapter_heading": True
            }
            self.sentences.insert(insert_index, new_item)
            self._renumber_sentences()
            self.playlist_frame.load_data(self.sentences, page_to_display=current_page)
            self.save_session()
            messagebox.showinfo("Success", "Chapter marker inserted. It will be treated as a chapter split during export.")

    def insert_text_block(self):
        idx = self.playlist_frame.get_selected_indices()
        insert_index = idx[0] if idx else len(self.sentences)
        dialog = ctk.CTkInputDialog(text="Enter new text:", title="Insert Text Block")
        new_text = dialog.get_input()
        if new_text and new_text.strip():
            current_page = self.playlist_frame.current_page
            new_item = {"uuid": uuid.uuid4().hex, "original_sentence": new_text.strip(), "paragraph": "no", "tts_generated": "no", "marked": True, "is_chapter_heading": False}
            self.sentences.insert(insert_index, new_item)
            self._renumber_sentences()
            self.playlist_frame.load_data(self.sentences, page_to_display=current_page)
            self.save_session()
            
    def delete_selected_blocks(self):
        indices = self.playlist_frame.get_selected_indices()
        if not indices: return messagebox.showwarning("Warning", "Select items to delete.")
        if not messagebox.askyesno("Confirm Deletion", f"Delete {len(indices)} item(s) and their associated audio files? This cannot be undone."): return
        
        current_page = self.playlist_frame.current_page
        for idx in sorted(indices, reverse=True):
            item_to_delete = self.sentences.pop(idx)
            self._delete_audio_file_for_item(item_to_delete)
        
        self._renumber_sentences()
        
        items_per_page = self.playlist_frame.items_per_page
        total_pages = (len(self.sentences) - 1) // items_per_page + 1 if self.sentences else 1
        page_to_display = min(current_page, max(0, total_pages - 1))
        
        self.playlist_frame.load_data(self.sentences, page_to_display=page_to_display)
        self.save_session()

    def move_selected_items(self, direction: int):
        """Moves selected items up (-1) or down (1) in the playlist."""
        selected_indices = self.playlist_frame.get_selected_indices()
        if not selected_indices:
            messagebox.showinfo("Info", "Select one or more items to move.")
            return

        sorted_indices = sorted(selected_indices, reverse=(direction == 1))
        new_selection = set()
        moved_count = 0
        
        temp_sentences = list(self.sentences)
        
        for idx in sorted_indices:
            new_idx = idx + direction
            if 0 <= new_idx < len(self.sentences):
                temp_sentences[idx], temp_sentences[new_idx] = temp_sentences[new_idx], temp_sentences[idx]
                new_selection.add(new_idx)
                moved_count += 1
            else:
                new_selection.add(idx)

        if moved_count > 0:
            self.sentences = temp_sentences
            self._renumber_sentences()
            
            items_per_page = self.playlist_frame.items_per_page
            current_page = self.playlist_frame.current_page
            new_page_for_first_selection = min(new_selection) // items_per_page if new_selection else current_page
            
            self.playlist_frame.load_data(self.sentences, page_to_display=new_page_for_first_selection)
            self.playlist_frame.selected_indices = new_selection
            self.playlist_frame._update_all_visuals()
            self.save_session()

    def find_next_item(self, direction: int, status_to_find: str):
        """Navigates to the next/previous item with the given status."""
        matching_indices = [i for i, s in enumerate(self.sentences) if s.get('tts_generated') == status_to_find]
        
        if not matching_indices:
            messagebox.showinfo("Not Found", f"No chunks with status '{status_to_find}' found.")
            return

        current_selection = self.playlist_frame.get_selected_indices()
        start_index = current_selection[0] if current_selection else -1 if direction == 1 else len(self.sentences)

        target_index = -1
        if direction == 1:  # Find next
            next_items = [i for i in matching_indices if i > start_index]
            target_index = next_items[0] if next_items else matching_indices[0]
        else:  # Find previous
            prev_items = [i for i in matching_indices if i < start_index]
            target_index = prev_items[-1] if prev_items else matching_indices[-1]

        items_per_page = self.playlist_frame.items_per_page
        target_page = target_index // items_per_page

        if self.playlist_frame.current_page != target_page:
            self.playlist_frame.display_page(target_page)
        
        self.playlist_frame.selected_indices = {target_index}
        self.playlist_frame.last_clicked_index = target_index
        self.playlist_frame._update_all_visuals()
        # FIX: Update stats panel after navigating
        self.playlist_frame.update_stats_panel()

    def _get_indices_to_process(self):
        if self.apply_fix_to_all_failed.get():
            return [i for i, s in enumerate(self.sentences) if s.get('tts_generated') == 'failed']
        else:
            return self.playlist_frame.get_selected_indices()

    def merge_failed_down(self):
        """Merges selected failed chunks (or all failed chunks) with the one below."""
        indices_to_process = self._get_indices_to_process()
        
        if not indices_to_process:
            return messagebox.showinfo("Info", "No failed chunks selected or found to merge.")
            
        if self.apply_fix_to_all_failed.get():
            if not messagebox.askyesno("Confirm Merge All", f"This will attempt to merge all {len(indices_to_process)} failed chunks with the chunk below each one. Continue?"):
                return

        merged_count = 0
        for idx in sorted(indices_to_process, reverse=True):
            if self.sentences[idx].get('tts_generated') != 'failed': continue
            if idx + 1 >= len(self.sentences) or self.sentences[idx+1].get('is_pause'): continue

            item1 = self.sentences[idx]
            item2 = self.sentences[idx+1]
            
            new_text = item1.get('original_sentence', '') + " " + item2.get('original_sentence', '')
            
            self._delete_audio_file_for_item(item1)
            self._delete_audio_file_for_item(item2)
            
            self.sentences[idx]['original_sentence'] = new_text
            self.sentences[idx]['tts_generated'] = 'no'
            self.sentences[idx]['marked'] = True
            
            self.sentences.pop(idx + 1)
            merged_count += 1
        
        if merged_count > 0:
            self._renumber_sentences()
            self.playlist_frame.load_data(self.sentences, page_to_display=self.playlist_frame.current_page)
            self.save_session()
            messagebox.showinfo("Success", f"{merged_count} chunk(s) merged and marked for regeneration.")
        else:
            messagebox.showinfo("Info", "No mergeable failed chunks were found.")

    def clean_special_chars_in_selected(self):
        """Removes special characters from the text of selected/all failed chunks."""
        indices_to_process = self._get_indices_to_process()
        if not indices_to_process: return messagebox.showwarning("Warning", "Please select one or more chunks to clean.")
            
        cleaned_count = 0
        for idx in indices_to_process:
            item = self.sentences[idx]
            original_text = item.get('original_sentence', '')
            cleaned_text = self.text_processor.clean_text_aggressively(original_text)
            
            if cleaned_text != original_text:
                item['original_sentence'] = cleaned_text
                item['tts_generated'] = 'no'
                item['marked'] = True
                self.playlist_frame.update_item(idx)
                cleaned_count += 1
        
        if cleaned_count > 0:
            self.save_session()
            messagebox.showinfo("Success", f"Cleaned special characters from {cleaned_count} chunk(s). They are now marked for regeneration.")
        else:
            messagebox.showinfo("Info", "No special characters were found to clean in the targeted chunks.")

    def filter_non_dict_words_in_selected(self):
        """Removes words with non-English characters from selected/all failed chunks."""
        indices_to_process = self._get_indices_to_process()
        if not indices_to_process: return messagebox.showwarning("Warning", "Please select one or more chunks to filter.")
            
        filtered_count = 0
        for idx in indices_to_process:
            item = self.sentences[idx]
            original_text = item.get('original_sentence', '')
            filtered_text = self.text_processor.filter_non_english_words(original_text)

            if filtered_text != original_text:
                item['original_sentence'] = filtered_text
                item['tts_generated'] = 'no'
                item['marked'] = True
                self.playlist_frame.update_item(idx)
                filtered_count += 1
        
        if filtered_count > 0:
            self.save_session()
            messagebox.showinfo("Success", f"Filtered words in {filtered_count} chunk(s). They are now marked for regeneration.")
        else:
            messagebox.showinfo("Info", "No words were filtered in the targeted chunks.")

    def _get_generation_settings(self):
        settings = {
            "ref_audio_path": self.ref_audio_path.get(), "exaggeration": self.exaggeration.get(),
            "cfg_weight": self.cfg_weight.get(), "temperature": self.temperature.get(),
            "speed": self.speed.get(), "items_per_page_str": self.items_per_page_str.get(),
            "target_gpus_str": self.target_gpus_str.get(), "num_full_outputs_str": self.num_full_outputs_str.get(),
            "master_seed_str": self.master_seed_str.get(), "num_candidates_str": self.num_candidates_str.get(),
            "max_attempts_str": self.max_attempts_str.get(), "asr_validation_enabled": self.asr_validation_enabled.get(),
            "asr_threshold_str": self.asr_threshold_str.get(),
            "disable_watermark": self.disable_watermark.get(), "generation_order": self.generation_order.get(),
            "chunking_enabled": self.chunking_enabled.get(), "max_chunk_chars_str": self.max_chunk_chars_str.get(),
            "silence_duration_str": self.silence_duration_str.get(), "norm_enabled": self.norm_enabled.get(),
            "silence_removal_enabled": self.silence_removal_enabled.get(), "norm_level_str": self.norm_level_str.get(),
            "silence_threshold": self.silence_threshold.get(),
            "silent_speed_str": self.silent_speed_str.get(),
            "frame_margin_str": self.frame_margin_str.get(),
            "metadata_artist": self.metadata_artist_str.get(), "metadata_album": self.metadata_album_str.get(),
            "metadata_title": self.metadata_title_str.get(),
            "auto_assemble_after_run": self.auto_assemble_after_run.get(),
        }
        return settings

    def _apply_generation_settings(self, settings):
        all_settings_map = {
            'ref_audio_path': self.ref_audio_path, 'exaggeration': self.exaggeration,
            'cfg_weight': self.cfg_weight, 'temperature': self.temperature, 'speed': self.speed,
            'items_per_page_str': self.items_per_page_str,
            'target_gpus_str': self.target_gpus_str, 'num_full_outputs_str': self.num_full_outputs_str,
            'master_seed_str': self.master_seed_str, 'num_candidates_str': self.num_candidates_str,
            'max_attempts_str': self.max_attempts_str, 'asr_validation_enabled': self.asr_validation_enabled,
            'asr_threshold_str': self.asr_threshold_str,
            'disable_watermark': self.disable_watermark, 'generation_order': self.generation_order,
            'chunking_enabled': self.chunking_enabled, 'max_chunk_chars_str': self.max_chunk_chars_str,
            'silence_duration_str': self.silence_duration_str, 'norm_enabled': self.norm_enabled,
            'silence_removal_enabled': self.silence_removal_enabled, 'norm_level_str': self.norm_level_str,
            'silence_threshold': self.silence_threshold,
            'silent_speed_str': self.silent_speed_str,
            'frame_margin_str': self.frame_margin_str,
            'metadata_artist': self.metadata_artist_str, 'metadata_album': self.metadata_album_str,
            'metadata_title': self.metadata_title_str,
            'auto_assemble_after_run': self.auto_assemble_after_run,
        }
        for key, var in all_settings_map.items():
            if key in settings:
                try: var.set(settings[key])
                except Exception as e: logging.warning(f"Could not apply setting for '{key}': {e}")
        
    def populate_template_dropdown(self):
        try:
            templates = sorted([f.stem for f in Path(self.TEMPLATES_DIR).glob("*.json")])
            self.template_option_menu.configure(values=templates if templates else ["No templates found"])
            self.selected_template_str.set(templates[0] if templates else "No templates found")
        except Exception as e:
            logging.error(f"Failed to populate template dropdown: {e}")
            self.template_option_menu.configure(values=["Error loading"])
            self.selected_template_str.set("Error loading")
            
    def save_generation_template(self):
        name = ctk.CTkInputDialog(text="Enter template name:", title="Save Template").get_input()
        if not name or not re.match("^[a-zA-Z0-9_-]*$", name):
            if name is not None: messagebox.showerror("Invalid Name", "Use only letters, numbers, underscores, hyphens.")
            return
        template_path = Path(self.TEMPLATES_DIR) / f"{name}.json"
        with open(template_path, 'w', encoding='utf-8') as f: json.dump(self._get_generation_settings(), f, indent=4)
        messagebox.showinfo("Success", f"Template '{name}' saved.")
        self.populate_template_dropdown()

    def load_generation_template(self):
        template_name = self.selected_template_str.get()
        if not template_name or "found" in template_name: return
        template_path = Path(self.TEMPLATES_DIR) / f"{template_name}.json"
        if not template_path.exists(): return messagebox.showerror("Error", f"Template file not found.")
        with open(template_path, 'r', encoding='utf-8') as f: settings = json.load(f)
        self._apply_generation_settings(settings)
        self.ref_audio_path_display.set(os.path.basename(self.ref_audio_path.get()) or "No file selected.")
        self.playlist_frame.refresh_view()
        messagebox.showinfo("Success", f"Template '{template_name}' loaded.")

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1, minsize=400)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        left_frame = ctk.CTkFrame(self, fg_color=self.colors["frame_bg"])
        left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        left_frame.grid_rowconfigure(0, weight=1); left_frame.grid_columnconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(left_frame, fg_color=self.colors["tab_bg"], text_color=self.text_color, segmented_button_selected_color="#3A7EBF")
        self.tabview.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.setup_tab = SetupTab(self.tabview.add("1. Setup"), self); self.setup_tab.pack(fill="both", expand=True)
        self.chapters_tab = ChaptersTab(self.tabview.add("2. Chapters"), self); self.chapters_tab.pack(fill="both", expand=True)
        self.generation_tab = GenerationTab(self.tabview.add("3. Generation"), self); self.generation_tab.pack(fill="both", expand=True)
        self.finalize_tab = FinalizeTab(self.tabview.add("4. Finalize"), self); self.finalize_tab.pack(fill="both", expand=True)
        self.advanced_tab = AdvancedTab(self.tabview.add("5. Advanced"), self); self.advanced_tab.pack(fill="both", expand=True)

        right_frame = ctk.CTkFrame(self, fg_color=self.colors["frame_bg"])
        right_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=1); right_frame.grid_columnconfigure(0, weight=1)
        self.playlist_frame = PlaylistFrame(master=right_frame, app_instance=self, fg_color=self.colors["tab_bg"])
        self.playlist_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=(0,5))
        
        self.controls = ControlsFrame(master=right_frame, app_instance=self, fg_color="transparent")
        self.controls.grid(row=1, column=0, pady=(5, 10), sticky="ew")
        
        self.bind("<m>", self.mark_current_sentence)

    def switch_to_tab(self, tab_index):
        tab_names = ["1. Setup", "2. Generation", "3. Finalize", "4. Advanced"]
        if 0 <= tab_index < len(tab_names):
            self.tabview.set(tab_names[tab_index])
