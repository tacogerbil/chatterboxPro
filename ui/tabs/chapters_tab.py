import customtkinter as ctk

class ChaptersTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance
        
        # Grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        ctk.CTkLabel(header_frame, text="Detected Chapters", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.app.text_color).pack(side="left")
        ctk.CTkButton(header_frame, text="↻ Refresh List", command=self.refresh_chapters, width=100, text_color="black").pack(side="right")

        # Scrollable list area
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Chapters List")
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.scroll_frame.grid_columnconfigure(0, weight=1) # Name
        self.scroll_frame.grid_columnconfigure(1, weight=0) # Index
        self.scroll_frame.grid_columnconfigure(2, weight=0) # Jump Button

        # Initial load
        self.refresh_chapters()

    def refresh_chapters(self):
        # Clear existing
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not self.app.sentences:
            ctk.CTkLabel(self.scroll_frame, text="No text loaded.", text_color="gray").pack(pady=20)
            return

        chapters_found = []
        for i, item in enumerate(self.app.sentences):
            if item.get('is_chapter_heading'):
                chapters_found.append((i, item))

        if not chapters_found:
            ctk.CTkLabel(self.scroll_frame, text="No chapters detected.\n\nUse 'Insert Chapter' in the Editing panel to mark them manually.", text_color="gray").pack(pady=20)
            return

        for idx, (real_index, item) in enumerate(chapters_found):
            text = item.get('original_sentence', f'Chapter {idx+1}')
            # Truncate if long
            if len(text) > 50: text = text[:47] + "..."
            
            # Row Widgets
            ctk.CTkLabel(self.scroll_frame, text=f"{idx+1}. {text}", anchor="w", text_color=self.app.text_color).grid(row=idx, column=0, sticky="ew", padx=5, pady=2)
            ctk.CTkLabel(self.scroll_frame, text=f"Idx: {real_index+1}", text_color="gray").grid(row=idx, column=1, padx=10, pady=2)
            
            # Jump Button
            # We use a default arg in lambda to capture the current loop variable value
            ctk.CTkButton(self.scroll_frame, text="Jump To", width=80, text_color="black",
                          command=lambda i=real_index: self.jump_to_chapter(i)).grid(row=idx, column=2, padx=5, pady=2)

    def jump_to_chapter(self, index):
        # Calculate page
        items_per_page = self.app.playlist_frame.items_per_page
        target_page = index // items_per_page
        
        # Switch tab context to Playlist (which is always visible on right, but we want to ensure user attention)
        # We don't need to change tabs on the left, but we do need to update the playlist view
        if self.app.playlist_frame.current_page != target_page:
            self.app.playlist_frame.display_page(target_page)
            
        self.app.playlist_frame.selected_indices = {index}
        self.app.playlist_frame.last_clicked_index = index
        self.app.playlist_frame._update_all_visuals()
        self.app.playlist_frame.update_stats_panel()
