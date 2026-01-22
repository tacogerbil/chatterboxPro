import customtkinter as ctk

class ChaptersTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance
        self.chapter_vars = [] # Store IntVar/BooleanVar for checkboxes
        self.found_chapters_indices = [] # Store tuples (real_index, item)

        # Grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        
        ctk.CTkLabel(header_frame, text="Detected Chapters", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.app.text_color).pack(side="left")
        
        # Header Buttons
        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.pack(side="right")
        
        ctk.CTkButton(btn_frame, text="Generate Selected", command=self.generate_selected_chapters, 
                      fg_color="#D35400", hover_color="#A04000", width=140).pack(side="right", padx=(10, 0))
        
        ctk.CTkButton(btn_frame, text="↻ Refresh List", command=self.refresh_chapters, width=100, text_color="black").pack(side="right", padx=5)

        # Selection Helpers
        sel_frame = ctk.CTkFrame(self, fg_color="transparent")
        sel_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))
        ctk.CTkButton(sel_frame, text="Select All", command=self.select_all, width=80, text_color="black", fg_color="gray").pack(side="left", padx=5)
        ctk.CTkButton(sel_frame, text="Deselect All", command=self.deselect_all, width=80, text_color="black", fg_color="gray").pack(side="left", padx=5)

        # Scrollable list area
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Chapters List")
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.scroll_frame.grid_columnconfigure(0, weight=0) # Checkbox
        self.scroll_frame.grid_columnconfigure(1, weight=1) # Name
        self.scroll_frame.grid_columnconfigure(2, weight=0) # Index
        self.scroll_frame.grid_columnconfigure(3, weight=0) # Jump Button

        # Initial load
        self.refresh_chapters()

    def refresh_chapters(self):
        # Clear existing
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.chapter_vars.clear()
        self.found_chapters_indices.clear()

        if not self.app.sentences:
            ctk.CTkLabel(self.scroll_frame, text="No text loaded.", text_color="gray").pack(pady=20)
            return

        for i, item in enumerate(self.app.sentences):
            if item.get('is_chapter_heading'):
                self.found_chapters_indices.append((i, item))

        if not self.found_chapters_indices:
            ctk.CTkLabel(self.scroll_frame, text="No chapters detected.\n\nUse 'Insert Chapter' in the Editing panel to mark them manually.", text_color="gray").pack(pady=20)
            return

        for idx, (real_index, item) in enumerate(self.found_chapters_indices):
            text = item.get('original_sentence', f'Chapter {idx+1}')
            if len(text) > 50: text = text[:47] + "..."
            
            # Checkbox
            var = ctk.BooleanVar(value=False)
            self.chapter_vars.append(var)
            
            ctk.CTkCheckBox(self.scroll_frame, text="", variable=var, width=24).grid(row=idx, column=0, padx=(5,0), pady=2)
            
            # Name
            ctk.CTkLabel(self.scroll_frame, text=f"{idx+1}. {text}", anchor="w", text_color=self.app.text_color).grid(row=idx, column=1, sticky="ew", padx=5, pady=2)
            
            # Index
            ctk.CTkLabel(self.scroll_frame, text=f"Idx: {real_index+1}", text_color="gray").grid(row=idx, column=2, padx=10, pady=2)
            
            # Jump Button
            ctk.CTkButton(self.scroll_frame, text="Jump To", width=80, text_color="black",
                          command=lambda i=real_index: self.jump_to_chapter(i)).grid(row=idx, column=3, padx=5, pady=2)
    
    def select_all(self):
        for var in self.chapter_vars: var.set(True)

    def deselect_all(self):
        for var in self.chapter_vars: var.set(False)

    def generate_selected_chapters(self):
        from tkinter import messagebox
        
        selected_indices = [i for i, var in enumerate(self.chapter_vars) if var.get()]
        if not selected_indices:
            messagebox.showinfo("Info", "No chapters selected for generation.")
            return

        if not messagebox.askyesno("Confirm Generation", f"Generate audio for {len(selected_indices)} selected chapter(s)?"):
            return

        # Calculate range of sentence indices
        indices_to_process = []
        
        for ch_idx in selected_indices:
            # Start is the index of the chapter heading
            start_real_index = self.found_chapters_indices[ch_idx][0]
            
            # End is the index of the next chapter heading, or the end of the list
            if ch_idx + 1 < len(self.found_chapters_indices):
                end_real_index = self.found_chapters_indices[ch_idx + 1][0]
            else:
                end_real_index = len(self.app.sentences)
                
            # Collect all indices in [start, end)
            indices_to_process.extend(range(start_real_index, end_real_index))
            
        # Ensure unique and sorted (though typical selection should be disjoint)
        indices_to_process = sorted(list(set(indices_to_process)))
        
        if not indices_to_process:
            messagebox.showerror("Error", "Selected chapters appear to be empty ranges.")
            return
            
        self.app.start_generation_orchestrator(indices_to_process)

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
