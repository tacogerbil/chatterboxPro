# ui/tabs/advanced_tab.py
import customtkinter as ctk

class AdvancedTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance
        self.text_color = self.app.text_color

        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="Advanced Text Operations (LLM)", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.text_color).pack(pady=10, anchor="w", padx=10)
        ctk.CTkSwitch(self, text="Enable LLM Pre-processing (Experimental / Not Implemented)", variable=self.app.llm_enabled, state="disabled", text_color=self.text_color).pack(anchor="w", padx=10, pady=5)
        ctk.CTkLabel(self, text="LLM API URL (OpenAI compatible):", text_color=self.text_color).pack(anchor="w", padx=10)
        ctk.CTkEntry(self, textvariable=self.app.llm_api_url, text_color=self.text_color).pack(fill="x", padx=10)
        ctk.CTkLabel(self, text="LLM System Prompt:", text_color=self.text_color).pack(anchor="w", padx=10, pady=(10,0))
        prompt_textbox = ctk.CTkTextbox(self, height=150, text_color=self.text_color)
        prompt_textbox.insert("1.0", "You are an assistant that corrects spelling and grammar in a given text without altering its original meaning or structure. Output only the corrected text.")
        prompt_textbox.pack(fill="both", expand=True, padx=10, pady=5)