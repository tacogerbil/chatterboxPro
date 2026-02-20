import glob
import sys
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

        # MCCC VRAM Patch: MOSS-TTS natively hardcodes device=input_ids.device in generate(),
        # which breaks accelerate device_map="auto" spanning across multiple GPUs.
        # We patch their architecture file in BOTH locations HuggingFace uses:
        #   1. The hub snapshot (load_path) — source of truth for downloads
        #   2. The transformers_modules cache — where trust_remote_code ACTUALLY IMPORTS FROM
        # Both must be patched; patching only the hub snapshot has no effect on running code.
        if combine_gpus:
            try:
                # Discover HF modules cache (cross-platform: ~/. on Linux, ~\AppData or ~/.cache on Windows)
                try:
                    from huggingface_hub.constants import HF_HOME
                except ImportError:
                    HF_HOME = os.path.expanduser("~/.cache/huggingface")
                hf_modules_cache = os.environ.get(
                    "HF_MODULES_CACHE",
                    os.path.join(HF_HOME, "modules")
                )

                # Collect all copies of the MOSS modeling file
                paths_to_patch = [os.path.join(load_path, "modeling_moss_tts.py")]
                modules_copies = glob.glob(
                    os.path.join(hf_modules_cache, "**", "modeling_moss_tts.py"),
                    recursive=True
                )
                paths_to_patch.extend(modules_copies)
                logging.info(f"MCCC: Found {len(paths_to_patch)} modeling_moss_tts.py file(s) to patch: {paths_to_patch}")

                for modeling_path in paths_to_patch:
                    if not os.path.exists(modeling_path):
                        continue
                    try:
                        with open(modeling_path, 'r', encoding='utf-8') as f:
                            content = f.read()

                        needs_write = False

                        # Patch 0: Fix deprecated torch_dtype= kwarg in MOSS's internal sub-model calls.
                        if "torch_dtype=" in content:
                            content = content.replace("torch_dtype=", "dtype=")
                            needs_write = True
                            logging.info(f"MCCC Patch 0 (torch_dtype): applied to {modeling_path}")

                        # Patch 1: Multi-GPU device routing — route inputs to the true first-layer device.
                        if "MCCC Multi-GPU Patch" not in content:
                            r1 = "        device = input_ids.device\n        \n        # MCCC Multi-GPU Patch: Find the true starting device where the embedding layer lives\n        model_device = next(self.parameters()).device\n"
                            content = content.replace("        device = input_ids.device\n", r1)

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
                            needs_write = True
                            logging.info(f"MCCC Patch 1 (Multi-GPU): applied to {modeling_path}")

                        # Patch 2: Fix cross-device tensor add in get_input_embeddings().
                        # Accelerate shards embedding layers across GPUs; inputs_embeds lands on cuda:0
                        # but embed_layer[N] may live on cuda:1 — the add() then crashes.
                        # Fix: route each input slice to its embed_layer's device, pull result back.
                        if "MCCC Patch2 get_input_embeddings" not in content:
                            p2_pattern = (
                                r'(\s+)(inputs_embeds = inputs_embeds \+ embed_layer'
                                r'\(input_ids\[\.\.\., i \+ 1\]\))'
                            )
                            p2_repl = (
                                r'\1inputs_embeds = inputs_embeds + '
                                r'embed_layer(input_ids[..., i + 1].to(next(embed_layer.parameters()).device))'
                                r'.to(inputs_embeds.device)  # MCCC Patch2 get_input_embeddings'
                            )
                            new_content, count = re.subn(p2_pattern, p2_repl, content)
                            if count > 0:
                                content = new_content
                                needs_write = True
                                logging.info(f"MCCC Patch 2 (get_input_embeddings): applied to {modeling_path}")
                            else:
                                logging.warning(f"MCCC Patch 2: target pattern not found in {modeling_path}")

                        if needs_write:
                            with open(modeling_path, 'w', encoding='utf-8') as f:
                                f.write(content)
                            logging.info(f"MOSS-TTS patches written: {modeling_path}")
                        else:
                            logging.info(f"MOSS-TTS already fully patched: {modeling_path}")
                    except Exception as e:
                        logging.error(f"Failed to patch {modeling_path}: {e}")

                # Invalidate stale cached imports so Python re-reads the patched files on next from_pretrained().
                # Without this, even a correctly patched file on disk has no effect — Python reuses
                # the old bytecode already loaded into sys.modules from the first import.
                stale_keys = [k for k in sys.modules if 'MOSS' in k or 'moss_tts' in k.lower()]
                for key in stale_keys:
                    del sys.modules[key]
                if stale_keys:
                    logging.info(f"MCCC: Invalidated {len(stale_keys)} stale module cache entries: {stale_keys}")
            except Exception as e:
                logging.error(f"MCCC patch discovery failed: {e}")

        # 2. Resolve Attention
        # FA2 detection: `import flash_attn_2_cuda` is unreliable — the internal CUDA extension
        # name changed across FA2 versions (2.4+) and throws OSError/RuntimeError on arch mismatch
        # (e.g. Blackwell SM 12.x) rather than ImportError. We catch all exceptions and use the
        # public flash_attn API instead. We also check the specific target GPU's compute capability.
        attn_impl = "eager"
        if "cuda" in device:
            has_fa2 = False
            fa2_reason = "not checked"
            try:
                import flash_attn
                from flash_attn import flash_attn_func  # stable public API, exists in all FA2 builds
                fa2_version = getattr(flash_attn, '__version__', '0')
                if int(fa2_version.split('.')[0]) >= 2:
                    has_fa2 = True
                    fa2_reason = f"flash_attn {fa2_version} detected"
                else:
                    fa2_reason = f"flash_attn {fa2_version} is FA1, skipping"
            except ImportError:
                fa2_reason = "flash_attn not installed"
            except Exception as e:
                # OSError = compiled for wrong CUDA arch; RuntimeError = CUDA init issue
                fa2_reason = f"flash_attn import error ({type(e).__name__}: {e})"

            if has_fa2 and dtype in {torch.float16, torch.bfloat16}:
                # Check the specific GPU being loaded to, not whatever is current device
                device_idx = int(device.split(':')[-1]) if ':' in device else 0
                major, minor = torch.cuda.get_device_capability(device_idx)
                if major >= 8:
                    attn_impl = "flash_attention_2"
                else:
                    fa2_reason += f" (GPU SM {major}.{minor} < 8.0, needs Ampere+)"

            if attn_impl != "flash_attention_2":
                attn_impl = "sdpa"
                logging.info(f"FA2 unavailable ({fa2_reason}), using SDPA.")
            else:
                logging.info(f"FA2 enabled ({fa2_reason}).")

        logging.info(f"MOSS-TTS Attention Implementation: {attn_impl}")

        # 3. Base Kwargs
        load_kwargs = {
            "trust_remote_code": True,
            "attn_implementation": attn_impl,
            "dtype": dtype,
        }

        # 4. Hardware Allocation Strategy
        if "cuda" in device:
            if combine_gpus:
                logging.info(f"Multi-GPU Spanning Enabled. Treating all available GPUs as a single VRAM pool.")
                # "auto" fills GPU 0 first (now empty — Whisper is on GPU 1), then spills to GPU 1.
                # More predictable than "balanced" and avoids fragmentation from split allocations.
                # NOTE: max_memory is computed BELOW, after the processor/audio_tokenizer are loaded,
                # so mem_get_info() captures the audio_tokenizer's ~2-3GB footprint on GPU 0.
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
        
        # Audio tokenizer placement.
        # When combining GPUs, keep the audio tokenizer on CPU (float32).
        # It loads in float32 by default and consumes ~8GB of GPU VRAM.
        # Offloading it to CPU:
        #   - Frees the full 8GB on GPU 0 for MOSS transformer layers
        #   - Avoids dtype mismatch (codec forward() receives float32 audio; bfloat16 weights crash)
        #   - MOSS's batch_encode/decode on CPU is fast enough (small buffers, not the bottleneck)
        if hasattr(processor, 'audio_tokenizer'):
            if combine_gpus:
                processor.audio_tokenizer = processor.audio_tokenizer.to("cpu")
            else:
                processor.audio_tokenizer = processor.audio_tokenizer.to(device)

        # 5b. Deferred max_memory computation (combine_gpus only).
        # CRITICAL: Must run AFTER processor.audio_tokenizer is moved to GPU 0 above.
        # The audio_tokenizer (~2-3GB, 1600 weights) would otherwise be invisible to mem_get_info()
        # when max_memory is set, causing Transformers to over-allocate on GPU 0 and OOM.
        if combine_gpus and "cuda" in device:
            max_mem = {}
            # 2GB per GPU is generous for MOSS 8B activations.
            # KV cache at 1024 tokens ≈ 0.5GB; peak forward-pass activations ≈ 1-1.5GB.
            # (Previously 3GB — was too conservative, killing our usable VRAM budget.)
            activation_headroom_gb = 2.0
            for i in range(torch.cuda.device_count()):
                free_bytes, total_bytes = torch.cuda.mem_get_info(i)
                free_gb = free_bytes / (1024**3)
                total_gb = total_bytes / (1024**3)
                usable_gb = max(1.0, free_gb - activation_headroom_gb)
                max_mem[i] = f"{usable_gb:.2f}GiB"
                logging.info(f"GPU {i}: {free_gb:.2f}GiB free / {total_gb:.2f}GiB total → allocating {usable_gb:.2f}GiB for MOSS weights.")

            # Guard: if available VRAM is too low, MOSS would silently offload layers to
            # disk (meta device), making generation hang at 0% indefinitely. Fail fast instead.
            # 12GB minimum allows up to 4GB CPU spillover, which accelerate handles fine.
            # (Disk offload hangs; CPU offload is just slower — big difference.)
            MIN_GPU_VRAM_GB = 12.0
            total_usable_gb = sum(float(v.replace("GiB", "")) for v in max_mem.values())
            if total_usable_gb < MIN_GPU_VRAM_GB:
                raise RuntimeError(
                    f"Insufficient GPU VRAM for MOSS in-memory inference: only {total_usable_gb:.1f}GiB "
                    f"usable across all GPUs (need {MIN_GPU_VRAM_GB}GiB). GPU memory from a prior "
                    f"failed attempt may still be allocated. Restart the application to reset GPU state."
                )
            load_kwargs["max_memory"] = max_mem

        logging.info(f"Loading MOSS Weights... (kwargs: {list(load_kwargs.keys())})")

        # Explicit VRAM defrag before massive load
        if "cuda" in device:
            import gc
            gc.collect()  # Break any reference cycles before cache flush
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
