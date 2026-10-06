"""
Spike CLI Entrypoint
Usage:
  py spike.py run <file-or-url>
  py spike.py eval <dataset.json>
  py spike.py status <video_id>
"""

import sys
from pathlib import Path

# Ensure root directory is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.cli import main

if __name__ == "__main__":
    main()
