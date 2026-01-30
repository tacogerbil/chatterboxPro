# ui/tabs/finalize_tab.py
import customtkinter as ctk

class FinalizeTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance
        self.text_color = self.app.text_color

        self.pack(fill="both", expand=True)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="Audiobook Assembly & Finalization", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.text_color).pack(pady=10, anchor="w", padx=10)

        ctk.CTkSwitch(self, text="Enable Smart Chunking", variable=self.app.chunking_enabled, text_color=self.text_color).pack(anchor="w", padx=10, pady=5)

        chunk_frame = ctk.CTkFrame(self, fg_color="transparent"); chunk_frame.pack(fill="x", padx=10)
        ctk.CTkLabel(chunk_frame, text="Max Chars per Chunk:", text_color=self.text_color).pack(side="left")
        ctk.CTkEntry(chunk_frame, textvariable=self.app.max_chunk_chars_str, width=80, text_color=self.text_color).pack(side="left", padx=5)

        silence_frame = ctk.CTkFrame(self, fg_color="transparent"); silence_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(silence_frame, text="Silence Between Chunks (ms):", text_color=self.text_color).pack(side="left")
        ctk.CTkEntry(silence_frame, textvariable=self.app.silence_duration_str, width=80, text_color=self.text_color).pack(side="left", padx=5)

        norm_frame = ctk.CTkFrame(self, fg_color=self.app.colors["tab_bg"]); norm_frame.pack(fill="x", padx=10, pady=10, ipady=5)
        self.norm_switch = ctk.CTkSwitch(norm_frame, text="Enable Audio Normalization (EBU R128)", variable=self.app.norm_enabled, state="normal" if self.app.deps.ffmpeg_ok else "disabled", text_color=self.text_color)
        self.norm_switch.pack(anchor="w", padx=10, pady=(10,5))
        norm_level_frame = ctk.CTkFrame(norm_frame, fg_color="transparent"); norm_level_frame.pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkLabel(norm_level_frame, text="Target Loudness (LUFS):", text_color=self.text_color).pack(side="left")
        ctk.CTkEntry(norm_level_frame, textvariable=self.app.norm_level_str, width=80, text_color=self.text_color).pack(side="left", padx=5)

        silence_removal_frame = ctk.CTkFrame(self, fg_color=self.app.colors["tab_bg"]); silence_removal_frame.pack(fill="x", padx=10, pady=10, ipady=5)
        self.silence_switch = ctk.CTkSwitch(silence_removal_frame, text="Enable Silence Removal (auto-editor)", variable=self.app.silence_removal_enabled, state="normal" if self.app.deps.auto_editor_ok else "disabled", text_color=self.text_color)
        self.silence_switch.pack(anchor="w", padx=10, pady=(10,5))
        
        # --- NEW Silence Removal Controls ---
        sr_controls_frame = ctk.CTkFrame(silence_removal_frame, fg_color="transparent")
        sr_controls_frame.pack(fill="x", padx=10, pady=(0, 10))
        sr_controls_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(sr_controls_frame, text="Silent Threshold:", text_color=self.text_color).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ctk.CTkEntry(sr_controls_frame, textvariable=self.app.silence_threshold, width=80, text_color=self.text_color).grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        ctk.CTkLabel(sr_controls_frame, text="Silent Speed:", text_color=self.text_color).grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ctk.CTkEntry(sr_controls_frame, textvariable=self.app.silent_speed_str, width=80, text_color=self.text_color).grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ctk.CTkLabel(sr_controls_frame, text="Frame Margin:", text_color=self.text_color).grid(row=2, column=0, sticky="w", padx=5, pady=2)
        ctk.CTkEntry(sr_controls_frame, textvariable=self.app.frame_margin_str, width=80, text_color=self.text_color).grid(row=2, column=1, sticky="w", padx=5, pady=2)

        metadata_frame = ctk.CTkFrame(self, fg_color=self.app.colors["tab_bg"])
        metadata_frame.pack(fill="x", padx=10, pady=10, ipady=5)
        metadata_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(metadata_frame, text="Audio File Metadata", font=ctk.CTkFont(weight="bold"), text_color=self.text_color).grid(row=0, column=0, columnspan=2, pady=(5,5), padx=10, sticky="w")
        
        ctk.CTkLabel(metadata_frame, text="Artist:", text_color=self.text_color).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkEntry(metadata_frame, textvariable=self.app.metadata_artist_str, text_color=self.text_color).grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(metadata_frame, text="Album/Series:", text_color=self.text_color).grid(row=2, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkEntry(metadata_frame, textvariable=self.app.metadata_album_str, placeholder_text="Defaults to session name", text_color=self.text_color).grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(metadata_frame, text="Book Title:", text_color=self.text_color).grid(row=3, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkEntry(metadata_frame, textvariable=self.app.metadata_title_str, placeholder_text="Defaults to session name", text_color=self.text_color).grid(row=3, column=1, padx=10, pady=5, sticky="ew")

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=(20, 10))
        button_frame.grid_columnconfigure((0,1), weight=1)

        self.assemble_button = ctk.CTkButton(button_frame, text="Assemble as Single File", command=self.app.start_assembly_in_background, height=40, font=ctk.CTkFont(size=14, weight="bold"), fg_color="#1E8449", hover_color="#145A32", text_color="white")
        self.assemble_button.grid(row=0, column=0, padx=5, sticky="ew")
        
        self.export_button = ctk.CTkButton(button_frame, text="Export by Chapter...", command=self.app.start_chapter_export_in_background, height=40, font=ctk.CTkFont(size=14, weight="bold"), text_color="black")
        self.export_button.grid(row=0, column=1, padx=5, sticky="ew")

        self.assembly_buttons = [self.assemble_button, self.export_button]