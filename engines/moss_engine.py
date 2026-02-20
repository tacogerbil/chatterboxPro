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
        
        # MCCC: Allow offline usage via model_path, fallback to HF repo
        self.custom_model_path = kwargs.get('model_path', '').strip()
        self.repo_id = "OpenMOSS-Team/MOSS-TTS"
        
        # Determine strict dtype based on device
        if "cuda" in self.device and torch.cuda.is_available():
            self.dtype = torch.bfloat16
        else:
            self.dtype = torch.float32

    def _ensure_loaded(self):
        """Lazy load the model and processor."""
        if self.model is not None:
            return

        logging.info(f"Loading MOSS-TTS ({self.repo_id}) on {self.device}...")
        try:
            # 1. Resolve Attention Implementation
            attn_impl = "eager"
            if "cuda" in self.device:
                # Check for Flash Attention 2
                has_fa2 = importlib.util.find_spec("flash_attn") is not None
                if has_fa2 and self.dtype in {torch.float16, torch.bfloat16}:
                     major, _ = torch.cuda.get_device_capability()
                     if major >= 8:
                         attn_impl = "flash_attention_2"
                
                if attn_impl == "eager":
                    # Fallback to PyTorch SDPA (Scaled Dot Product Attention)
                    # This is efficient and built-in to PyTorch 2.0+
                    attn_impl = "sdpa" 
            
            logging.info(f"MOSS-TTS Attention Implementation: {attn_impl}")

            load_path = self.repo_id

            if self.custom_model_path:
                # User specified a custom path. Let's check if it has the model files.
                if not os.path.exists(os.path.join(self.custom_model_path, "config.json")):
                    # Need to download it to this path
                    from huggingface_hub import snapshot_download
                    logging.info(f"Downloading MOSS-TTS to custom path: {self.custom_model_path}...")
                    os.makedirs(self.custom_model_path, exist_ok=True)
                    snapshot_download(repo_id=self.repo_id, local_dir=self.custom_model_path)
                
                load_path = self.custom_model_path
            else:
                # No custom path. Use default cache, but resolve to local path to avoid HF backslash bugs.
                from huggingface_hub import snapshot_download
                logging.info(f"Resolving {self.repo_id} to local HF cache...")
                load_path = snapshot_download(repo_id=self.repo_id)
                logging.info(f"Resolved to local path: {load_path}")
            
            # 2. Load Processor
            self.processor = AutoProcessor.from_pretrained(
                load_path, 
                trust_remote_code=True
            )
            
            # Move audio tokenizer to device if applicable (as per MOSS docs)
            if hasattr(self.processor, 'audio_tokenizer'):
                 self.processor.audio_tokenizer = self.processor.audio_tokenizer.to(self.device)

            # 3. Load Model
            self.model = AutoModel.from_pretrained(
                load_path,
                trust_remote_code=True,
                attn_implementation=attn_impl,
                torch_dtype=self.dtype
            ).to(self.device)
            
            self.model.eval()
            
            # Update sample rate from config if possible
            if hasattr(self.processor, 'model_config'):
                 self.sr = getattr(self.processor.model_config, 'sampling_rate', 24000)
            
            logging.info(f"MOSS-TTS loaded successfully. SR={self.sr}")
            
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
            
            input_ids = batch["input_ids"].to(self.device)
            attention_mask = batch["attention_mask"].to(self.device)
            
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
                "do_sample": True,
            }
            
            # Isolation: Disable cuDNN SDPA for MOSS to prevent crashes
            # This context manager ensures it DOES NOT affect other parts of the app
            ctx = nullcontext()
            if "cuda" in self.device and hasattr(torch.backends.cuda, "sdp_kernel"):
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
