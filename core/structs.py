from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class WorkerTask:
    """
    Explicit contract for data passed to the TTS worker process.
    Follows MCCC Law 7 (Explicit Interfaces) and eliminates brittle tuple unpacking.
    """
    # Task Metadata
    task_index: int
    original_index: int
    sentence_number: int
    uuid: str
    session_name: str
    run_idx: int
    output_dir_str: str

    # Direct Inputs
    text_chunk: str
    ref_audio_path: Optional[str]

    # Execution Context
    device_str: str
    master_seed: int

    # Generation Parameters (Flattened or grouped)
    # Grouping them ensures we don't miss new settings added to GenerationSettings
    exaggeration: float
    temperature: float
    cfg_weight: float
    disable_watermark: bool
    num_candidates: int
    max_attempts: int
    bypass_asr: bool
    asr_threshold: float
    speed: float
    tts_engine: str
    
    # Audio Effects
    pitch_shift: float
    timbre_shift: float
    gruffness: float
    bass_boost: float
    treble_boost: float
    
    # Auto-Expression Settings (Phase 3 Quality Improvement)
    auto_expression_enabled: bool = False
    expression_sensitivity: float = 1.0
    
    # Optional Model Overrides
    model_path: Optional[str] = None

