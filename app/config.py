import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "fleet-ota-secret-key-change-in-production")
    FIRMWARE_DIR = Path(os.environ.get("FIRMWARE_DIR", BASE_DIR / "firmware")).resolve()
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 4 * 1024 * 1024))  # 4 MB default
    ESP32_MAGIC_BYTE = 0xE9
