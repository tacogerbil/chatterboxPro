# ui/tabs/generation_tab.py
import customtkinter as ctk
from tkinter import filedialog
from CTkToolTip import CTkToolTip

class GenerationTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance
        self.text_color = self.app.text_color

        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text="TTS Generation Parameters", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.text_color).grid(row=0, column=0, columnspan=4, pady=10, padx=10, sticky="w")
        
        row = 1
        
        # Updated helper functions to include recommendation text
        def add_entry(label, var, tooltip, recommendation=""):
            nonlocal row
            ctk.CTkLabel(self, text=label, text_color=self.text_color).grid(row=row, column=0, padx=10, pady=5, sticky="w")
            entry = ctk.CTkEntry(self, textvariable=var, text_color=self.text_color, width=80)
            entry.grid(row=row, column=1, padx=(10, 5), pady=5, sticky="w")
            ctk.CTkLabel(self, text=recommendation, text_color="gray50", font=ctk.CTkFont(size=11)).grid(row=row, column=2, columnspan=2, padx=(0, 10), pady=5, sticky="w")
            CTkToolTip(entry, message=tooltip, delay=0.2)
            row += 1

        ctk.CTkLabel(self, text="Reference Audio:", text_color=self.text_color).grid(row=row, column=0, padx=10, pady=5, sticky="w")
        ref_entry_frame = ctk.CTkFrame(self, fg_color="transparent")
        ref_entry_frame.grid(row=row, column=1, columnspan=3, padx=10, pady=5, sticky="ew")
        ref_entry_frame.grid_columnconfigure(0, weight=1)
        ref_entry = ctk.CTkEntry(ref_entry_frame, textvariable=self.app.ref_audio_path, text_color=self.text_color)
        ref_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(ref_entry_frame, text="...", width=30, command=lambda: self.app.ref_audio_path.set(filedialog.askopenfilename(filetypes=[("Audio Files", "*.wav")]))).grid(row=0, column=1, padx=(5,0))
        row += 1
        CTkToolTip(ref_entry, "Path to the WAV file to be used for voice cloning.", delay=0.2)
        
        add_entry("Exaggeration:", self.app.exaggeration, "Controls the emotional intensity. 0.5 is neutral.", "(Range: 0.0 - 1.0)")
        add_entry("CFG Weight:", self.app.cfg_weight, "Classifier-Free Guidance. Higher values make the voice more like the reference.", "(Rec: 0.5 - 0.9)")
        add_entry("Temperature:", self.app.temperature, "Controls randomness. Higher values are more diverse, lower are more deterministic.", "(Rec: 0.7 - 0.9)")
        add_entry("Speed:", self.app.speed, "Adjusts the speaking rate. 1.0 is normal speed.", "(Range: 0.5 - 2.0)")

        ctk.CTkLabel(self, text="Generation Order:", text_color=self.text_color).grid(row=row, column=0, padx=10, pady=5, sticky="w")
        order_menu = ctk.CTkOptionMenu(self, variable=self.app.generation_order, values=["Fastest First", "In Order"], text_color="black")
        order_menu.grid(row=row, column=1, columnspan=3, padx=10, pady=5, sticky="ew")
        CTkToolTip(order_menu, message="'Fastest First' prioritizes long chunks for efficient GPU use.\n'In Order' generates sequentially so you can listen sooner.", delay=0.2)
        row += 1

        # --- Items Per Page Controls ---
        page_size_frame = ctk.CTkFrame(self, fg_color="transparent")
        page_size_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=5)

        ctk.CTkLabel(page_size_frame, text="Items Per Page:", text_color=self.text_color).pack(side="left", padx=(5,0))
        
        page_size_entry = ctk.CTkEntry(page_size_frame, textvariable=self.app.items_per_page_str, width=45, text_color=self.text_color)
        page_size_entry.pack(side="left", padx=5)
        page_size_entry.bind("<Return>", lambda event: self.app.playlist_frame.refresh_view())
        CTkToolTip(page_size_entry, message="Set custom number of items per page and press Enter to apply.")

        page_size_options = ["15", "25", "50", "100", "200"]
        page_size_dropdown = ctk.CTkOptionMenu(page_size_frame, variable=self.app.items_per_page_str,
                                               values=page_size_options,
                                               command=lambda _: self.app.playlist_frame.refresh_view(),
                                               text_color="black")
        page_size_dropdown.pack(side="left")
        CTkToolTip(page_size_dropdown, message="Select the number of text chunks to display per page in the playlist.")
        row += 1
        
        # Spacer to add some distance
        ctk.CTkFrame(self, fg_color="transparent", height=10).grid(row=row, column=0); row+=1

        add_entry("Target Devices:", self.app.target_gpus_str, "Comma-separated list of devices (e.g., cuda:0,cuda:1,cpu).")
        add_entry("# of Full Outputs:", self.app.num_full_outputs_str, "How many complete audiobooks to generate (each with a different master seed if seed=0).")
        add_entry("Master Seed (0=random):", self.app.master_seed_str, "Set a seed for reproducible results. Set to 0 for random.")
        add_entry("Candidates per Chunk:", self.app.num_candidates_str, "Number of audio options to generate for each text chunk before picking the best one.")
        add_entry("ASR Max Retries:", self.app.max_attempts_str, "If ASR fails, how many times to retry generating a candidate.")
        add_entry("ASR Acceptance Threshold:", self.app.asr_threshold_str, "Similarity score (0.0 to 1.0) required for ASR validation to pass.", "(Rec: 0.85)")
        
        ctk.CTkSwitch(self, text="Bypass ASR Validation", variable=self.app.asr_validation_enabled, onvalue=False, offvalue=True, text_color=self.text_color).grid(row=row, columnspan=3, pady=5, sticky="w", padx=10); row += 1
        ctk.CTkSwitch(self, text="Disable Perth Watermark", variable=self.app.disable_watermark, text_color=self.text_color).grid(row=row, columnspan=3, pady=5, sticky="w", padx=10); row += 1

        ctk.CTkButton(self, text="Save as Template...", command=self.app.save_generation_template, text_color="black").grid(row=row, column=0, columnspan=4, padx=10, pady=(20, 10), sticky="ew")