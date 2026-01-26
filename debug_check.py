import sys
import os

# Add current dir to path just in case
sys.path.append(os.getcwd())

print(f"CWD: {os.getcwd()}")

try:
    print("Attempting import core.services.generation_service...")
    from core.services.generation_service import GenerationService
    print("GenerationService imported.")
except Exception as e:
    print(f"GenerationService Import Failed: {e}")
    import traceback
    traceback.print_exc()

try:
    print("Attempting import workers.tts_worker...")
    from workers.tts_worker import worker_process_chunk
    print("tts_worker imported.")
except Exception as e:
    print(f"tts_worker Import Failed: {e}")
    import traceback
    traceback.print_exc()
