import sys
import os

# expandable_segments reduces fragmentation-induced OOM on Linux.
# Not supported on the Windows PyTorch build — skip it there to avoid UserWarnings.
if sys.platform != "win32":
    os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

# Ensure the project root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from core.q_main_window import launch_qt_app

if __name__ == "__main__":
    launch_qt_app()
