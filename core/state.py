from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

@dataclass
class GenerationSettings:
    """Holds all generation-related settings."""
    exaggeration: float = 0.5
    cfg_weight: float = 0.7
    temperature: float = 0.8
    speed: float = 1.0
    items_per_page: int = 15
    target_gpus: str = "cuda:0"
    num_full_outputs: int = 1
    master_seed: int = 0
    num_candidates: int = 1
    max_attempts: int = 3
    
    # ASR Settings
    asr_validation_enabled: bool = True
    asr_threshold: float = 0.85
    
    # Processing Settings
    disable_watermark: bool = True
    chunking_enabled: bool = True
    max_chunk_chars: int = 290
    silence_duration: int = 250
    norm_enabled: bool = False
    silence_removal_enabled: bool = False
    norm_level: float = -23.0
    silence_threshold: float = 0.04
    silent_speed: float = 9999
    
    # TTS Engine
    tts_engine: str = "chatterbox"
    
    # Voice Effects
    pitch_shift: float = 0.0
    timbre_shift: float = 0.0
    gruffness: float = 0.0

@dataclass
class AppState:
    """
    Central application state.
    Serves as the Single Source of Truth, independent of the UI framework.
    """
    # Session Data
    session_name: str = ""
    source_file_path: str = ""
    sentences: List[Dict[str, Any]] = field(default_factory=list)
    
    # Reference Audio
    ref_audio_path: str = ""
    
    # Settings
    settings: GenerationSettings = field(default_factory=GenerationSettings)
    
    # Runtime State
    is_playing: bool = False
    current_playing_index: int = -1
    generation_active: bool = False
    
    def update_settings(self, **kwargs):
        """Update settings from a dictionary."""
        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
