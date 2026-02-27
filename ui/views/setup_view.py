from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, 
    QFileDialog, QMessageBox, QLabel, QGroupBox, QComboBox, QCheckBox, QLayout,
    QScrollArea
)
from PySide6.QtCore import Qt, Signal
from typing import Optional, List, Dict, Any
import os
import shutil
import dataclasses
import logging

from core.state import AppState
from utils.text_processor import TextPreprocessor
from core.services.project_service import ProjectService
from core.services.template_service import TemplateService
from ui.components.progress_widget import ProgressWidget

class SetupView(QWidget):
    template_loaded = Signal()
    session_updated = Signal() # New: Emitted when sentences/session data changes

    def __init__(
        self, 
        app_state: AppState,
        project_service: 'ProjectService',
        template_service: 'TemplateService',
        parent: Optional[QWidget] = None
    ) -> None:
        """
        
        
        Args:
            app_state: Application state
            project_service: Injected project service
            template_service: Injected template service
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.state = app_state
        self.processor = TextPreprocessor()
        
        self.project_service = project_service
        self.template_service = template_service
        self.gen_service: Optional[Any] = None # Injected later
        
        self.setup_ui()
        self.populate_templates()
        self.check_system()

    def setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        
        self.setup_header(layout)
        self.setup_session_controls(layout)
        self.setup_processing_controls(layout)
        self.setup_key_params(layout) # Restored
        self.setup_voice_controls(layout)
        self.setup_main_controls(layout)
        self.setup_system_check(layout)
        layout.addStretch()
        
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def setup_header(self, layout: QVBoxLayout) -> None:
        # --- Session Header ---
        header_layout = QHBoxLayout()
        header = QLabel("Session & Source")
        font = header.font()
        font.setPointSize(14)
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)
        header_layout.addStretch()
        
        # Session Btns
        new_btn = QPushButton("New Session")
        new_btn.clicked.connect(self.new_session)
        load_btn = QPushButton("Load Session")
        load_btn.clicked.connect(self.load_session_dialog)
        
        save_btn = QPushButton("💾 Save Session")
        save_btn.clicked.connect(self.manual_save_session)
        
        header_layout.addWidget(new_btn)
        header_layout.addWidget(load_btn)
        header_layout.addWidget(save_btn)
        layout.addLayout(header_layout)

    def setup_session_controls(self, layout: QVBoxLayout) -> None:
        form_layout = QFormLayout()
        
        # Session Name
        self.session_name_edit = QLineEdit()
        self.session_name_edit.setPlaceholderText("My Audiobook Project")
        self.session_name_edit.textChanged.connect(lambda t: setattr(self.state, 'session_name', t))
        form_layout.addRow("Session Name:", self.session_name_edit)
        
        # Source Text File
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_btn = QPushButton("Browse...")
        self.file_btn.clicked.connect(self.browse_file)
        
        file_layout = QHBoxLayout()
        file_layout.addWidget(self.file_path_edit)
        file_layout.addWidget(self.file_btn)
        form_layout.addRow("Source Text:", file_layout)
        
        layout.addLayout(form_layout)


    def setup_processing_controls(self, layout: QVBoxLayout) -> None:
        # Edit & Process Button (Consolidated Workflow)
        self.edit_btn = QPushButton("Edit Source Text")
        self.edit_btn.setToolTip("Opens file in external editor, then reloads")
        self.edit_btn.setStyleSheet("background-color: #2E86C1; color: white; padding: 10px; font-weight: bold;")
        self.edit_btn.clicked.connect(self.open_editor_and_process)
        layout.addWidget(self.edit_btn)
        
        # Aggro Clean Switch
        self.aggro_chk = QCheckBox("Remove all special characters on processing")
        self.aggro_chk.setChecked(self.state.aggro_clean_on_parse)
        self.aggro_chk.stateChanged.connect(
            lambda s: setattr(self.state, 'aggro_clean_on_parse', s == Qt.Checked or s == 2)
        )
        layout.addWidget(self.aggro_chk)
        
    def setup_key_params(self, layout: QVBoxLayout) -> None:
        """Restores the 'Key Parameters (Loaded)' display from Reference."""
        group = QGroupBox("Key Parameters (Summary)")
        f_layout = QFormLayout(group)
        
        self.lbl_ref_audio = QLabel("--")
        self.lbl_voice_name = QLabel("--") # New
        self.lbl_voice_preset = QLabel("--")
        self.lbl_exaggeration = QLabel("--")
        self.lbl_temp = QLabel("--")
        self.lbl_speed = QLabel("--")
        self.lbl_auto_expression = QLabel("--")
        
        f_layout.addRow("Voice Profile:", self.lbl_voice_name) # New
        f_layout.addRow("Voice Preset:", self.lbl_voice_preset)
        f_layout.addRow("Reference Audio:", self.lbl_ref_audio)
        f_layout.addRow("Exaggeration:", self.lbl_exaggeration)
        f_layout.addRow("Temperature:", self.lbl_temp)
        f_layout.addRow("Speed:", self.lbl_speed)
        f_layout.addRow("Auto-Expression:", self.lbl_auto_expression)
        
        # Edit Button to jump to Generation Tab? (Optional, kept simpler for now)
        layout.addWidget(group)
        
    def refresh_params_display(self) -> None:
        """Updates the Parameter labels from AppState."""
        self.lbl_voice_name.setText(self.state.voice_name) # New

        # Ref Audio
        ref = self.state.ref_audio_path
        self.lbl_ref_audio.setText(os.path.basename(ref) if ref else "None")
        if ref: self.lbl_ref_audio.setToolTip(ref)
            
        # Settings
        s = self.state.settings
        self.lbl_exaggeration.setText(f"{s.exaggeration:.2f}")
        self.lbl_temp.setText(f"{s.temperature:.2f}")
        self.lbl_speed.setText(f"{s.speed:.2f}x")
        
        # Voice Preset (from generation view if available)
        preset = getattr(s, 'voice_preset', 'Custom')
        self.lbl_voice_preset.setText(preset)
        
        # Auto-Expression
        auto_expr = getattr(s, 'auto_expression_enabled', False)
        sensitivity = getattr(s, 'expression_sensitivity', 1.0)
        if auto_expr:
            self.lbl_auto_expression.setText(f"Enabled (Sensitivity: {sensitivity:.1f})")
        else:
            self.lbl_auto_expression.setText("Disabled")
            
        pass

    # UI refreshes should be signal-driven, not event-driven
    
    def setup_voice_controls(self, layout: QVBoxLayout) -> None:
        tpl_group = QGroupBox("Generation Voices")
        t_layout = QHBoxLayout(tpl_group)
        self.template_combo = QComboBox()
        self.template_combo.addItems(["No voices found"]) 
        
        self.load_tpl_btn = QPushButton("Load Voice")
        self.load_tpl_btn.clicked.connect(self.load_template)
        
        self.del_tpl_btn = QPushButton("Delete Voice")
        self.del_tpl_btn.setStyleSheet("background-color: #A93226; color: white; font-weight: bold;")
        self.del_tpl_btn.clicked.connect(self.delete_template)
        
        t_layout.addWidget(QLabel("Select Voice:"))
        t_layout.addWidget(self.template_combo, stretch=1)
        t_layout.addWidget(self.load_tpl_btn)
        t_layout.addWidget(self.del_tpl_btn)
        layout.addWidget(tpl_group)

    def setup_main_controls(self, layout: QVBoxLayout) -> None:
        ctrl_group = QGroupBox("Main Controls")
        c_layout = QVBoxLayout(ctrl_group)
        
        # Auto Assemble
        self.auto_asm_chk = QCheckBox("Re-Assemble After Full Run")
        self.auto_asm_chk.setChecked(self.state.auto_assemble_after_run)
        self.auto_asm_chk.stateChanged.connect(
            lambda s: setattr(self.state, 'auto_assemble_after_run', s == Qt.Checked or s == 2)
        )
        c_layout.addWidget(self.auto_asm_chk)

        # Auto Regen
        # Auto Regen Row
        reg_layout = QHBoxLayout()
        self.auto_reg_chk = QCheckBox("Continue to Regenerate until all files pass")
        self.auto_reg_chk.setChecked(getattr(self.state, 'auto_regen_main', False))
        self.auto_reg_chk.setEnabled(False)  # Read-only reflection; change setting in Config → ASR Validation
        self.auto_reg_chk.setToolTip("Reflects the 'Auto-loop' setting from Config → ASR Validation.\nChange the setting there.")
        
        # ASR Info Label (User Request)
        s = self.state.settings
        self.lbl_auto_reg_info = QLabel(f"(Max Retries: {s.max_attempts} | ASR: {int(s.asr_threshold*100)}%)")
        self.lbl_auto_reg_info.setStyleSheet("color: gray; font-size: 8pt; margin-left: 5px;")
        
        reg_layout.addWidget(self.auto_reg_chk)
        reg_layout.addWidget(self.lbl_auto_reg_info)
        reg_layout.addStretch()
        
        c_layout.addLayout(reg_layout)

        # GPU Status Display (Replaced Checkboxes per User Request)
        self.lbl_gpu_status = QLabel("")
        self.lbl_gpu_status.setAlignment(Qt.AlignCenter)
        self.lbl_gpu_status.setTextFormat(Qt.RichText) 
        self.lbl_gpu_status.setStyleSheet("color: #555; font-size: 10pt; margin: 10px 0;")
        c_layout.addWidget(self.lbl_gpu_status)
        self.refresh_gpu_status()

        # Generation Control Layout: [ Start ] [ Stop ]
        gen_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("Start Generation")
        self.start_btn.setStyleSheet("background-color: #27AE60; color: white; font-size: 14px; font-weight: bold; padding: 10px;")
        self.start_btn.clicked.connect(self.toggle_generation)
        gen_layout.addWidget(self.start_btn, stretch=3)
        
        self.stop_btn = QPushButton("🛑 Stop") 
        self.stop_btn.setToolTip("Stop Generation")
        self.stop_btn.setFixedWidth(100) 
        self.stop_btn.setStyleSheet("background-color: #A93226; color: white; font-weight: bold; border-radius: 4px;")
        self.stop_btn.clicked.connect(self.stop_generation)
        
        gen_layout.addWidget(self.stop_btn, stretch=0)
        
        c_layout.addLayout(gen_layout)
        
        self.progress_widget = ProgressWidget()
        self.progress_widget.setVisible(False)  # Hidden until generation starts
        layout.addWidget(self.progress_widget)
        
        layout.addWidget(ctrl_group)

    def refresh_gpu_status(self) -> None:
        """Updates the GPU indicator matching the Chapters view."""
        if not hasattr(self, 'lbl_gpu_status'): return
        
        caps = self.state.system_capabilities
        gpu_names = caps.get('gpu_names', [])
        targets = self.state.settings.target_gpus
        
        active_names = []
        if "cuda:" in targets:
            try:
                parts = targets.split(',')
                for p in parts:
                    idx = int(p.split(':')[1])
                    if idx < len(gpu_names):
                        active_names.append(gpu_names[idx])
            except: 
                pass
                
        if active_names:
            if len(active_names) > 1:
                joined = "<br>".join([f"{n} ●" for n in active_names])
                text = f"Active GPUs:<br>{joined}"
                self.lbl_gpu_status.setText(text)
                self.lbl_gpu_status.setStyleSheet("color: #00FF00; font-weight: bold; margin: 5px 0;")
            else:
                text = f"Active GPU:<br>{active_names[0]} ●"
                self.lbl_gpu_status.setText(text)
                self.lbl_gpu_status.setStyleSheet("color: #27AE60; font-weight: bold; margin: 5px 0;")
            self.lbl_gpu_status.setVisible(True)
        else:
            self.lbl_gpu_status.setVisible(False)

    def refresh_values(self) -> None:
        """Updates UI based on state changes."""
        s = self.state.settings
        if hasattr(self, 'lbl_auto_reg_info'):
            self.lbl_auto_reg_info.setText(f"(Max Retries: {s.max_attempts} | ASR: {int(s.asr_threshold*100)}%)")
        if hasattr(self, 'auto_reg_chk'):
            self.auto_reg_chk.blockSignals(True)
            self.auto_reg_chk.setChecked(getattr(self.state, 'auto_regen_main', False))
            self.auto_reg_chk.blockSignals(False)
        self.refresh_gpu_status()

    def setup_system_check(self, layout: QVBoxLayout) -> None:
        sys_group = QGroupBox("System Check")
        s_layout = QFormLayout(sys_group)
        self.lbl_ffmpeg = QLabel("Checking...")
        self.lbl_auto = QLabel("Checking...")
        self.lbl_gpu = QLabel("Checking...")
        
        s_layout.addRow("FFmpeg:", self.lbl_ffmpeg)
        s_layout.addRow("Auto-Editor:", self.lbl_auto)
        s_layout.addRow("GPU Mode:", self.lbl_gpu)
        
        layout.addWidget(sys_group)

    def check_system(self) -> None:
        ffmpeg = shutil.which('ffmpeg')
        self.lbl_ffmpeg.setText("Found" if ffmpeg else "Not Found (Required)")
        self.lbl_ffmpeg.setStyleSheet("color: green" if ffmpeg else "color: red")
        
        ae = shutil.which('auto-editor')
        self.lbl_auto.setText("Found" if ae else "Not Found (Optional)")
        self.lbl_auto.setStyleSheet("color: green" if ae else "color: orange")

        caps = self.state.system_capabilities
        if caps.get('cuda_available', False):
            count = caps.get('gpu_count', 0)
            names = caps.get('gpu_names', [])
            targets = self.state.settings.target_gpus
            
            active_indices = []
            if "cuda:" in targets:
                parts = targets.split(',')
                for p in parts:
                    try:
                        idx = int(p.split(':')[1])
                        active_indices.append(idx)
                    except: pass
            
            if active_indices:
                active_names = [names[i] for i in active_indices if i < len(names)]
                if len(active_names) > 1:
                    # Dual/Multi Mode
                    self.lbl_gpu.setText(f"Multi-GPU Active ({len(active_names)} devices): {', '.join(active_names)}")
                else:
                    # Single Mode
                    self.lbl_gpu.setText(f"Single GPU Active: {active_names[0]}")
            else:
                 self.lbl_gpu.setText("No GPUs Selected")

            self.lbl_gpu.setStyleSheet("color: green")
        else:
            self.lbl_gpu.setText("CPU Mode (No CUDA found)")
            self.lbl_gpu.setStyleSheet("color: orange")

    def browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Text Source", "", 
                                            "Text/Ebook (*.txt *.epub *.pdf *.docx *.mobi)")
        if path:
            self.file_path_edit.setText(path)
            self.state.source_file_path = path
            if not self.session_name_edit.text():
                name = os.path.splitext(os.path.basename(path))[0]
                self.session_name_edit.setText(name)
                self.state.session_name = name

    def open_editor_and_process(self) -> None:
        """
        Opens the internal source editor. 
        On save, writes back to disk and processes chunks.
        """
        if not self.state.source_file_path: 
            QMessageBox.warning(self, "No File", "Please select a source file first.")
            return
        
        try:
            # 1. Read File
            raw_text = self.processor.extract_text_from_file(self.state.source_file_path)
            if raw_text.startswith("Error"):
                QMessageBox.critical(self, "Error", raw_text)
                return
            
            # 2. Internal Editor (ReviewTextDialog)
            from ui.dialogs.review_text_dialog import ReviewTextDialog
            dlg = ReviewTextDialog(raw_text, self)
            
            if dlg.exec():
                final_text = dlg.result_text
                
                # 3. Save changes to source file
                try:
                    with open(self.state.source_file_path, 'w', encoding='utf-8') as f:
                        f.write(final_text)
                except Exception as e:
                    print(f"Warning: Could not save back to source file: {e}")

                self._perform_text_processing(final_text)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))



    def _perform_text_processing(self, text: str) -> None:
        """Helper to handle the logic of processing text after user review."""
        # Step 1: Preprocess (Split sentences + clean)
        sentences = self.processor.preprocess_text(
            text, 
            aggressive_clean=self.state.aggro_clean_on_parse
        )
        
        # Step 2: Chunking (if enabled)
        if self.state.settings.chunking_enabled:
            sentences = self.processor.group_sentences_into_chunks(
                sentences, 
                max_chars=self.state.settings.max_chunk_chars
            )
        
        self.state.sentences = sentences
        self.state.is_session_loaded = True # New data created, safe to save.
        # Signal Global Update (Fixes Playlist not showing items)
        self.session_updated.emit()
        
        QMessageBox.information(self, "Success", f"Loaded {len(sentences)} chunks.")
        
        # Save Session
        self.project_service.save_session(self.state.session_name, {
            "source_file_path": self.state.source_file_path,
            "sentences": self.state.sentences,
            "generation_settings": dataclasses.asdict(self.state.settings),
            "ref_audio_path": self.state.ref_audio_path,
            "voice_preset": getattr(self.state.settings, 'voice_preset', 'Custom')
        })

    def new_session(self) -> None:
        self.session_name_edit.clear()
        self.file_path_edit.clear()
        self.state.sentences = []
        self.state.is_session_loaded = False
        
    def load_session_dialog(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "Select Session Folder", "Outputs_Pro")
        if dir_path:
            data = self.project_service.load_session(dir_path)
            if data:
                # DEBUG: Log keys
                logging.info(f"Session Load Keys: {list(data.keys())}")
                if 'sentences' in data:
                    logging.info(f"Sentences type: {type(data['sentences'])}, len: {len(data['sentences'])}")
                
                # Update State & UI
                self.state.session_name = data.get('session_name', '')
                self.session_name_edit.setText(self.state.session_name)
                
                loaded_sentences = data.get('sentences', [])
                self.state.sentences = loaded_sentences
                self.state.is_session_loaded = True # Safety Flag
                
                src_path = data.get('source_file_path', '')
                self.state.source_file_path = src_path # FIX: Sync state
                self.file_path_edit.setText(src_path)
                
                if 'generation_settings' in data:
                     # Remove certain global user preferences so they aren't overwritten by historical project saves
                     loaded_settings = data['generation_settings'].copy()
                     
                     # Keys to preserve from current global AppState
                     preserve_keys = ['max_attempts', 'target_gpus']
                     for key in preserve_keys:
                         if key in loaded_settings:
                             del loaded_settings[key]
                             
                     self.state.update_settings(**loaded_settings)
                
                # Restore ref_audio_path
                if 'ref_audio_path' in data:
                    self.state.ref_audio_path = data['ref_audio_path']
                
                # Restore voice_preset (stored separately from settings)
                if 'voice_preset' in data:
                    # This will be picked up by Key Parameters display
                    setattr(self.state.settings, 'voice_preset', data['voice_preset'])
                
                self.session_updated.emit() # Refresh other views
                
                msg = f"Session loaded with {len(self.state.sentences)} chunks."
                
                # Auto-Recovery Suggestion
                if len(self.state.sentences) == 0 and src_path and os.path.exists(src_path):
                    msg += "\n\nSource file found. Would you like to re-process text now?"
                    reply = QMessageBox.question(self, "Loaded (Empty)", msg, 
                                               QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                    if reply == QMessageBox.Yes:
                        self.open_editor_and_process()
                else:
                    QMessageBox.information(self, "Loaded", msg)
            else:
                QMessageBox.warning(self, "Error", 
                    "Failed to load session content.\n\n"
                    "Please make sure you selected a specific Session Folder (e.g., 'Outputs_Pro/MyBook'), "
                    "and not the parent 'Outputs_Pro' folder itself.")

    def manual_save_session(self) -> None:
        if not self.state.session_name:
            QMessageBox.warning(self, "Error", "No active session to save.")
            return
            
        if not self.state.is_session_loaded and not self.state.sentences:
            # If not loaded and empty, warn user
            reply = QMessageBox.question(self, "Safety Warning", 
                                       "Session data has not been fully loaded. Saving now might overwrite your file with empty data.\n\n"
                                       "Are you SURE you want to save?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return

        if self.project_service.save_current_session(self.state):
            self.state.is_session_loaded = True # Mark safe
            QMessageBox.information(self, "Saved", f"Session '{self.state.session_name}' saved successfully.")
        else:
            QMessageBox.critical(self, "Error", "Failed to save session.")

    def toggle_generation(self) -> None:
        """Starts or stops generation based on current state."""
        if not self.gen_service:
            QMessageBox.critical(self, "Error", "Generation service not initialized.")
            return
        
        # Check if generation is already running
        if hasattr(self.gen_service, 'is_running') and self.gen_service.is_running:
            self.stop_generation()
            return
        
        # Validate prerequisites
        if not self.state.sentences:
            QMessageBox.warning(self, "No Data", "Please load or process text first.")
            return
        
        if not self.state.ref_audio_path:
            QMessageBox.warning(self, "No Reference", "Please select a reference audio file in the Generation tab.")
            return
        
        # Start generation
        try:
            self.gen_service.start_generation()
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            logging.info("Generation started from Setup view")
        except Exception as e:
            logging.error(f"Failed to start generation: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start generation:\n{e}")

    def populate_templates(self) -> None:
        templates = self.template_service.list_templates()
        self.template_combo.clear()
        if templates:
            self.template_combo.addItems(templates)
        else:
            self.template_combo.addItem("No voices found")

    def load_template(self) -> None:
        name = self.template_combo.currentText()
        if not name or "found" in name: 
            return
        
        data = self.template_service.load_template(name)
        if data:
            try:
                for key, value in data.items():
                    if hasattr(self.state.settings, key):
                        setattr(self.state.settings, key, value)
                
                self.state.voice_name = name # Update State
                self.refresh_params_display() # Update UI
                
                QMessageBox.information(self, "Success", f"Loaded voice '{name}'.")
                self.template_loaded.emit() 
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to apply voice: {e}")
        else:
            QMessageBox.warning(self, "Error", "Failed to load voice data.")

    def delete_template(self) -> None:
        name = self.template_combo.currentText()
        if not name or "found" in name: 
            return
        
        reply = QMessageBox.question(self, "Confirm Delete", 
                                   f"Are you sure you want to delete voice '{name}'?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            if self.template_service.delete_template(name):
                QMessageBox.information(self, "Deleted", f"Voice '{name}' deleted.")
                self.populate_templates()
            else:
                QMessageBox.critical(self, "Error", f"Failed to delete voice '{name}'.")

    def set_generation_service(self, service: Any) -> None:
        self.gen_service = service
        
        service.progress_update.connect(self.progress_widget.update_progress)
        service.stats_updated.connect(self.progress_widget.update_stats)
        service.eta_updated.connect(self.progress_widget.update_eta)
        service.started.connect(lambda: self.progress_widget.setVisible(True))
        service.finished.connect(lambda: self.progress_widget.setVisible(False))
        service.stopped.connect(lambda: self.progress_widget.setVisible(False))

    def stop_generation(self) -> None:
        if self.gen_service:
            self.gen_service.request_stop()
        else:
            QMessageBox.warning(self, "Error", "Generation Service not connected.")
