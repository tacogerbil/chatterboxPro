# engines/moss_engine.py
"""
MOSS-TTS Engine Implementation.
Adapts the OpenMOSS-Team/MOSS-TTS model for ChatterboxPro.
"""
import torch
import torchaudio
import logging
import os
from typing import Dict, Any, Optional
import importlib.util
from contextlib import nullcontext

from transformers import AutoModel, AutoProcessor

from .base_engine import BaseTTSEngine

class MossEngine(BaseTTSEngine):
    """
    Adapter for MOSS-TTS (8B) using Hugging Face Transformers.
    Supports text-to-speech and voice cloning via reference audio.
    """
    
    def __init__(self, device: str, **kwargs):
        """
        Initialize the MOSS-TTS engine.
        
        Args:
            device: Device string (e.g., 'cuda', 'cpu')
            **kwargs: Additional args like model_path
        """
        super().__init__(device)
        self.model = None
        self.processor = None
        self.sr = 24000 # MOSS-TTS usually outputs 24kHz
        
        self.custom_model_path = kwargs.get('model_path', '').strip()
        self.repo_id = "OpenMOSS-Team/MOSS-TTS"
        
        # Determine strict dtype based on device
        if "cuda" in self.device and torch.cuda.is_available():
            self.dtype = torch.bfloat16
        else:
            self.dtype = torch.float32
            
        self.combine_gpus = kwargs.get('combine_gpus', False)

    def _ensure_loaded(self):
        """Lazy load the model and processor using the clean adapter."""
        if self.model is not None:
            return

        logging.info(f"Loading MOSS-TTS ({self.repo_id}) on {self.device} via MossLoader...")
        try:
            from adapters.huggingface.moss_loader import MossLoader
            self.model, self.processor, self.sr = MossLoader.load(
                repo_id=self.repo_id,
                custom_model_path=self.custom_model_path,
                device=self.device,
                dtype=self.dtype,
                combine_gpus=self.combine_gpus
            )
            logging.info(f"MOSS-TTS loaded via adapter successfully. SR={self.sr}")
        except Exception as e:
            logging.critical(f"Failed to load MOSS-TTS: {e}")
            raise RuntimeError(f"MOSS-TTS Load Failed: {e}")

    def generate(
        self, 
        text: str, 
        ref_audio_path: str,
        **params
    ) -> torch.Tensor:
        """
        Generate audio using MOSS-TTS.
        
        Args:
            text: Input text
            ref_audio_path: Path to reference audio (optional, for cloning)
            **params: 
                - temperature (default 0.7)
                - top_p (default 0.8)
                - max_new_tokens (default 1024)
        """
        self._ensure_loaded()
        
        try:
            # Prepare inputs
            reference = [ref_audio_path] if (ref_audio_path and os.path.exists(ref_audio_path)) else None
            
            # Construct message
            user_message = self.processor.build_user_message(text=text, reference=reference)
            
            # Process inputs
            # mode="generation" is specific to MOSS processor usage
            batch = self.processor([user_message], mode="generation")
            
            # With device_map="balanced" the model is sharded across GPUs.
            # self.device is just the init hint; the actual first layer may be on a different GPU.
            # Use the model's true first-parameter device so inputs land in the right place.
            model_first_device = next(self.model.parameters()).device
            input_ids = batch["input_ids"].to(model_first_device)
            attention_mask = batch["attention_mask"].to(model_first_device)
            
            # MOSS-TTS Recommended Hyperparameters (for 8B model)
            # audio_temperature: 1.7
            # audio_top_p: 0.8
            # audio_top_k: 25
            # audio_repetition_penalty: 1.0
            
            # Map standard params to MOSS params
            temp = params.get('temperature', 1.7)
            # If default 0.7 from UI is passed, it might be too low. 
            # But we respect user input. 
            # (Ideally UI slider range should be increased)
            
            gen_kwargs = {
                "max_new_tokens": params.get('max_new_tokens', 1024),
                "audio_temperature": temp,
                "audio_top_p": params.get('top_p', 0.8),
                "audio_top_k": 25, # Fixed default
                "audio_repetition_penalty": 1.0, 
            }
            
            # Isolation: Disable cuDNN SDPA for MOSS to prevent crashes.
            # torch.backends.cuda.sdp_kernel() was deprecated in PyTorch 2.3;
            # use torch.nn.attention.sdpa_kernel() instead.
            ctx = nullcontext()
            if "cuda" in self.device:
                try:
                    from torch.nn.attention import sdpa_kernel, SDPBackend
                    ctx = sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION, SDPBackend.MATH])
                except (ImportError, AttributeError):
                    # Fallback for older PyTorch builds
                    if hasattr(torch.backends.cuda, "sdp_kernel"):
                        ctx = torch.backends.cuda.sdp_kernel(enable_cudnn=False)
            
            with ctx, torch.no_grad():
                outputs = self.model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    **gen_kwargs
                )
            
            # Decode output
            # processor.decode returns a list of messages. We want the audio from the first one.
            decoded_msgs = self.processor.decode(outputs)
            
            # Extract audio codes
            if not decoded_msgs:
                raise ValueError("No output generated from MOSS-TTS")
                
            last_msg = decoded_msgs[-1] # content is usually in the last message
            
            if hasattr(last_msg, 'audio_codes_list') and last_msg.audio_codes_list:
                # audio_codes_list is usually a list of tensors
                audio_tensor = last_msg.audio_codes_list[0]
                
                # Normalize to [1, samples]
                if audio_tensor.dim() == 1:
                    audio_tensor = audio_tensor.unsqueeze(0)
                
                return audio_tensor.cpu()
            else:
                 # Look for it elsewhere just in case
                 logging.error(f"Unexpected MOSS Data Structure: {dir(last_msg)}")
                 raise ValueError("Could not find audio data in MOSS response")
                 
        except Exception as e:
            logging.error(f"MOSS-TTS Generation Error: {e}")
            raise

    def prepare_reference(self, audio_path: str, **params) -> None:
        """
        MOSS-TTS processes references on-the-fly via the processor.
        No explicit pre-cache needed.
        """
        pass

    def get_supported_params(self) -> Dict[str, Dict[str, Any]]:
        return {
            'temperature': {
                'min': 0.1, 'max': 2.5, 'default': 1.7, 
                'description': 'Audio Temperature (Rec: 1.7)'
            },
            'top_p': {
                'min': 0.1, 'max': 1.0, 'default': 0.8,
                'description': 'Nucleus sampling probability'
            },
             'max_new_tokens': {
                'min': 256, 'max': 4096, 'default': 1024,
                'description': 'Maximum generation length'
            }
        }

    @property
    def engine_name(self) -> str:
        return "MOSS-TTS"

    def cleanup(self):
        if self.model:
            del self.model
        if self.processor:
            del self.processor
        self.model = None
        self.processor = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
