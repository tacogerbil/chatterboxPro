# ui/components/labeled_slider.py
import customtkinter as ctk
from CTkToolTip import CTkToolTip

class LabeledSlider(ctk.CTkFrame):
    """
    Reusable slider component with:
    - Label on left
    - Slider in middle with contextual labels at each end
    - Entry box on right for manual input
    - Optional tooltip
    """
    def __init__(self, master, label_text, variable, from_value, to_value, 
                 left_label="", right_label="", tooltip="", 
                 number_of_steps=None, **kwargs):
        super().__init__(master, fg_color="transparent")
        
        self.variable = variable
        self.from_value = from_value
        self.to_value = to_value
        
        # Configure grid
        self.grid_columnconfigure(1, weight=1)  # Slider column expands
        
        # Main label (left side)
        main_label = ctk.CTkLabel(self, text=label_text, 
                                 text_color=kwargs.get('text_color', '#101010'))
        main_label.grid(row=0, column=0, padx=(0, 10), sticky="w")
        
        # Slider frame with contextual labels
        slider_frame = ctk.CTkFrame(self, fg_color="transparent")
        slider_frame.grid(row=0, column=1, sticky="ew", padx=5)
        slider_frame.grid_columnconfigure(1, weight=1)
        
        # Left contextual label
        if left_label:
            left_ctx_label = ctk.CTkLabel(slider_frame, text=left_label, 
                                         text_color="gray50", 
                                         font=ctk.CTkFont(size=10))
            left_ctx_label.grid(row=0, column=0, padx=(0, 5), sticky="w")
        
        # Slider
        self.slider = ctk.CTkSlider(
            slider_frame, 
            from_=from_value, 
            to=to_value,
            variable=variable,
            number_of_steps=number_of_steps,
            command=self._on_slider_change
        )
        self.slider.grid(row=0, column=1, sticky="ew")
        
        # Right contextual label
        if right_label:
            right_ctx_label = ctk.CTkLabel(slider_frame, text=right_label, 
                                          text_color="gray50", 
                                          font=ctk.CTkFont(size=10))
            right_ctx_label.grid(row=0, column=2, padx=(5, 0), sticky="e")
        
        # Entry box (right side) for manual input
        self.entry = ctk.CTkEntry(self, textvariable=variable, width=60,
                                 text_color=kwargs.get('text_color', '#101010'))
        self.entry.grid(row=0, column=2, padx=(5, 0))
        self.entry.bind("<Return>", self._on_entry_change)
        self.entry.bind("<FocusOut>", self._on_entry_change)
        
        # Tooltip (applied to both slider and entry)
        if tooltip:
            CTkToolTip(self.slider, message=tooltip, delay=0.2)
            CTkToolTip(self.entry, message=tooltip, delay=0.2)
    
    def _on_slider_change(self, value):
        """Update entry when slider moves."""
        # Round to 2 decimal places for display
        self.variable.set(round(float(value), 2))
    
    def _on_entry_change(self, event=None):
        """Validate and clamp entry input."""
        try:
            value = float(self.variable.get())
            # Clamp to valid range
            if value < self.from_value:
                value = self.from_value
            elif value > self.to_value:
                value = self.to_value
            self.variable.set(round(value, 2))
        except (ValueError, TypeError):
            # Reset to slider's current value if invalid
            self.variable.set(round(self.slider.get(), 2))
