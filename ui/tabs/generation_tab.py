# ui/tabs/generation_tab.py
import customtkinter as ctk
from tkinter import filedialog
from CTkToolTip import CTkToolTip
import sys
from pathlib import Path

# Add parent directory to path for component imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from components.labeled_slider import LabeledSlider

class GenerationTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance
        self.text_color = self.app.text_color

        self.grid_columnconfigure(0, weight=1)
        
        # Header
        ctk.CTkLabel(self, text="TTS Generation Parameters", 
                    font=ctk.CTkFont(size=16, weight="bold"), 
                    text_color=self.text_color).grid(row=0, column=0, pady=10, padx=10, sticky="w")
        
        row = 1
        
        # Reference Audio
        ctk.CTkLabel(self, text="Reference Audio:", text_color=self.text_color).grid(row=row, column=0, padx=10, pady=5, sticky="w")
        ref_entry_frame = ctk.CTkFrame(self, fg_color="transparent")
        ref_entry_frame.grid(row=row, column=0, padx=10, pady=5, sticky="ew")
        ref_entry_frame.grid_columnconfigure(0, weight=1)
        ref_entry = ctk.CTkEntry(ref_entry_frame, textvariable=self.app.ref_audio_path, text_color=self.text_color)
        ref_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(ref_entry_frame, text="Browse...", width=80, 
                     command=lambda: self.app.ref_audio_path.set(
                         filedialog.askopenfilename(filetypes=[("Audio Files", "*.wav")])
                     )).grid(row=0, column=1)
        CTkToolTip(ref_entry, "Path to the WAV file to be used for voice cloning.", delay=0.2)
        row += 1
        
        # Spacer
        ctk.CTkFrame(self, fg_color="transparent", height=15).grid(row=row, column=0); row += 1
        
        # --- SLIDER CONTROLS ---
        
        # Exaggeration Slider
        exag_slider = LabeledSlider(
            self, 
            label_text="Exaggeration:",
            variable=self.app.exaggeration,
            from_value=0.0,
            to_value=1.0,
            left_label="Monotone",
            right_label="Expressive",
            tooltip="Emotional intensity. 0.0 = flat/monotone, 0.5 = neutral, 1.0 = very expressive",
            number_of_steps=100,
            text_color=self.text_color
        )
        exag_slider.grid(row=row, column=0, padx=10, pady=8, sticky="ew"); row += 1
        
        # CFG Weight Slider
        cfg_slider = LabeledSlider(
            self,
            label_text="Voice Similarity:",
            variable=self.app.cfg_weight,
            from_value=0.0,
            to_value=1.0,
            left_label="Creative",
            right_label="Match Reference",
            tooltip="How closely to match the reference voice. Higher = stronger accent/tone from reference. Lower = more variation.",
            number_of_steps=100,
            text_color=self.text_color
        )
        cfg_slider.grid(row=row, column=0, padx=10, pady=8, sticky="ew"); row += 1
        
        # Temperature Slider
        temp_slider = LabeledSlider(
            self,
            label_text="Temperature:",
            variable=self.app.temperature,
            from_value=0.5,
            to_value=1.0,
            left_label="Consistent",
            right_label="Varied",
            tooltip="Creativity/randomness. Lower = consistent/robotic, Higher = varied/natural.",
            number_of_steps=50,
            text_color=self.text_color
        )
        temp_slider.grid(row=row, column=0, padx=10, pady=8, sticky="ew"); row += 1
        
        # Speed Slider
        speed_slider = LabeledSlider(
            self,
            label_text="Speed:",
            variable=self.app.speed,
            from_value=0.5,
            to_value=2.0,
            left_label="0.5× Slower",
            right_label="2× Faster",
            tooltip="Speaking rate. 0.5 = half speed, 1.0 = normal, 2.0 = double speed. Uses FFmpeg for high-quality time-stretching.",
            number_of_steps=150,
            text_color=self.text_color
        )
        speed_slider.grid(row=row, column=0, padx=10, pady=8, sticky="ew"); row += 1
        
        # Spacer
        ctk.CTkFrame(self, fg_color="transparent", height=15).grid(row=row, column=0); row += 1
        
        # Generation Order
        order_frame = ctk.CTkFrame(self, fg_color="transparent")
        order_frame.grid(row=row, column=0, padx=10, pady=5, sticky="ew")
        order_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(order_frame, text="Generation Order:", text_color=self.text_color).grid(row=0, column=0, padx=(0, 10), sticky="w")
        order_menu = ctk.CTkOptionMenu(order_frame, variable=self.app.generation_order, 
                                       values=["Fastest First", "In Order"], text_color="black")
        order_menu.grid(row=0, column=1, sticky="ew")
        CTkToolTip(order_menu, message="'Fastest First' prioritizes long chunks for efficient GPU use.\n'In Order' generates sequentially so you can listen sooner.", delay=0.2)
        row += 1

        # Items Per Page
        page_size_frame = ctk.CTkFrame(self, fg_color="transparent")
        page_size_frame.grid(row=row, column=0, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(page_size_frame, text="Items Per Page:", text_color=self.text_color).pack(side="left", padx=(0, 10))
        
        page_size_entry = ctk.CTkEntry(page_size_frame, textvariable=self.app.items_per_page_str, width=60, text_color=self.text_color)
        page_size_entry.pack(side="left", padx=5)
        page_size_entry.bind("<Return>", lambda event: self.app.playlist_frame.refresh_view())
        CTkToolTip(page_size_entry, message="Set custom number of items per page and press Enter to apply.")

        page_size_options = ["15", "25", "50", "100", "200"]
        page_size_dropdown = ctk.CTkOptionMenu(page_size_frame, variable=self.app.items_per_page_str,
                                               values=page_size_options,
                                               command=lambda _: self.app.playlist_frame.refresh_view(),
                                               text_color="black", width=80)
        page_size_dropdown.pack(side="left")
        CTkToolTip(page_size_dropdown, message="Select the number of text chunks to display per page in the playlist.")
        row += 1
        
        # Spacer
        ctk.CTkFrame(self, fg_color="transparent", height=20).grid(row=row, column=0); row += 1
        
        # --- ADVANCED SETTINGS (Collapsible) ---
        advanced_label = ctk.CTkLabel(self, text="▼ Advanced Settings", 
                                     font=ctk.CTkFont(size=13, weight="bold"),
                                     text_color=self.text_color, cursor="hand2")
        advanced_label.grid(row=row, column=0, padx=10, pady=5, sticky="w")
        row += 1
        
        # Advanced settings frame
        self.advanced_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.advanced_frame.grid(row=row, column=0, padx=20, pady=5, sticky="ew")
        self.advanced_frame.grid_columnconfigure(1, weight=1)
        
        adv_row = 0
        def add_advanced_entry(label, var, tooltip):
            nonlocal adv_row
            ctk.CTkLabel(self.advanced_frame, text=label, text_color=self.text_color).grid(row=adv_row, column=0, padx=5, pady=3, sticky="w")
            entry = ctk.CTkEntry(self.advanced_frame, textvariable=var, text_color=self.text_color, width=100)
            entry.grid(row=adv_row, column=1, padx=5, pady=3, sticky="w")
            CTkToolTip(entry, message=tooltip, delay=0.2)
            adv_row += 1
        
        add_advanced_entry("Target Devices:", self.app.target_gpus_str, "Comma-separated list of devices (e.g., cuda:0,cuda:1,cpu).")
        add_advanced_entry("# of Full Outputs:", self.app.num_full_outputs_str, "How many complete audiobooks to generate (each with a different master seed if seed=0).")
        add_advanced_entry("Master Seed (0=random):", self.app.master_seed_str, "Set a seed for reproducible results. Set to 0 for random.")
        add_advanced_entry("Candidates per Chunk:", self.app.num_candidates_str, "Number of audio options to generate for each text chunk before picking the best one.")
        add_advanced_entry("ASR Max Retries:", self.app.max_attempts_str, "If ASR fails, how many times to retry generating a candidate.")
        add_advanced_entry("ASR Threshold:", self.app.asr_threshold_str, "Similarity score (0.0 to 1.0) required for ASR validation to pass.")
        
        ctk.CTkSwitch(self.advanced_frame, text="Bypass ASR Validation", variable=self.app.asr_validation_enabled, 
                     onvalue=False, offvalue=True, text_color=self.text_color).grid(row=adv_row, column=0, columnspan=2, pady=3, sticky="w", padx=5)
        adv_row += 1
        ctk.CTkSwitch(self.advanced_frame, text="Disable Perth Watermark", variable=self.app.disable_watermark, 
                     text_color=self.text_color).grid(row=adv_row, column=0, columnspan=2, pady=3, sticky="w", padx=5)
        
        row += 1
        
        # Spacer
        ctk.CTkFrame(self, fg_color="transparent", height=20).grid(row=row, column=0); row += 1
        
        # Save Template Button
        ctk.CTkButton(self, text="💾 Save as Template...", command=self.app.save_generation_template, 
                     text_color="black", height=35).grid(row=row, column=0, padx=10, pady=(10, 10), sticky="ew")