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
    generation_order: str = "fastest" # "fastest" or "sequential"
    
    # ASR Settings
    asr_validation_enabled: bool = True
    asr_threshold: float = 0.98  # Raised from 0.85 for stricter quality control
    
    # Auto-Expression Settings (Optional Enhancement)
    auto_expression_enabled: bool = False
    expression_sensitivity: float = 1.0  # Multiplier for expression adjustments (0.5-2.0)
    
    # Processing Settings
    disable_watermark: bool = True
    chunking_enabled: bool = True
    max_chunk_chars: int = 400  # Increased from 290 for better Chatterbox prosody (Phase 2)
    silence_duration: int = 250
    chapter_buffer_before_ms: int = 1500 # Default before chapter
    chapter_buffer_after_ms: int = 2000 # Default after chapter
    norm_enabled: bool = True  # Enable EBU R128 normalization by default
    silence_removal_enabled: bool = False
    norm_level: float = -23.0
    silence_threshold: float = 0.04
    silent_speed: float = 9999
    frame_margin: int = 6
    
    # Metadata (For Export)
    metadata_title: str = ""
    metadata_artist: str = ""
    metadata_album: str = ""
    
    # TTS Engine
    tts_engine: str = "chatterbox"
    
    # Voice Effects
    pitch_shift: float = 0.0
    timbre_shift: float = 0.0
    gruffness: float = 0.0
    bass_boost: float = 0.0
    treble_boost: float = 0.0
    
    # Custom Model Paths
    model_path: Optional[str] = None

@dataclass
class AppState:
    """
    Central application state.
    Serves as the Single Source of Truth, independent of the UI framework.
    """
    # Session Data
    session_name: str = ""
    voice_name: str = "Custom / Unsaved" # Track loaded voice name
    source_file_path: str = ""
    sentences: List[Dict[str, Any]] = field(default_factory=list)
    is_session_loaded: bool = False # Safety flag to prevent overwriting during auto-save
    
    # Reference Audio
    ref_audio_path: str = ""
    
    # Settings
    settings: GenerationSettings = field(default_factory=GenerationSettings)
    
    # Runtime State
    is_playing: bool = False
    current_playing_index: int = -1
    generation_active: bool = False
    
    # UI State Persisted
    auto_regen_main: bool = False # For Chapters Tab "Auto-loop" logic
    auto_regen_sub: bool = False # For Batch Fix Logic
    auto_assemble_after_run: bool = False
    aggro_clean_on_parse: bool = False
    
    # UI Theme State (MCCC: Consolidated Config)
    theme_name: str = "dark_teal.xml"
    theme_invert: bool = False
    
    # Window State
    window_geometry_hex: str = ""
    
    # Global Engine Config
    model_path: Optional[str] = None
    
    # Progress Tracking (MCCC: Centralized Statistics)
    total_chunks: int = 0
    chunks_passed: int = 0
    chunks_failed: int = 0
    chunks_completed: int = 0
    generation_start_time: float = 0.0  # timestamp
    chunk_status: Dict[int, str] = field(default_factory=dict)  # {index: 'passed'|'failed'}
    
    # System Capabilities (MCCC: Hardware isolation)
    system_capabilities: Dict[str, Any] = field(default_factory=dict)
    
    def update_settings(self, **kwargs):
        """Update settings from a dictionary."""
        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
