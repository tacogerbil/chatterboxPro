# ui/playlist.py
import tkinter as tk
import customtkinter as ctk
from CTkToolTip import CTkToolTip

class PlaylistFrame(ctk.CTkFrame):
    """The interactive playlist widget for displaying and managing text chunks."""
    def __init__(self, master, app_instance, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app_instance
        self.labels = []
        self.selected_indices = set()
        self.last_clicked_index = None
        self.current_page = 0
        
        self.chapter_font = ctk.CTkFont(size=14, weight="bold")
        self.normal_font = ctk.CTkFont(size=14)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=160)
        
        # --- Pagination ---
        pagination_frame = ctk.CTkFrame(self, fg_color="transparent")
        pagination_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        
        self.prev_button = ctk.CTkButton(pagination_frame, text="< Prev", command=self.prev_page, width=80, text_color="black")
        self.prev_button.pack(side="left", padx=5)
        
        self.page_label = ctk.CTkLabel(pagination_frame, text="Page 1/1", text_color=self.app.text_color)
        self.page_label.pack(side="left", expand=True)

        # --- NEW: Go To Page Entry ---
        self.page_entry = ctk.CTkEntry(pagination_frame, width=40, text_color=self.app.text_color)
        self.page_entry.pack(side="left", padx=5)
        self.page_entry.bind("<Return>", self.go_to_page)
        CTkToolTip(self.page_entry, message="Enter page number and press Enter")

        self.next_button = ctk.CTkButton(pagination_frame, text="Next >", command=self.next_page, width=80, text_color="black")
        self.next_button.pack(side="right", padx=5)

        # --- Playlist Scrollable Frame ---
        self.scrollable_frame = ctk.CTkScrollableFrame(self, label_text="Text Chunks", label_text_color=self.app.text_color)
        self.scrollable_frame.grid(row=1, column=0, sticky="nsew", padx=(5,0), pady=(0,5))

        # --- Statistics Panel ---
        self.stats_frame = ctk.CTkFrame(self, fg_color=self.app.colors["tab_bg"])
        self.stats_frame.grid(row=1, column=1, sticky="ns", padx=(2, 5), pady=(0,5))
        self.stats_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.stats_frame, text="Chunk Stats", font=ctk.CTkFont(weight="bold"), text_color=self.app.text_color).grid(row=0, column=0, columnspan=2, pady=5, padx=10, sticky="w")
        
        ctk.CTkLabel(self.stats_frame, text="Status:", text_color=self.app.text_color).grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self.status_val_label = ctk.CTkLabel(self.stats_frame, text="--", text_color="gray50", anchor="w")
        self.status_val_label.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        ctk.CTkLabel(self.stats_frame, text="Seed:", text_color=self.app.text_color).grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.seed_val_label = ctk.CTkLabel(self.stats_frame, text="--", text_color="gray50", anchor="w")
        self.seed_val_label.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        ctk.CTkLabel(self.stats_frame, text="ASR Match:", text_color=self.app.text_color).grid(row=3, column=0, sticky="w", padx=10, pady=2)
        self.asr_val_label = ctk.CTkLabel(self.stats_frame, text="--", text_color="gray50", anchor="w")
        self.asr_val_label.grid(row=3, column=1, sticky="ew", padx=5, pady=2)

    @property
    def items_per_page(self):
        return self.app.get_validated_int(self.app.items_per_page_str, 25)

    def refresh_view(self):
        """Refreshes the playlist view, typically after changing page size."""
        self.load_data(self.app.sentences, page_to_display=0)

    def load_data(self, sentences_data, page_to_display=0):
        self.app.sentences = sentences_data
        total_pages = (len(self.app.sentences) - 1) // self.items_per_page + 1 if self.app.sentences else 1
        self.current_page = min(page_to_display, max(0, total_pages - 1))
        self.last_clicked_index = None
        self.selected_indices.clear()
        self.display_page(self.current_page)
        self.update_stats_panel()

    def display_page(self, page_num):
        self.current_page = page_num
        for widget in self.scrollable_frame.winfo_children(): widget.destroy()
        self.labels.clear()

        start_index = self.current_page * self.items_per_page
        end_index = min((self.current_page + 1) * self.items_per_page, len(self.app.sentences))

        for i, s_data in enumerate(self.app.sentences[start_index:end_index]):
            global_index = start_index + i
            text = s_data.get("original_sentence", "")
            
            display_text = f"[{s_data.get('sentence_number', global_index+1)}] {text}"
            
            font = self.chapter_font if s_data.get("is_chapter_heading") else self.normal_font
            label = ctk.CTkLabel(self.scrollable_frame, text=display_text, wraplength=1000, justify="left", anchor="w", font=font)
            
            label.pack(fill="x", padx=5, pady=2)
            label.bind("<Button-1>", lambda e, index=global_index: self._on_label_click(e, index))
            label.bind("<Double-1>", lambda e, index=global_index: self.app.play_selected_sentence(index))
            try: CTkToolTip(label, message=text, delay=0.5)
            except Exception: pass
            self.labels.append(label)
        self.update_pagination_controls()
        self._update_all_visuals()

    def update_item(self, index):
        if index // self.items_per_page == self.current_page:
            local_index = index % self.items_per_page
            if local_index < len(self.labels):
                self._update_label_visual(index, self.labels[local_index])
        if index in self.selected_indices:
            self.update_stats_panel()

    def _update_label_visual(self, index, label):
        s_data = self.app.sentences[index]
        is_marked = s_data.get("marked", False)
        is_failed = s_data.get("tts_generated") == "failed"
        is_success = s_data.get("tts_generated") == "yes"
        is_chapter = s_data.get("is_chapter_heading", False)
        is_pause = s_data.get("is_pause", False)
        
        status_symbol = ""
        if is_pause:
            status_symbol = "⏸"
        elif s_data.get('tts_generated'):
            status_symbol = "✓" if is_success else "✗" if is_failed else "…"
        
        text = s_data.get("original_sentence", "")
        display_text = f"[{s_data.get('sentence_number', index+1)}] {status_symbol} {text}"

        font = self.chapter_font if is_chapter else self.normal_font
        label.configure(text=display_text, font=font)

        fg, text_color = "transparent", self.app.text_color
        
        if is_chapter: fg = self.app.colors["chapter"]
        elif is_pause: fg = "#D6EAF8"
        
        if index in self.selected_indices: fg = self.app.colors["selection"]
        elif is_marked: fg = self.app.colors["marked"]
        elif is_failed: fg, text_color = self.app.colors["failed"], "white"
        
        label.configure(fg_color=fg, text_color=text_color)

    def _update_all_visuals(self):
        start_index = self.current_page * self.items_per_page
        for i, label in enumerate(self.labels):
            self._update_label_visual(start_index + i, label)

    def update_pagination_controls(self):
        total_pages = (len(self.app.sentences) - 1) // self.items_per_page + 1 if self.app.sentences else 1
        self.page_label.configure(text=f"Page {self.current_page + 1} / {total_pages}")
        self.prev_button.configure(state="normal" if self.current_page > 0 else "disabled")
        self.next_button.configure(state="normal" if self.current_page < total_pages - 1 else "disabled")

    def prev_page(self):
        if self.current_page > 0:
            self.display_page(self.current_page - 1)

    def next_page(self):
        if self.current_page < ((len(self.app.sentences) - 1) // self.items_per_page):
            self.display_page(self.current_page + 1)

    def go_to_page(self, event=None):
        try:
            page_num = int(self.page_entry.get()) - 1
            total_pages = (len(self.app.sentences) - 1) // self.items_per_page + 1 if self.app.sentences else 1
            if 0 <= page_num < total_pages:
                self.display_page(page_num)
            else:
                # Optionally provide feedback for invalid page number
                self.page_entry.delete(0, 'end')
        except ValueError:
            # Handle non-integer input
            self.page_entry.delete(0, 'end')

    def _on_label_click(self, event, index):
        if event.state & 0x0004: # Ctrl+Click
            self.selected_indices.symmetric_difference_update({index})
        elif event.state & 0x0001 and self.last_clicked_index is not None and self.last_clicked_index != index: # Shift+Click
            start, end = sorted((self.last_clicked_index, index))
            self.selected_indices.update(range(start, end + 1))
        else: # Normal Click
            self.selected_indices = {index}
        self.last_clicked_index = index
        self._update_all_visuals()
        self.update_stats_panel()

    def update_stats_panel(self):
        if len(self.selected_indices) == 1:
            index = list(self.selected_indices)[0]
            s_data = self.app.sentences[index]
            
            status = s_data.get("tts_generated", "no")
            seed = s_data.get("generation_seed", "--")
            ratio = s_data.get("similarity_ratio")

            self.status_val_label.configure(text=status.capitalize())
            self.seed_val_label.configure(text=str(seed))

            if ratio is not None:
                self.asr_val_label.configure(text=f"{ratio:.2%}")
            else:
                self.asr_val_label.configure(text="N/A")

        else: # No selection or multiple selections
            self.status_val_label.configure(text="--")
            self.seed_val_label.configure(text="--")
            self.asr_val_label.configure(text="--")

    def get_selected_indices(self): return sorted(list(self.selected_indices))