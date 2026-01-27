from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import numpy as np

import librosa
import torch
import perth
import torch.nn.functional as F
from huggingface_hub import hf_hub_download
from peft import PeftModel
from utils.file_utils import get_audio_hash

from .models.t3 import T3
from .models.s3tokenizer import S3_SR, drop_invalid_tokens
from .models.s3gen import S3GEN_SR, S3Gen
from .models.tokenizers import EnTokenizer
from .models.voice_encoder import VoiceEncoder
from .models.t3.modules.cond_enc import T3Cond


REPO_ID = "ResembleAI/chatterbox"
COND_CACHE_DIR = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")) / "chatterbox_conds"
COND_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def punc_norm(text: str) -> str:
    """
        Quick cleanup func for punctuation from LLMs or
        containing chars not seen often in the dataset
    """
    if len(text) == 0:
        return "You need to add some text for me to talk."

    # Capitalise first letter
    if len(text) > 0 and text[0].islower(): # check length before accessing index 0
        text = text[0].upper() + text[1:]

    # Remove multiple space chars
    text = " ".join(text.split())

    # Replace uncommon/llm punc
    punc_to_replace = [
        ("...", ", "),
        ("…", ", "),
        (":", ","),
        (" - ", ", "),
        (";", ", "),
        ("—", "-"),
        ("–", "-"),
        (" ,", ","),
        ("“", "\""),
        ("”", "\""),
        ("‘", "'"),
        ("’", "'"),
    ]
    for old_char_sequence, new_char in punc_to_replace:
        text = text.replace(old_char_sequence, new_char)

    # Add full stop if no ending punc
    text = text.rstrip(" ")
    sentence_enders = {".", "!", "?", "-", ","}
    if len(text) > 0 and not any(text.endswith(p) for p in sentence_enders): # check length
        text += "."

    return text


@dataclass
class Conditionals:
    """
    Conditionals for T3 and S3Gen
    - T3 conditionals:
        - speaker_emb
        - clap_emb
        - cond_prompt_speech_tokens
        - cond_prompt_speech_emb
        - emotion_adv
    - S3Gen conditionals:
        - prompt_token
        - prompt_token_len
        - prompt_feat
        - prompt_feat_len
        - embedding
    """
    t3: T3Cond
    gen: dict

    def to(self, device):
        self.t3 = self.t3.to(device=device)
        for k, v in self.gen.items():
            if torch.is_tensor(v):
                self.gen[k] = v.to(device=device)
        return self

    def save(self, fpath: Path):
        arg_dict = dict(
            t3=self.t3.__dict__,
            gen=self.gen
        )
        torch.save(arg_dict, fpath)

    @classmethod
    def load(cls, fpath, map_location="cpu"):
        # Ensure weights_only=False if T3Cond or other complex objects are stored directly
        # If only tensors and basic types, weights_only=True might be okay, but safer False.
        kwargs = torch.load(fpath, map_location=map_location, weights_only=False)
        return cls(T3Cond(**kwargs['t3']), kwargs['gen'])


class ChatterboxTTS:
    ENC_COND_LEN = 6 * S3_SR
    DEC_COND_LEN = 10 * S3GEN_SR

    def __init__(
        self,
        t3: T3,
        s3gen: S3Gen,
        ve: VoiceEncoder,
        tokenizer: EnTokenizer,
        device: str,
        conds: Conditionals = None,
    ):
        self.sr = S3GEN_SR
        self.device = device

        self.t3 = t3.to(self.device).eval()
        self.s3gen = s3gen.to(self.device).eval()
        self.ve = ve.to(self.device).eval()
        self.tokenizer = tokenizer

        if conds:
            self.conds = conds.to(self.device)
        else:
            self.conds = None

        self.watermarker = perth.PerthImplicitWatermarker()

    @classmethod
    def from_local(cls, ckpt_dir, device) -> 'ChatterboxTTS':
        ckpt_dir = Path(ckpt_dir)
        map_location = device

        ve = VoiceEncoder()
        ve.load_state_dict(
            torch.load(ckpt_dir / "ve.pt", map_location=map_location)
        )

        t3 = T3()
        t3_state_dict = torch.load(ckpt_dir / "t3_cfg.pt", map_location=map_location)
        # Handle nested state dict keys if present
        if "model" in t3_state_dict and isinstance(t3_state_dict["model"], (dict, list)):
            model_state = t3_state_dict["model"]
            if isinstance(model_state, list) and len(model_state) > 0:
                t3_state_dict = model_state[0] # Take the first if it's a list of dicts
            elif isinstance(model_state, dict):
                t3_state_dict = model_state
        elif "state_dict" in t3_state_dict: # Another common pattern
             t3_state_dict = t3_state_dict["state_dict"]
        t3.load_state_dict(t3_state_dict)

        s3gen = S3Gen()
        s3gen.load_state_dict(
            torch.load(ckpt_dir / "s3gen.pt", map_location=map_location)
        )

        tokenizer = EnTokenizer(
            str(ckpt_dir / "tokenizer.json")
        )

        conds_obj = None
        if (builtin_voice := ckpt_dir / "conds.pt").exists():
            conds_obj = Conditionals.load(builtin_voice, map_location=map_location)

        return cls(t3, s3gen, ve, tokenizer, device, conds=conds_obj)

    @classmethod
    def from_pretrained(cls, device) -> 'ChatterboxTTS':
        downloaded_files = {}
        # Make sure all necessary files for from_local are downloaded
        required_files = ["ve.pt", "t3_cfg.pt", "s3gen.pt", "tokenizer.json"]
        optional_files = ["conds.pt"] # conds.pt is optional

        for fpath_str in required_files + optional_files:
            try:
                # Using local_files_only=False by default to ensure download if not present
                # Add cache_dir to huggingface_hub.constants.HF_HUB_CACHE or your preferred location
                # to control where models are stored.
                local_path = hf_hub_download(repo_id=REPO_ID, filename=fpath_str,
                                             cache_dir=os.path.join(Path.home(), ".cache", "huggingface", "hub"))
                downloaded_files[fpath_str] = local_path
            except Exception as e:
                if fpath_str in optional_files:
                    print(f"Optional file {fpath_str} not found or download failed: {e}. Proceeding without it.")
                else:
                    raise RuntimeError(f"Required file {fpath_str} could not be downloaded: {e}")

        ckpt_dir = Path(downloaded_files["ve.pt"]).parent
        return cls.from_local(ckpt_dir, device)



    def _try_load_cached_conds(self, cache_file: Path, exaggeration: float) -> Conditionals | None:
        if not cache_file.exists():
            return None
            
        print(f"Loading cached conditionals from {cache_file}")
        try:
            loaded_conds = Conditionals.load(cache_file, map_location=self.device)
            # Validate exaggeration match
            if not hasattr(loaded_conds.t3, 'emotion_adv') or \
               not torch.is_tensor(loaded_conds.t3.emotion_adv) or \
               not np.isclose(loaded_conds.t3.emotion_adv.item(), exaggeration):
                
                print("Exaggeration changed or emotion_adv invalid, patching.")
                new_emotion_adv = exaggeration * torch.ones(
                    1, 1, 1, device=self.device, dtype=loaded_conds.t3.speaker_emb.dtype
                )
                
                # Reconstruct T3Cond
                new_t3 = T3Cond(
                    speaker_emb=loaded_conds.t3.speaker_emb,
                    clap_emb=getattr(loaded_conds.t3, 'clap_emb', None),
                    cond_prompt_speech_tokens=getattr(loaded_conds.t3, 'cond_prompt_speech_tokens', None),
                    cond_prompt_speech_emb=getattr(loaded_conds.t3, 'cond_prompt_speech_emb', None),
                    emotion_adv=new_emotion_adv
                ).to(device=self.device)
                
                loaded_conds.t3 = new_t3
                loaded_conds.to(self.device).save(cache_file)
                
            return loaded_conds.to(self.device)
            
        except Exception as e:
            print(f"Failed to load/validate cache: {e}. Recomputing.")
            return None

    def _compute_new_conds(self, wav_fpath: str | Path, exaggeration: float) -> Conditionals:
        # 1. Load Audio
        s3gen_ref_wav_np, _ = librosa.load(wav_fpath, sr=S3GEN_SR)
        ref_16k_wav_np, _ = librosa.load(wav_fpath, sr=S3_SR)
        
        # Ensure numpy
        if not isinstance(s3gen_ref_wav_np, np.ndarray): s3gen_ref_wav_np = np.array(s3gen_ref_wav_np)
        if not isinstance(ref_16k_wav_np, np.ndarray): ref_16k_wav_np = np.array(ref_16k_wav_np)

        # 2. S3Gen Reference (Decoder)
        s3gen_ref_wav_trimmed = s3gen_ref_wav_np[:self.DEC_COND_LEN]
        s3gen_ref_dict = self.s3gen.embed_ref(
            torch.from_numpy(s3gen_ref_wav_trimmed).float(), 
            S3GEN_SR, 
            device=self.device
        )

        # 3. T3 Conditionals (Encoder)
        t3_cond_prompt_tokens = None
        if (plen := getattr(self.t3.hp, 'speech_cond_prompt_len', 0)) and plen > 0:
            ref_16k_input = [ref_16k_wav_np[:self.ENC_COND_LEN]]
            batch_tokens, _ = self.s3gen.tokenizer.forward(ref_16k_input, max_len=plen)
            t3_cond_prompt_tokens = torch.atleast_2d(batch_tokens[0]).to(self.device)

        # Voice Encoder
        ve_embed_numpy = self.ve.embeds_from_wavs([ref_16k_wav_np], sample_rate=S3_SR)
        ve_embed = torch.from_numpy(ve_embed_numpy).to(self.device)
        if ve_embed.ndim > 1 and ve_embed.shape[0] > 1: 
            ve_embed = ve_embed.mean(axis=0, keepdim=True)
        elif ve_embed.ndim == 1: 
            ve_embed = ve_embed.unsqueeze(0)

        target_dtype = self.t3.text_emb.weight.dtype if hasattr(self.t3, 'text_emb') else torch.float32

        t3_cond_obj = T3Cond(
            speaker_emb=ve_embed.to(dtype=target_dtype),
            cond_prompt_speech_tokens=t3_cond_prompt_tokens,
            emotion_adv=exaggeration * torch.ones(1, 1, 1, device=self.device, dtype=target_dtype),
        ).to(device=self.device)

        return Conditionals(t3_cond_obj, s3gen_ref_dict)

    def prepare_conditionals(self, wav_fpath: str | Path, exaggeration: float = 0.5, use_cache: bool = True) -> None:
        """
        Prepare conditionals for T3 and S3Gen from a reference audio file.
        Handles caching and embedding generation.
        """
        if not wav_fpath or not Path(wav_fpath).exists():
            print(f"[TTS.prepare_conditionals/WARN] Invalid reference audio path: {wav_fpath}.")
            if self.conds is None:
                raise ValueError("Reference audio path is invalid and no default conditionals are loaded.")
            return

        cache_file = None
        if use_cache:
            try:
                # Calculate Hash
                stat = os.stat(wav_fpath)
                unique_key = f"{wav_fpath}-{stat.st_mtime}-{stat.st_size}-{exaggeration}"
                audio_hash = hashlib.md5(unique_key.encode()).hexdigest()
                
                cache_file = COND_CACHE_DIR / f"{audio_hash}.pt"
                
                # Try Load
                if cached := self._try_load_cached_conds(cache_file, exaggeration):
                    self.conds = cached
                    return
            except Exception as e:
                print(f"[TTS/WARN] Caching setup failed: {e}. Proceeding without cache.")

        # Compute New
        self.conds = self._compute_new_conds(wav_fpath, exaggeration)

        # Save Cache
        if use_cache and cache_file:
            try:
                self.conds.save(cache_file)
                print(f"Saved new conditionals to cache: {cache_file}")
            except Exception as e:
                print(f"Failed to save to cache: {e}")

    def generate(
        self,
        text,
        audio_prompt_path=None,
        exaggeration=0.5,
        cfg_weight=0.5,
        temperature=0.8,
        apply_watermark=True,
        use_cond_cache=True,
    ):
        if audio_prompt_path:
            self.prepare_conditionals(audio_prompt_path, exaggeration=exaggeration, use_cache=use_cond_cache)

        if self.conds is None:
             raise ValueError("Conditionals not prepared. Provide `audio_prompt_path` or ensure built-in voice is loaded.")

        current_emotion_adv = self.conds.t3.emotion_adv
        target_dtype = self.conds.t3.speaker_emb.dtype # Use dtype from existing speaker_emb

        if not torch.is_tensor(current_emotion_adv) or not np.isclose(current_emotion_adv.item(), exaggeration):
            _cond_t3: T3Cond = self.conds.t3
            new_emotion_adv = exaggeration * torch.ones(1, 1, 1, device=self.device, dtype=target_dtype)

            self.conds.t3 = T3Cond(
                speaker_emb=_cond_t3.speaker_emb,
                clap_emb=getattr(_cond_t3, 'clap_emb', None),
                cond_prompt_speech_tokens=getattr(_cond_t3, 'cond_prompt_speech_tokens', None),
                cond_prompt_speech_emb=getattr(_cond_t3, 'cond_prompt_speech_emb', None),
                emotion_adv=new_emotion_adv
            ).to(device=self.device)

        text = punc_norm(text)
        text_tokens_single = self.tokenizer.text_to_tokens(text).to(self.device) # [1, T_text]

        # CFG setup: batch of 2 for cond and uncond
        # T3.prepare_input_embeds handles zeroing out the uncond part of text_emb
        text_tokens_cfg_batch = torch.cat([text_tokens_single, text_tokens_single.clone()], dim=0)

        sot = self.t3.hp.start_text_token
        eot = self.t3.hp.stop_text_token
        text_tokens_cfg_batch = F.pad(text_tokens_cfg_batch, (1, 0), value=sot)
        text_tokens_cfg_batch = F.pad(text_tokens_cfg_batch, (0, 1), value=eot)

        with torch.inference_mode():
            speech_tokens_result_batch = self.t3.inference(
                t3_cond=self.conds.t3, # T3.inference will expand this to batch size 2 if needed
                text_tokens=text_tokens_cfg_batch,
                max_new_tokens=1000,
                temperature=temperature,
                cfg_weight=cfg_weight,
            )
            print("[TTS Debug] T3 Inference returned. Validating tokens...")

            # Result from t3.inference (with CFG > 0) is the conditional part, already selected.
            # It should be [1, S_speech]
            speech_tokens = speech_tokens_result_batch[0] # Take the single sequence

            speech_tokens = drop_invalid_tokens(speech_tokens)
            speech_tokens = speech_tokens.to(self.device)
            if speech_tokens.ndim == 1:
                speech_tokens = speech_tokens.unsqueeze(0) # S3Gen expects [B, T]
            if speech_tokens.numel() == 0: # Handle empty tokens after drop_invalid
                print("[TTS.generate/WARN] No valid speech tokens after dropping SOS/EOS. Returning empty audio.")
                return torch.zeros((1,0), dtype=target_dtype, device="cpu")


            # S3Gen inference
            # s3gen.inference returns (wav, flow_cache), we only need wav here.
            # flow_cache is None for CausalMaskedDiffWithXvec in s3gen.flow
            
            # PEFT Fix: Robust access to inference method
            inference_model = self.s3gen
            # Recursive unwrap to find 'inference' method
            # PeftModel -> LoraModel -> model (S3Gen)
            for _ in range(6): 
                if hasattr(inference_model, 'inference'):
                    break
                if hasattr(inference_model, 'base_model'):
                    inference_model = inference_model.base_model
                elif hasattr(inference_model, 'model'):
                    inference_model = inference_model.model
                else:
                    break
            
            # Final specific check for DDP if needed, though usually handled above
            if not hasattr(inference_model, 'inference') and hasattr(inference_model, 'module'):
                inference_model = inference_model.module

            if not hasattr(inference_model, 'inference'):
                 # Fatal error with debug info
                 safe_attrs = [a for a in dir(inference_model) if not a.startswith('__')][:20]
                 raise AttributeError(f"Could not find 'inference' in {type(self.s3gen)} -> {type(inference_model)}. Attrs: {safe_attrs}")

            print(f"[TTS Debug] Invoking S3Gen inference on {type(inference_model).__name__}", flush=True)

            s3gen_output = inference_model.inference(
                speech_tokens=speech_tokens,
                ref_dict=self.conds.gen,
            )
            # s3gen.inference in s3gen.py might return a tuple (wav, cache) or just wav
            if isinstance(s3gen_output, tuple):
                wav = s3gen_output[0]
            else:
                wav = s3gen_output

            wav_np = wav.squeeze(0).detach().cpu().numpy()
            if apply_watermark:
                wav_np = self.watermarker.apply_watermark(wav_np, sample_rate=self.sr)
            return torch.from_numpy(wav_np).unsqueeze(0)

    def load_adapter(self, adapter_path: str, adapter_name: str) -> None:
        """
        Load a LoRA adapter onto the S3Gen model using PEFT.
        
        Args:
            adapter_path: Path to the adapter weights (local or HF Hub)
            adapter_name: Name to assign to this adapter for referencing
        """


        if not hasattr(self.s3gen, 'active_adapters'):
            # If not already a PeftModel, wrap it
            # Note: We wrap self.s3gen because that's where the linear layers are
            self.s3gen = PeftModel.from_pretrained(
                self.s3gen, 
                adapter_path, 
                adapter_name=adapter_name
            )
        else:
            # Already wrapped, just load another adapter
            self.s3gen.load_adapter(adapter_path, adapter_name=adapter_name)
            
        print(f"[TTS] Loaded adapter '{adapter_name}' from {adapter_path}")

    def set_adapter(self, adapter_names: str | list[str], adapter_weights: list[float] | None = None) -> None:
        """
        Activate one or more loaded adapters.
        
        Args:
            adapter_names: Single adapter name or list of names to activate
            adapter_weights: Optional weights for mixing adapters (if list provided)
        """


        if not hasattr(self.s3gen, 'set_adapter'):
            print("[TTS/WARN] No adapters loaded. Call load_adapter first.")
            return

        if isinstance(adapter_names, str):
            self.s3gen.set_adapter(adapter_names)
            print(f"[TTS] Activated adapter: {adapter_names}")
        else:
            # Multi-adapter mixing
            if adapter_weights:
                self.s3gen.add_weighted_adapter(
                    adapters=adapter_names,
                    weights=adapter_weights,
                    adapter_name="mixed_adapter",
                    combination_type="linear"
                )
                self.s3gen.set_adapter("mixed_adapter")
                print(f"[TTS] Activated mixed adapter: {adapter_names} with weights {adapter_weights}")
            else:
                # Just string them together? PEFT set_adapter usually expects a single name 
                # or manages multiple active adapters differently depending on config.
                # Standard set_adapter takes a string. Mixed adapters must be explicitly created.
                # If no weights provided but list given, assume equal weighting or error?
                # For now, let's assume if list given without weights, we just want to enable them?
                # Actually PEFT's set_adapter can take a list for some models, but usually for mixed.
                # Let's fallback to creating a mixed adapter with equal weights if no weights given.
                weights = [1.0 / len(adapter_names)] * len(adapter_names)
                self.s3gen.add_weighted_adapter(
                    adapters=adapter_names,
                    weights=weights,
                    adapter_name="mixed_adapter",
                    combination_type="linear"
                )
                self.s3gen.set_adapter("mixed_adapter")
                print(f"[TTS] Activated mixed adapter (equal weights): {adapter_names}")