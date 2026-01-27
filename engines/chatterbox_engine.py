# engines/chatterbox_engine.py
"""
Chatterbox TTS Engine Adapter.
Wraps the existing Chatterbox implementation to conform to BaseTTSEngine interface.
"""
import torch
from pathlib import Path
from typing import Dict, Any

from .base_engine import BaseTTSEngine
from chatterbox.tts import ChatterboxTTS

class ChatterboxEngine(BaseTTSEngine):
    """Adapter for Chatterbox TTS engine."""
    
    def __init__(self, device: str, model_path: str = None, **kwargs):
        super().__init__(device)
        self.model = None
        self.sr = 24000  # Chatterbox sample rate
        self.model_path = model_path
    
    def _ensure_model_loaded(self):
        """Lazy load the model on first use."""
        if self.model is None:
            if self.model_path:
                print(f"[ChatterboxEngine] Loading from local path: {self.model_path}")
                self.model = ChatterboxTTS.from_local(self.model_path, self.device)
            else:
                print(f"[ChatterboxEngine] Loading from Hub (default)...")
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
            temperature=temperature
            # apply_watermark and use_cond_cache are NOT supported in official upstream
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
