# engines/f5_engine.py
"""
F5-TTS Engine Implementation.
State-of-the-art voice cloning with excellent quality and speed.
"""
import torch
import torchaudio
from pathlib import Path
from typing import Dict, Any
import logging
import tempfile
import os

from .base_engine import BaseTTSEngine

class F5Engine(BaseTTSEngine):
    """F5-TTS engine with state-of-the-art voice cloning."""
    
    def __init__(self, device: str):
        super().__init__(device)
        self.model = None
        self.sr = 24000  # F5-TTS sample rate
    
    def _ensure_model_loaded(self):
        """Lazy load the F5-TTS model on first use."""
        if self.model is None:
            try:
                from f5_tts.api import F5TTS
                import os
                
                # Check for custom model path from environment variable
                custom_cache = os.environ.get('F5_MODEL_PATH') or os.environ.get('HF_HOME')
                if custom_cache:
                    logging.info(f"Using custom model cache: {custom_cache}")
                    os.environ['HF_HOME'] = custom_cache
                
                logging.info(f"Loading F5-TTS model on {self.device}...")
                
                # Load F5-TTS model
                self.model = F5TTS(device=self.device)
                self.sr = 24000
                
                logging.info("F5-TTS model loaded successfully")
            except ImportError:
                raise ImportError(
                    "F5-TTS requires the f5-tts library. Install with:\n"
                    "pip install git+https://github.com/SWivid/F5-TTS.git"
                )
            except Exception as e:
                logging.error(f"Failed to load F5-TTS model: {e}")
                raise
    
    def generate(
        self, 
        text: str, 
        ref_audio_path: str,
        speed: float = 1.0,
        cross_fade_duration: float = 0.15,
        **kwargs
    ) -> torch.Tensor:
        """
        Generate audio using F5-TTS.
        
        Args:
            text: Text to synthesize
            ref_audio_path: Path to reference audio for voice cloning
            speed: Speaking rate multiplier (handled by FFmpeg post-processing)
            cross_fade_duration: Duration for cross-fading between segments
        
        Returns:
            Audio tensor (1, samples) at 24kHz
        """
        self._ensure_model_loaded()
        
        try:
            # F5-TTS generates directly to tensor
            result = self.model.infer(
                ref_file=ref_audio_path,
                ref_text="",  # F5 can auto-transcribe reference
                gen_text=text,
                cross_fade_duration=cross_fade_duration
            )
            
            # F5-TTS returns (wav, sr, spectrogram) tuple
            if isinstance(result, tuple):
                wav_tensor = result[0]  # Extract audio tensor
            else:
                wav_tensor = result
            
            # Ensure correct shape (1, samples)
            if wav_tensor.dim() == 1:
                wav_tensor = wav_tensor.unsqueeze(0)
            elif wav_tensor.shape[0] > 1:
                wav_tensor = wav_tensor.mean(dim=0, keepdim=True)
            
            return wav_tensor
        
        except Exception as e:
            logging.error(f"F5-TTS generation failed: {e}")
            raise
    
    def prepare_reference(self, audio_path: str, **kwargs) -> None:
        """
        F5-TTS doesn't require explicit reference preparation.
        It processes the reference audio on-the-fly during generation.
        """
        self._ensure_model_loaded()
        logging.info(f"F5-TTS: Reference audio set to {audio_path}")
    
    def get_supported_params(self) -> Dict[str, Dict[str, Any]]:
        """Return F5-TTS-specific parameters."""
        return {
            'cross_fade_duration': {
                'min': 0.0,
                'max': 1.0,
                'default': 0.15,
                'description': 'Duration for cross-fading between audio segments',
                'step': 0.05
            },
            'speed': {
                'min': 0.5,
                'max': 2.0,
                'default': 1.0,
                'description': 'Speaking rate (handled by FFmpeg post-processing)',
                'step': 0.1
            },
        }
    
    @property
    def engine_name(self) -> str:
        return "F5-TTS"
    
    def cleanup(self):
        """Free GPU memory when switching engines."""
        if self.model is not None:
            del self.model
            self.model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
