import sys
import os

# Must be set before any CUDA allocation occurs.
# expandable_segments:True prevents fragmentation-induced OOM when loading large models
# (e.g. MOSS 8B) alongside smaller ones (e.g. Whisper) on the same GPU.
# Worker subprocesses inherit this via os.environ, so it covers the multiprocessing pool too.
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

# Ensure the project root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from core.q_main_window import launch_qt_app

if __name__ == "__main__":
    launch_qt_app()
