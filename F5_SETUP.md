# F5-TTS Setup Guide

## Installation

### Step 1: Install F5-TTS

```bash
pip install git+https://github.com/SWivid/F5-TTS.git
```

This will install:
- F5-TTS core library
- Required dependencies (torch, torchaudio, etc.)
- Pre-trained models (~500MB download on first use)

### Step 2: Verify Installation

Run this test in Python:

```python
from f5_tts.api import F5TTS

# This will download models on first run
model = F5TTS(device="cuda:0")  # or "cpu" if no GPU
print("F5-TTS loaded successfully!")
```

### Step 3: Select F5 in ChatterboxPro

1. Open ChatterboxPro
2. Go to **Generation** tab
3. Select **"f5"** from the TTS Engine dropdown
4. Generate a preview to test

---

## System Requirements

### Minimum:
- **GPU**: 6GB VRAM (NVIDIA recommended)
- **RAM**: 8GB system RAM
- **Storage**: 2GB for models

### Recommended:
- **GPU**: 8GB+ VRAM
- **RAM**: 16GB system RAM
- **CUDA**: 11.8 or higher

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'f5_tts'"

**Solution:** F5-TTS not installed. Run:
```bash
pip install git+https://github.com/SWivid/F5-TTS.git
```

### "CUDA out of memory"

**Solutions:**
1. Close other GPU applications
2. Reduce batch size (not applicable for single-sentence preview)
3. Use CPU instead: Set device to "cpu" in settings
4. Switch to XTTS or Chatterbox (lower VRAM)

### "Model download failed"

**Solution:** Manual download:
1. Go to: https://huggingface.co/SWivid/F5-TTS
2. Download model files
3. Place in: `~/.cache/f5_tts/`

### Generation is slow

**Expected behavior:** F5-TTS is slower than Chatterbox but faster than XTTS
- Chatterbox: ~2-3s per sentence
- F5-TTS: ~4-6s per sentence
- XTTS: ~3-5s per sentence

Quality trade-off is worth it for final audiobooks!

---

## Performance Tips

1. **Use GPU**: F5-TTS is significantly faster on GPU
2. **Warm-up**: First generation is slower (model loading)
3. **Reference Audio**: Use clean, 10-30 second reference clips
4. **Batch Processing**: F5-TTS benefits from longer text chunks

---

## Comparison

| Feature | Chatterbox | XTTS | F5-TTS |
|---------|-----------|------|--------|
| Quality | Good | Excellent | **Best** |
| Speed | Fastest | Fast | Medium |
| Accent | ❌ British bias | ✅ Good | ✅ **Excellent** |
| VRAM | 4GB | 6GB | 6GB |
| Setup | Built-in | `pip install TTS` | Git install |

---

## Next Steps

After installation:
1. Test with Keanu Reeves voice
2. Compare quality vs XTTS and Chatterbox
3. Use F5 for final audiobook generation if quality is best
