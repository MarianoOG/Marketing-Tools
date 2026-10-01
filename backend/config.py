"""Paths and settings shared by every backend module.

Everything comes from the environment, with ``.env`` at the repository root
loaded first. ``DATA_DIR`` is where generated files live; it defaults to
``data/`` next to this package, and Compose points it at the mounted volume.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

load_dotenv(ENV_PATH)

DATA_DIR = Path(os.environ.get("DATA_DIR") or ROOT / "data").resolve()
IMG_DIR = DATA_DIR / "img"

HOST = os.environ.get("BACKEND_HOST", "127.0.0.1")
PORT = int(os.environ.get("BACKEND_PORT", "8765"))
