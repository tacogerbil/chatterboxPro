# engines/base_engine.py
"""
Base interface for all TTS engines.
All TTS engines must implement this interface to be compatible with ChatterboxPro.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pathlib import Path
import torch

class BaseTTSEngine(ABC):
    """Abstract base class for TTS engines."""
    
    def __init__(self, device: str):
        """
        Initialize the TTS engine.
        
        Args:
            device: Device string (e.g., 'cuda:0', 'cpu')
        """
        self.device = device
        self.sr = 24000  # Default sample rate, can be overridden
    
    @abstractmethod
    def generate(
        self, 
        text: str, 
        ref_audio_path: str,
        **params
    ) -> torch.Tensor:
        """
        Generate audio from text using voice cloning.
        
        Args:
            text: Text to synthesize
            ref_audio_path: Path to reference audio for voice cloning
            **params: Engine-specific parameters (exaggeration, temperature, etc.)
        
        Returns:
            Audio tensor (1, samples) at self.sr sample rate
        """
        pass
    
    @abstractmethod
    def prepare_reference(self, audio_path: str, **params) -> None:
        """
        Prepare/cache reference audio embeddings for faster generation.
        
        Args:
            audio_path: Path to reference audio
            **params: Engine-specific parameters
        """
        pass
    
    @abstractmethod
    def get_supported_params(self) -> Dict[str, Dict[str, Any]]:
        """
        Return dictionary of supported parameters and their metadata.
        
        Returns:
            Dict with parameter names as keys and metadata as values:
            {
                'temperature': {
                    'min': 0.5,
                    'max': 1.0,
                    'default': 0.8,
                    'description': 'Controls randomness'
                },
                ...
            }
        """
        pass
    
    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return human-readable engine name."""
        pass
    
    def cleanup(self):
        """Optional cleanup method called when switching engines."""
        pass
