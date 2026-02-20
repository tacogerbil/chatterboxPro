import torch
import logging
import os
from transformers import AutoModel, AutoProcessor

class MossLoader:
    """
    Adapter for instantiating the MOSS-TTS Hugging Face model.
    MCCC: Single Responsibility - Hardware mapping and model materialization.
    """
    
    @staticmethod
    def load(
        repo_id: str = "OpenMOSS-Team/MOSS-TTS",
        custom_model_path: str = "",
        device: str = "cuda:0",
        dtype: torch.dtype = torch.bfloat16,
        combine_gpus: bool = False
    ):
        """
        Safely loads the MOSS model and processor.
        
        Args:
            repo_id: HF repo ID
            custom_model_path: Optional local cache path
            device: Target device if not combining
            dtype: Expected tensor layout
            combine_gpus: If True, uses HF 'auto' to span multiple GPUs.
            
        Returns:
            (model, processor, sample_rate)
        """
        # 1. Resolve Path
        load_path = repo_id
        if custom_model_path:
            if not os.path.exists(os.path.join(custom_model_path, "config.json")):
                from huggingface_hub import snapshot_download
                logging.info(f"Downloading MOSS-TTS to custom path: {custom_model_path}...")
                os.makedirs(custom_model_path, exist_ok=True)
                snapshot_download(repo_id=repo_id, local_dir=custom_model_path)
            load_path = custom_model_path
        else:
            from huggingface_hub import snapshot_download
            logging.info(f"Resolving {repo_id} to local HF cache...")
            load_path = snapshot_download(repo_id=repo_id)

        # 2. Resolve Attention
        attn_impl = "eager"
        if "cuda" in device:
            has_fa2 = False
            try:
                import flash_attn
                import flash_attn_2_cuda
                has_fa2 = True
            except ImportError:
                pass
                
            if has_fa2 and dtype in {torch.float16, torch.bfloat16}:
                 major, _ = torch.cuda.get_device_capability()
                 if major >= 8:
                     attn_impl = "flash_attention_2"
            
            if attn_impl == "eager":
                # Fallback to PyTorch SDPA 
                attn_impl = "sdpa" 
                
        logging.info(f"MOSS-TTS Attention Implementation: {attn_impl}")

        # 3. Base Kwargs
        load_kwargs = {
            "trust_remote_code": True,
            "attn_implementation": attn_impl,
            "torch_dtype": dtype,
        }

        # 4. Hardware Allocation Strategy
        if "cuda" in device:
            if combine_gpus:
                logging.info(f"Multi-GPU Spanning Enabled. Treating all available GPUs as a single VRAM pool.")
                load_kwargs["device_map"] = "auto"
                # Do NOT use 8-bit. We have enough combined VRAM to run native precision!
            else:
                logging.info(f"Single-GPU Mode. Falling back to 8-bit quantization to prevent OOM on {device}.")
                try:
                    import bitsandbytes
                    load_kwargs["load_in_8bit"] = True
                    load_kwargs["device_map"] = { "": device }
                except Exception as e:
                    logging.warning(f"Failed to configure 8-bit quantization: {e}")
                    load_kwargs["device_map"] = { "": device }
        else:
            load_kwargs["device_map"] = { "": "cpu" }

        # 5. Execute Load
        logging.info(f"Loading MOSS Processor...")
        processor = AutoProcessor.from_pretrained(
            load_path, 
            trust_remote_code=True
        )
        
        # Audio tokenizer needs explicit movement if not using 'auto'
        if hasattr(processor, 'audio_tokenizer'):
            if combine_gpus:
                # 'auto' handles it, usually maps to first visible GPU
                # But to be safe, we'll put it on cuda:0 since it's tiny
                processor.audio_tokenizer = processor.audio_tokenizer.to("cuda:0")
            else:
                processor.audio_tokenizer = processor.audio_tokenizer.to(device)

        logging.info(f"Loading MOSS Weights... (kwargs: {list(load_kwargs.keys())})")
        
        # Explicit VRAM defrag before massive load
        if "cuda" in device:
            torch.cuda.empty_cache()
            
        model = AutoModel.from_pretrained(
            load_path,
            **load_kwargs
        )
        
        model.eval()
        
        sr = 24000
        if hasattr(processor, 'model_config'):
              sr = getattr(processor.model_config, 'sampling_rate', 24000)
              
        return model, processor, sr
