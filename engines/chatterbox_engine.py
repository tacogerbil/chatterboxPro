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

# MCCC: Version Pinning
# To prevent future breakage, set this to the specific commit hash of the model you want to use.
# Example: "a1b2c3d4..."
# Leave as None to always use the latest version (Risk of drift).
MODEL_REVISION = None # Back to Latest (SHA caused 404)

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
                
                # Check for critical model file
                model_file = Path(self.model_path) / "ve.pt"
                if not model_file.exists():
                    print(f"[ChatterboxEngine] Model file {model_file} not found.")
                    
                    found_in_cache = False
                    try:
                        import shutil
                        import os
                        
                        # 0. Check Local Repo Source (Highest Priority)
                        # If the user has the model inside the 'chatterbox' package in this repo
                        repo_root = Path(__file__).parent.parent / "chatterbox"
                        local_repo_ve = repo_root / "ve.pt"
                        
                        print(f"[ChatterboxEngine] Checking local repo at: {repo_root}")
                        
                        if local_repo_ve.exists():
                             print(f"[ChatterboxEngine] Found model in local repo: {repo_root}")
                             print(f"[ChatterboxEngine] Copying from Repo to Target: {self.model_path}...")
                             # We Copy here (safe) or Move? Copy is safer for repo integrity, but user might want space.
                             # Let's Copy to be safe, user can delete original if they want.
                             for item in repo_root.iterdir():
                                if item.name == "ve.pt" or item.name == "config.json" or item.suffix == ".bin":  # Copy known model files
                                     shutil.copy2(item, self.model_path)
                             print("[ChatterboxEngine] Transfer complete.")
                             found_in_cache = True
                        
                        # 1. Try to find in Local HuggingFace Cache (Second Priority)
                        elif not found_in_cache:
                            user_home = Path.home()
                            cache_search_path = user_home / ".cache" / "huggingface" / "hub"
                            
                            # Pattern: models--ResembleAI--chatterbox/snapshots/<hash>/ve.pt
                            if cache_search_path.exists():
                                print(f"[ChatterboxEngine] Searching local cache: {cache_search_path}")
                                # Recursive glob to look deep in snapshots
                                potential_model_files = list(cache_search_path.glob("models--ResembleAI--chatterbox/snapshots/*/ve.pt"))
                                
                                if potential_model_files:
                                    source_ve = potential_model_files[0]
                                    source_dir = source_ve.parent
                                    print(f"[ChatterboxEngine] Found existing model in cache: {source_dir}")
                                    print(f"[ChatterboxEngine] MOVING to {self.model_path} (Saving Space)...")
                                    
                                    # Move all files from source snapshot to target
                                    for item in source_dir.iterdir():
                                        if item.is_file() or item.is_dir():
                                            shutil.move(str(item), str(self.model_path))
                                            
                                    print("[ChatterboxEngine] Transfer complete.")
                                    found_in_cache = True
                                
                    except Exception as e:
                        print(f"[ChatterboxEngine] Local transfer failed: {e}")

                    # 2. Strict Local Failure (No Auto-Download)
                    if not found_in_cache:
                        error_msg = (
                            f"Model file 've.pt' not found in {self.model_path}.\n"
                            f"Also could not find it in local repo ({repo_root}) or local cache.\n"
                            "Please Ensure the Chatterbox model files are present in your installation."
                        )
                        print(f"[ChatterboxEngine] CRITICAL: {error_msg}")
                        raise FileNotFoundError(error_msg)
                
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
