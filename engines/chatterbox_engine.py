# engines/chatterbox_engine.py
"""
Chatterbox TTS Engine Adapter.
Wraps the existing Chatterbox implementation to conform to BaseTTSEngine interface.
"""
import torch
from pathlib import Path
from typing import Dict, Any, Optional

from .base_engine import BaseTTSEngine
from chatterbox.tts import ChatterboxTTS
from huggingface_hub import hf_hub_download

REPO_ID = "ResembleAI/chatterbox"

# Files that MUST be present for a valid Chatterbox installation
_REQUIRED_FILES = ["ve.pt", "t3_cfg.pt", "s3gen.pt", "tokenizer.json"]
_OPTIONAL_FILES = ["conds.pt"]

# Fingerprint files that identify a WRONG engine living in the target folder.
_WRONG_ENGINE_MARKERS: Dict[str, list] = {
    "MOSS-TTS": ["modeling_moss_tts.py", "configuration_moss_tts.py"],
    "F5-TTS":   ["F5TTS_Base_train.yaml"],
    "XTTS":     ["config.json"],  # broad, only flagged when combined with below
}
# A definitive MOSS fingerprint (its Python module files never appear in Chatterbox)
_DEFINITIVE_WRONG_MARKERS = [
    "modeling_moss_tts.py",
    "configuration_moss_tts.py",
    "processing_moss_tts.py",
]


def _detect_wrong_engine(path: Path) -> Optional[str]:
    """
    Checks whether a directory contains model files from a different engine.

    Returns the engine name string if foreign files are detected, else None.
    
    """
    for marker in _DEFINITIVE_WRONG_MARKERS:
        if (path / marker).exists():
            return "MOSS-TTS"
    return None


def _download_to_dir(target_dir: Path) -> None:
    """
    Downloads Chatterbox model files directly into target_dir using hf_hub.

    Uses local_dir so files land flat in the user's chosen folder,
    not inside the HuggingFace cache hierarchy.
    

    Raises:
        RuntimeError: If any required file fails to download.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"[ChatterboxEngine] Downloading Chatterbox model to: {target_dir}")

    for fname in _REQUIRED_FILES + _OPTIONAL_FILES:
        try:
            hf_hub_download(
                repo_id=REPO_ID,
                filename=fname,
                local_dir=str(target_dir),
            )
            print(f"[ChatterboxEngine] ✓ {fname}")
        except Exception as e:
            if fname in _OPTIONAL_FILES:
                print(f"[ChatterboxEngine] Optional file '{fname}' not available: {e}")
            else:
                raise RuntimeError(
                    f"Failed to download required Chatterbox file '{fname}': {e}"
                )

    print(f"[ChatterboxEngine] Download complete → {target_dir}")


class ChatterboxEngine(BaseTTSEngine):
    """Adapter for Chatterbox TTS engine."""

    def __init__(self, device: str, model_path: str = None, **kwargs):
        super().__init__(device)
        self.model = None
        self.sr = 24000  # Chatterbox sample rate
        self.model_path = model_path or ""

    def _ensure_model_loaded(self) -> None:
        """
        Lazy-loads the Chatterbox model on first use.

        Load strategy (
          1. Custom path set
             a. Detect wrong engine files → raise immediately with clear message
             b. Required files present   → load from path
             c. Files absent             → download directly to path, then load
          2. No custom path → from_pretrained() (downloads to HF cache)
        """
        if self.model is not None:
            return

        if self.model_path:
            target = Path(self.model_path)

            # Gate 1: Wrong engine detection
            wrong = _detect_wrong_engine(target)
            if wrong:
                raise RuntimeError(
                    f"[ChatterboxEngine] Wrong model detected in '{target}'.\n"
                    f"Found {wrong} files. This folder belongs to a different engine.\n"
                    "Please choose an empty folder or a valid Chatterbox model directory."
                )

            # Gate 2: Files present → load directly
            if (target / "ve.pt").exists():
                print(f"[ChatterboxEngine] Loading from local path: {target}")
                self.model = ChatterboxTTS.from_local(str(target), self.device)

            # Gate 3: Files absent → download to custom path, then load
            else:
                print(f"[ChatterboxEngine] Model not found at '{target}'. Downloading...")
                _download_to_dir(target)
                self.model = ChatterboxTTS.from_local(str(target), self.device)

        else:
            # No custom path — use HuggingFace cache (default behaviour)
            print("[ChatterboxEngine] No custom path set. Loading from HF Hub (default cache)...")
            self.model = ChatterboxTTS.from_pretrained(self.device)

        self.sr = self.model.sr

    def generate(
        self, 
        text: str, 
        ref_audio_path: str,
        exaggeration: float = 0.5,
        temperature: float = 0.8,
        cfg_weight: float = 0.7,
        apply_watermark: bool = False,
        **kwargs
    ) -> torch.Tensor:
        """
        Generate audio using Chatterbox.
        
        Args:
            text: Text to synthesize
            ref_audio_path: Path to reference audio
            exaggeration: Emotional intensity (0.0-1.0)
            temperature: Randomness (0.5-1.0)
            cfg_weight: Voice similarity strength (0.0-1.0)
            apply_watermark: Whether to apply Perth watermark
        
        Returns:
            Audio tensor (1, samples)
        """
        self._ensure_model_loaded()
        
        # Prepare conditionals (this caches embeddings)
        self.model.prepare_conditionals(
            ref_audio_path, 
            exaggeration=exaggeration
        )
        
        # Generate audio
        # Upstream ChatterboxTTS.generate signature:
        # text, repetition_penalty, min_p, top_p, audio_prompt_path, exaggeration, cfg_weight, temperature
        wav_tensor = self.model.generate(
            text,
            audio_prompt_path=None,  # Already prepared via prepare_conditionals
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            temperature=temperature,
            apply_watermark=apply_watermark
        )
        
        return wav_tensor
    
    def prepare_reference(self, audio_path: str, exaggeration: float = 0.5, **kwargs) -> None:
        """Prepare reference audio embeddings."""
        self._ensure_model_loaded()
        self.model.prepare_conditionals(audio_path, exaggeration=exaggeration)
    
    def get_supported_params(self) -> Dict[str, Dict[str, Any]]:
        """Return Chatterbox-specific parameters."""
        return {
            'exaggeration': {
                'min': 0.0,
                'max': 1.0,
                'default': 0.5,
                'description': 'Emotional intensity. 0.0 = flat/monotone, 1.0 = very expressive',
                'step': 0.01
            },
            'cfg_weight': {
                'min': 0.0,
                'max': 1.0,
                'default': 0.7,
                'description': 'Voice similarity strength. Higher = closer to reference voice',
                'step': 0.01
            },
            'temperature': {
                'min': 0.5,
                'max': 1.0,
                'default': 0.8,
                'description': 'Creativity/randomness. Lower = consistent, Higher = varied',
                'step': 0.01
            },
        }
    
    @property
    def engine_name(self) -> str:
        return "Chatterbox"
    
    def cleanup(self):
        """Free GPU memory when switching engines."""
        if self.model is not None:
            del self.model
            self.model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
