# ui/controls_frame.py
import customtkinter as ctk

class CollapsibleFrame(ctk.CTkFrame):
    """A collapsible frame widget for customtkinter."""
    def __init__(self, master, text="", text_color="#000000", start_open=True, **kwargs):
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)

        self.is_open = start_open
        self.header_text = text

        self.header_button = ctk.CTkButton(self, text="", command=self.toggle,
                                           fg_color="transparent", text_color=text_color,
                                           hover=False, anchor="w", font=ctk.CTkFont(weight="bold"))
        self.header_button.grid(row=0, column=0, sticky="ew", padx=5)

        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        
        self.update_state()

    def toggle(self):
        self.is_open = not self.is_open
        self.update_state()
    
    def update_state(self):
        if self.is_open:
            self.content_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))
            self.header_button.configure(text=f"−  {self.header_text}") # Using minus sign
        else:
            self.content_frame.grid_forget()
            self.header_button.configure(text=f"+ {self.header_text}")

    def get_content_frame(self):
        return self.content_frame

class ControlsFrame(ctk.CTkFrame):
    """The entire control panel for the playlist, with collapsible sections."""
    def __init__(self, master, app_instance, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app_instance
        
        self.grid_columnconfigure(0, weight=1)
        
        button_kwargs = {"text_color": "black"}
        collapsible_kwargs = {"fg_color": self.app.colors["tab_bg"], "text_color": self.app.text_color}

        # --- Group 1: Playback & Navigation ---
        playback_collapsible = CollapsibleFrame(self, text="Playback & Navigation", start_open=True, **collapsible_kwargs)
        playback_collapsible.pack(fill="x", expand=True, padx=5, pady=(0, 3))
        playback_frame = playback_collapsible.get_content_frame()
        playback_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkButton(playback_frame, text="▶ Play", command=self.app.play_selected_sentence, **button_kwargs).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(playback_frame, text="■ Stop", command=self.app.stop_playback, **button_kwargs).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(playback_frame, text="▶ Play From", command=self.app.play_from_selection, **button_kwargs).grid(row=0, column=2, columnspan=2, padx=2, pady=2, sticky="ew")

        ctk.CTkButton(playback_frame, text="▲ Move Up", command=lambda: self.app.move_selected_items(-1), **button_kwargs).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(playback_frame, text="▼ Move Down", command=lambda: self.app.move_selected_items(1), **button_kwargs).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(playback_frame, text="◄ Prev Error", command=lambda: self.app.find_next_item(-1, 'failed'), **button_kwargs).grid(row=1, column=2, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(playback_frame, text="Next Error ►", command=lambda: self.app.find_next_item(1, 'failed'), **button_kwargs).grid(row=1, column=3, padx=2, pady=2, sticky="ew")
        
        # Search functionality
        search_frame = ctk.CTkFrame(playback_frame, fg_color="transparent")
        search_frame.grid(row=2, column=0, columnspan=4, padx=5, pady=(10, 5), sticky="ew")
        search_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(search_frame, text="🔍", font=ctk.CTkFont(size=16)).grid(row=0, column=0, padx=(0, 5))
        self.app.search_entry = ctk.CTkEntry(search_frame, placeholder_text="Search text...")
        self.app.search_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self.app.search_entry.bind("<Return>", lambda e: self.app.search_text())
        
        self.app.search_prev_btn = ctk.CTkButton(search_frame, text="◄", width=30, command=self.app.search_prev, state="disabled")
        self.app.search_prev_btn.grid(row=0, column=2, padx=2)
        
        self.app.search_next_btn = ctk.CTkButton(search_frame, text="►", width=30, command=self.app.search_next, state="disabled")
        self.app.search_next_btn.grid(row=0, column=3, padx=2)
        
        self.app.search_match_label = ctk.CTkLabel(search_frame, text="0/0", width=50, text_color=self.app.text_color)
        self.app.search_match_label.grid(row=0, column=4, padx=(5, 0))

        # --- Group 2: Chunk Editing & Status ---
        editing_collapsible = CollapsibleFrame(self, text="Chunk Editing & Status", start_open=False, **collapsible_kwargs)
        editing_collapsible.pack(fill="x", expand=True, padx=5, pady=(0, 3))
        editing_frame = editing_collapsible.get_content_frame()
        editing_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        ctk.CTkButton(editing_frame, text="✎ Edit", command=self.app.edit_selected_sentence, **button_kwargs).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(editing_frame, text="➗ Split", command=self.app.split_selected_chunk, **button_kwargs).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(editing_frame, text="➕ Insert Text", command=self.app.insert_text_block, **button_kwargs).grid(row=0, column=2, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(editing_frame, text="⏸ Insert Pause", command=self.app.insert_pause, **button_kwargs).grid(row=0, column=3, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(editing_frame, text="📑 Insert Chapter", command=self.app.insert_chapter_marker, **button_kwargs).grid(row=0, column=4, padx=2, pady=2, sticky="ew")

        ctk.CTkButton(editing_frame, text="M Mark", command=self.app.mark_current_sentence, **button_kwargs).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(editing_frame, text="✓ Mark Passed", command=self.app.mark_as_passed, fg_color="#2ECC71", hover_color="#27AE60", **button_kwargs).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(editing_frame, text="🔄 Reset Generation", command=self.app.reset_all_generation_status, fg_color="#C0392B", hover_color="#A93226", text_color="white").grid(row=1, column=2, columnspan=2, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(editing_frame, text="❌ Delete", command=self.app.delete_selected_blocks, fg_color="#E59866", hover_color="#D35400", **button_kwargs).grid(row=1, column=4, padx=2, pady=2, sticky="ew")

        # --- Group 3: Batch Fix & Regeneration ---
        fixit_collapsible = CollapsibleFrame(self, text="Batch Fix & Regeneration", start_open=False, **collapsible_kwargs)
        fixit_collapsible.pack(fill="x", expand=True, padx=5, pady=(0, 3))
        fixit_frame = fixit_collapsible.get_content_frame()
        fixit_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        ctk.CTkCheckBox(fixit_frame, text="Apply Batch Fix to ALL Failed Chunks", variable=self.app.apply_fix_to_all_failed, text_color=self.app.text_color).grid(row=0, column=0, columnspan=3, padx=10, pady=(5, 2), sticky="w")
        ctk.CTkButton(fixit_frame, text="Merge Failed Down", command=self.app.merge_failed_down, **button_kwargs).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(fixit_frame, text="Clean Special Chars", command=self.app.clean_special_chars_in_selected, **button_kwargs).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(fixit_frame, text="Filter Non-English", command=self.app.filter_non_dict_words_in_selected, **button_kwargs).grid(row=1, column=2, padx=2, pady=2, sticky="ew")

        ctk.CTkButton(fixit_frame, text="Split All Failed", command=self.app.split_all_failed_chunks, **button_kwargs).grid(row=2, column=0, columnspan=3, padx=5, pady=2, sticky="ew")

        # Regenerate button and auto-loop checkbox on same row
        ctk.CTkButton(fixit_frame, text="↻ Regenerate Marked", command=self.app.regenerate_marked_sentences, fg_color="#A40000", hover_color="#800000", text_color="white").grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        self.app.auto_regen_sub_checkbox = ctk.CTkCheckBox(fixit_frame, text="Auto-loop", variable=self.app.auto_regen_sub, text_color=self.app.text_color)
        self.app.auto_regen_sub_checkbox.grid(row=3, column=2, padx=5, pady=5, sticky="w")
        
        self.app.reassemble_after_regen_checkbox = ctk.CTkCheckBox(fixit_frame, text="Re-Assemble Audiobook After Regeneration", variable=self.app.reassemble_after_regen, text_color=self.app.text_color)
        self.app.reassemble_after_regen_checkbox.grid(row=4, column=0, columnspan=3, padx=10, pady=(0,5), sticky="w")