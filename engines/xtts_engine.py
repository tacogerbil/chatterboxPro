# engines/xtts_engine.py
"""
XTTS v2 TTS Engine Implementation.
Provides voice cloning with better accent preservation than Chatterbox.
"""
import torch
import torchaudio
from pathlib import Path
from typing import Dict, Any
import logging

from .base_engine import BaseTTSEngine

class XTTSEngine(BaseTTSEngine):
    """XTTS v2 TTS engine with voice cloning."""
    
    def __init__(self, device: str):
        super().__init__(device)
        self.model = None
        self.sr = 24000  # XTTS sample rate
        self._ref_embeddings = None
    
    def _ensure_model_loaded(self):
        """Lazy load the XTTS model on first use."""
        if self.model is None:
            try:
                from TTS.api import TTS
                logging.info(f"Loading XTTS v2 model on {self.device}...")
                
                # Load XTTS v2 model
                self.model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(self.device)
                self.sr = 24000  # XTTS uses 24kHz
                
                logging.info("XTTS v2 model loaded successfully")
            except ImportError:
                raise ImportError(
                    "XTTS requires the TTS library. Install with: pip install TTS"
                )
            except Exception as e:
                logging.error(f"Failed to load XTTS model: {e}")
                raise
    
    def generate(
        self, 
        text: str, 
        ref_audio_path: str,
        temperature: float = 0.7,
        length_penalty: float = 1.0,
        repetition_penalty: float = 5.0,
        top_k: int = 50,
        top_p: float = 0.85,
        **kwargs
    ) -> torch.Tensor:
        """
        Generate audio using XTTS v2.
        
        Args:
            text: Text to synthesize
            ref_audio_path: Path to reference audio for voice cloning
            temperature: Sampling temperature (0.1-1.0, lower = more consistent)
            length_penalty: Length penalty for generation
            repetition_penalty: Penalty for repetitive tokens
            top_k: Top-k sampling
            top_p: Nucleus sampling threshold
        
        Returns:
            Audio tensor (1, samples) at 24kHz
        """
        self._ensure_model_loaded()
        
        # XTTS generates to file, so we need a temp file
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            temp_path = tmp_file.name
        
        try:
            # Generate audio
            self.model.tts_to_file(
                text=text,
                speaker_wav=ref_audio_path,
                language="en",
                file_path=temp_path,
                temperature=temperature,
                length_penalty=length_penalty,
                repetition_penalty=repetition_penalty,
                top_k=top_k,
                top_p=top_p
            )
            
            # Load the generated audio
            wav_tensor, sr = torchaudio.load(temp_path)
            
            # Ensure correct sample rate
            if sr != self.sr:
                resampler = torchaudio.transforms.Resample(sr, self.sr)
                wav_tensor = resampler(wav_tensor)
            
            # Ensure mono
            if wav_tensor.shape[0] > 1:
                wav_tensor = wav_tensor.mean(dim=0, keepdim=True)
            
            return wav_tensor
        
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def prepare_reference(self, audio_path: str, **kwargs) -> None:
        """
        XTTS doesn't require explicit reference preparation.
        It processes the reference audio on-the-fly during generation.
        """
        self._ensure_model_loaded()
        # XTTS handles reference audio internally, no pre-processing needed
        logging.info(f"XTTS: Reference audio set to {audio_path}")
    
    def get_supported_params(self) -> Dict[str, Dict[str, Any]]:
        """Return XTTS-specific parameters."""
        return {
            'temperature': {
                'min': 0.1,
                'max': 1.0,
                'default': 0.7,
                'description': 'Sampling temperature. Lower = more consistent, Higher = more varied',
                'step': 0.05
            },
            'length_penalty': {
                'min': 0.5,
                'max': 2.0,
                'default': 1.0,
                'description': 'Length penalty for generation',
                'step': 0.1
            },
            'repetition_penalty': {
                'min': 1.0,
                'max': 10.0,
                'default': 5.0,
                'description': 'Penalty for repetitive speech',
                'step': 0.5
            },
        }
    
    @property
    def engine_name(self) -> str:
        return "XTTS v2"
    
    def cleanup(self):
        """Free GPU memory when switching engines."""
        if self.model is not None:
            del self.model
            self.model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
