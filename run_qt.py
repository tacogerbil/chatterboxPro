import sys
import os


# Ensure the execution directory is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from core.q_main_window import launch_qt_app

if __name__ == "__main__":
    launch_qt_app()
