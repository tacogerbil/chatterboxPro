import torch
import logging
import os
import re
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

        # MCCC VRAM Patch: MOSS-TTS natively hardcodes device=input_ids.device in generate()
        # This breaks accelerate device_map="auto" spanning. We dynamically patch their architecture file.
        if combine_gpus:
            try:
                modeling_path = os.path.join(load_path, "modeling_moss_tts.py")
                if os.path.exists(modeling_path):
                    with open(modeling_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    # Check if already patched to avoid redundant writes
                    if "MCCC Multi-GPU Patch" not in content:
                        logging.info("Applying MCCC Multi-GPU Patch to MOSS-TTS architecture...")
                        
                        # 1. Resolve true base device
                        r1 = "        device = input_ids.device\n        \n        # MCCC Multi-GPU Patch: Find the true starting device where the embedding layer lives\n        model_device = next(self.parameters()).device\n"
                        content = content.replace("        device = input_ids.device\n", r1)
                        
                        # 2. Push inputs to actual device, pull outputs back to mask tracking device
                        target_call = (
                            "            outputs = self(\n"
                            "                input_ids=current_input_ids,\n"
                            "                attention_mask=current_attention_mask,\n"
                            "                past_key_values=past_key_values,\n"
                            "                use_cache=True,\n"
                            "            )"
                        )
                        patched_call = (
                            "            outputs = self(\n"
                            "                input_ids=current_input_ids.to(model_device),\n"
                            "                attention_mask=current_attention_mask.to(model_device) if current_attention_mask is not None else None,\n"
                            "                past_key_values=past_key_values,\n"
                            "                use_cache=True,\n"
                            "            )\n"
                            "            # MCCC: Pull logits back to our tracker device so subsequent loop math works on matching devices\n"
                            "            outputs.logits = [l.to(device) for l in outputs.logits]"
                        )
                        content = content.replace(target_call, patched_call)
                        
                        with open(modeling_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        logging.info("MOSS-TTS architecture successfully patched for Multi-GPU.")
            except Exception as e:
                logging.error(f"Failed to dynamically patch MOSS-TTS architecture: {e}")

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
