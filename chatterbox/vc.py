from pathlib import Path

import librosa
import torch
import perth
from huggingface_hub import hf_hub_download

from .models.s3tokenizer import S3_SR
from .models.s3gen import S3GEN_SR, S3Gen


REPO_ID = "ResembleAI/chatterbox"


class ChatterboxVC:
    ENC_COND_LEN = 6 * S3_SR
    DEC_COND_LEN = 10 * S3GEN_SR

    def __init__(
        self,
        s3gen: S3Gen,
        device: str,
        ref_dict: dict=None,
    ):
        self.sr = S3GEN_SR
        self.s3gen = s3gen
        self.device = device
        self.watermarker = perth.PerthImplicitWatermarker()
        if ref_dict is None:
            self.ref_dict = None
        else:
            self.ref_dict = {
                k: v.to(device) if torch.is_tensor(v) else v
                for k, v in ref_dict.items()
            }

    @classmethod
    def from_local(cls, ckpt_dir, device) -> 'ChatterboxVC':
        ckpt_dir = Path(ckpt_dir)
        ref_dict = None
        if (builtin_voice := ckpt_dir / "conds.pt").exists():
            states = torch.load(builtin_voice)
            ref_dict = states['gen']

        s3gen = S3Gen()
        s3gen.load_state_dict(
            torch.load(ckpt_dir / "s3gen.pt")
        )
        s3gen.to(device).eval()

        return cls(s3gen, device, ref_dict=ref_dict)

    @classmethod
    def from_pretrained(cls, device) -> 'ChatterboxVC':
        for fpath in ["s3gen.pt", "conds.pt"]:
            local_path = hf_hub_download(repo_id=REPO_ID, filename=fpath)

        return cls.from_local(Path(local_path).parent, device)

    def set_target_voice(self, wav_fpath):
        ## Load reference wav
        s3gen_ref_wav, _sr = librosa.load(wav_fpath, sr=S3GEN_SR)

        s3gen_ref_wav = s3gen_ref_wav[:self.DEC_COND_LEN]
        self.ref_dict = self.s3gen.embed_ref(s3gen_ref_wav, S3GEN_SR, device=self.device)

    def load_adapter(self, adapter_path: str, adapter_name: str):
        """
        Load a LoRA adapter for the S3Gen flow estimator using PEFT.
        """
        from peft import PeftModel
        
        estimator = self.s3gen.flow.decoder.estimator
        if not isinstance(estimator, PeftModel):
            # First time loading: wrap the estimator
            # internal_estimator = estimator
            self.s3gen.flow.decoder.estimator = PeftModel.from_pretrained(
                estimator,
                adapter_path,
                adapter_name=adapter_name
            )
            # Ensure it stays on device
            self.s3gen.flow.decoder.estimator.to(self.device)
        else:
            # Already wrapped, just load new adapter
            estimator.load_adapter(adapter_path, adapter_name=adapter_name)

    def set_adapter(self, adapter_name: str):
        """
        Switch the active LoRA adapter.
        """
        from peft import PeftModel
        estimator = self.s3gen.flow.decoder.estimator
        if isinstance(estimator, PeftModel):
            estimator.set_adapter(adapter_name)
        else:
            print(f"Warning: Model is not using PEFT, cannot set adapter {adapter_name}")

    def generate(
        self,
        audio,
        target_voice_path=None,
    ):
        if target_voice_path:
            self.set_target_voice(target_voice_path)
        else:
            assert self.ref_dict is not None, "Please `prepare_conditionals` first or specify `target_voice_path`"

        with torch.inference_mode():
            audio_16, _ = librosa.load(audio, sr=S3_SR)
            audio_16 = torch.from_numpy(audio_16).float().to(self.device)[None, ]

            s3_tokens, _ = self.s3gen.tokenizer(audio_16)
            wav, _ = self.s3gen.inference(
                speech_tokens=s3_tokens,
                ref_dict=self.ref_dict,
            )
            wav = wav.squeeze(0).detach().cpu().numpy()
            watermarked_wav = self.watermarker.apply_watermark(wav, sample_rate=self.sr)
        return torch.from_numpy(watermarked_wav).unsqueeze(0)
