# ui/tabs/setup_tab.py
import customtkinter as ctk

class SetupTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance

        self.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self, text="Session & Source File", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.app.text_color).pack(pady=(10, 5), anchor="w", padx=10)
        
        ctk.CTkLabel(self, text="Session Name:", text_color=self.app.text_color).pack(anchor="w", padx=10)
        ctk.CTkEntry(self, textvariable=self.app.session_name, text_color=self.app.text_color).pack(fill="x", padx=10)
        btn_frame = ctk.CTkFrame(self, fg_color="transparent"); btn_frame.pack(fill="x", pady=5, padx=5)
        btn_frame.grid_columnconfigure((0,1), weight=1)
        ctk.CTkButton(btn_frame, text="New Session", command=self.app.new_session, text_color="black").grid(row=0, column=0, padx=5, sticky="ew")
        ctk.CTkButton(btn_frame, text="Load Session", command=self.app.load_session, text_color="black").grid(row=0, column=1, padx=5, sticky="ew")

        # --- TEXT FILE CONTROLS ---
        ctk.CTkLabel(self, text="Source File:", text_color=self.app.text_color).pack(anchor="w", padx=10, pady=(10,0))
        self.app.source_file_label = ctk.CTkLabel(self, text="No file selected.", wraplength=350, text_color=self.app.text_color)
        self.app.source_file_label.pack(anchor="w", padx=10)
        
        ctk.CTkButton(self, text="Select File...", command=self.app.select_source_file, text_color="black").pack(fill="x", padx=10, pady=5)
        
        # --- PROCESSING BUTTONS FRAME ---
        process_btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        process_btn_frame.pack(fill="x", padx=10, pady=(5,10))
        process_btn_frame.grid_columnconfigure(0, weight=1)
        
        self.app.aggro_clean_switch = ctk.CTkSwitch(process_btn_frame, text="Remove all special characters on processing", variable=self.app.aggro_clean_on_parse, text_color=self.app.text_color)
        self.app.aggro_clean_switch.grid(row=0, column=0, sticky="w", pady=(0, 5))

        self.app.process_button = ctk.CTkButton(process_btn_frame, text="Process Text File", command=self.app.process_file_content, text_color="black")
        self.app.process_button.grid(row=1, column=0, sticky="ew")

        # --- TEMPLATES ---
        template_frame = ctk.CTkFrame(self, fg_color=self.app.colors["tab_bg"])
        template_frame.pack(fill="x", padx=10, pady=(10,5), ipady=5)
        template_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(template_frame, text="Generation Templates", font=ctk.CTkFont(weight="bold"), text_color=self.app.text_color).grid(row=0, column=0, columnspan=2, pady=(5,0), padx=10, sticky="w")
        self.app.template_option_menu = ctk.CTkOptionMenu(template_frame, variable=self.app.selected_template_str, values=["No templates found"], text_color="black")
        self.app.template_option_menu.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        ctk.CTkButton(template_frame, text="Load", command=self.app.load_generation_template, text_color="black", width=70).grid(row=1, column=1, padx=(0,10), pady=5)

        # --- KEY PARAMETERS DISPLAY ---
        key_params_frame = ctk.CTkFrame(self, fg_color=self.app.colors["tab_bg"])
        key_params_frame.pack(fill="x", padx=10, pady=5, ipady=5)
        key_params_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(key_params_frame, text="Key Parameters (Loaded)", font=ctk.CTkFont(weight="bold"), text_color=self.app.text_color).grid(row=0, column=0, columnspan=2, pady=(5,5), padx=10, sticky="w")
        
        ctk.CTkLabel(key_params_frame, text="Reference:", text_color=self.app.text_color).grid(row=1, column=0, padx=10, pady=2, sticky="w")
        ref_val_label = ctk.CTkLabel(key_params_frame, textvariable=self.app.ref_audio_path_display, text_color="gray50", anchor="w", wraplength=250)
        ref_val_label.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        
        ctk.CTkLabel(key_params_frame, text="Exaggeration:", text_color=self.app.text_color).grid(row=2, column=0, padx=10, pady=2, sticky="w")
        ctk.CTkLabel(key_params_frame, textvariable=self.app.exaggeration, text_color="gray50", anchor="w").grid(row=2, column=1, padx=5, pady=2, sticky="ew")
        
        ctk.CTkLabel(key_params_frame, text="Temperature:", text_color=self.app.text_color).grid(row=3, column=0, padx=10, pady=2, sticky="w")
        ctk.CTkLabel(key_params_frame, textvariable=self.app.temperature, text_color="gray50", anchor="w").grid(row=3, column=1, padx=5, pady=2, sticky="ew")
        
        ctk.CTkButton(key_params_frame, text="Edit All Parameters...", command=lambda: self.app.switch_to_tab(1), text_color="black").grid(row=4, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew")

        # --- MAIN CONTROLS ---
        ctk.CTkLabel(self, text="Main Controls", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.app.text_color).pack(pady=(10, 5), anchor="w", padx=10)
        
        self.app.auto_assemble_checkbox = ctk.CTkCheckBox(self, text="Re-Assemble After Full Run", variable=self.app.auto_assemble_after_run, text_color=self.app.text_color)
        self.app.auto_assemble_checkbox.pack(pady=(0, 5), padx=10, anchor="w")

        # New Auto-Regen Checkbox (Main)
        self.app.auto_regen_main_checkbox = ctk.CTkCheckBox(self, text="Continue to Regenerate until all files pass", variable=self.app.auto_regen_main, text_color=self.app.text_color)
        self.app.auto_regen_main_checkbox.pack(pady=(0, 5), padx=10, anchor="w")
        
        # Dual-GPU Checkbox (only show if 2+ GPUs detected)
        if self.app.gpu_count >= 2:
            self.app.dual_gpu_checkbox = ctk.CTkCheckBox(self, text=f"Use Both GPUs ({self.app.gpu_count} detected)", variable=self.app.use_dual_gpu, text_color=self.app.text_color)
            self.app.dual_gpu_checkbox.pack(pady=(0, 5), padx=10, anchor="w")

        self.app.start_stop_button = ctk.CTkButton(self, text="Start Generation", command=self.app.toggle_generation_main, height=40, font=ctk.CTkFont(size=14, weight="bold"), text_color="black")
        self.app.start_stop_button.pack(fill="x", padx=10, pady=5)
        self.app.progress_bar = ctk.CTkProgressBar(self, progress_color="#3A7EBF"); self.app.progress_bar.pack(fill="x", padx=10, pady=(10,0)); self.app.progress_bar.set(0)
        self.app.progress_label = ctk.CTkLabel(self, text="0/0 (0.00%)", text_color=self.app.text_color); self.app.progress_label.pack()

        # --- SYSTEM CHECK ---
        sys_check_frame = ctk.CTkFrame(self, fg_color=self.app.colors["tab_bg"]); sys_check_frame.pack(fill="x", padx=10, pady=(20, 5), ipady=5)
        ctk.CTkLabel(sys_check_frame, text="System Check", font=ctk.CTkFont(weight="bold"), text_color=self.app.text_color).pack()
        ctk.CTkLabel(sys_check_frame, text=f"FFmpeg: {'Found' if self.app.deps.ffmpeg_ok else 'Not Found'}", text_color="green" if self.app.deps.ffmpeg_ok else "#A40000").pack(anchor="w", padx=10)
        ctk.CTkLabel(sys_check_frame, text=f"auto-editor: {'Found' if self.app.deps.auto_editor_ok else 'Not Found'}", text_color="green" if self.app.deps.auto_editor_ok else "#A40000").pack(anchor="w", padx=10)