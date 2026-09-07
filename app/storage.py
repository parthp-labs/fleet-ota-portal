import json
import os
import re
import secrets
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

HEX64_REGEX = re.compile(r'^[0-9a-fA-F]{64}$')

class StorageError(Exception):
    """Base storage error."""
    pass

class InvalidKeyError(StorageError):
    """Raised when an API key does not match the 64-character hex format."""
    pass

class DeviceNotFoundError(StorageError):
    """Raised when an API key is not found on disk."""
    pass

class InvalidFirmwareError(StorageError):
    """Raised when the uploaded firmware is invalid (magic byte mismatch or empty)."""
    pass

class FileTooLargeError(StorageError):
    """Raised when uploaded file exceeds maximum allowed size."""
    pass


def is_valid_api_key(key: Optional[str]) -> bool:
    """Check if the provided key is exactly 64 hex characters."""
    if not key or not isinstance(key, str):
        return False
    return bool(HEX64_REGEX.match(key.strip()))


def normalize_api_key(key: str) -> str:
    """Validate and normalize an API key to lowercase 64 hex characters."""
    if not is_valid_api_key(key):
        raise InvalidKeyError("API key must be exactly 64 hexadecimal characters.")
    return key.strip().lower()


def generate_api_key() -> str:
    """Generate a cryptographically random 64-hex-character API key using secrets."""
    return secrets.token_hex(32)


def get_firmware_paths(key: str, firmware_dir: Path) -> Tuple[Path, Path]:
    """
    Get the .bin and .json paths for an API key.
    Strictly validates key format before returning paths to prevent path traversal.
    """
    norm_key = normalize_api_key(key)
    bin_path = (firmware_dir / f"{norm_key}.bin").resolve()
    json_path = (firmware_dir / f"{norm_key}.json").resolve()
    
    # Extra safety check against directory traversal
    resolved_dir = firmware_dir.resolve()
    if bin_path.parent != resolved_dir or json_path.parent != resolved_dir:
        raise InvalidKeyError("Path traversal attempt detected.")
        
    return bin_path, json_path


def device_exists(key: str, firmware_dir: Path) -> bool:
    """Check whether a valid device metadata file exists on disk."""
    if not is_valid_api_key(key):
        return False
    try:
        _, json_path = get_firmware_paths(key, firmware_dir)
        return json_path.is_file()
    except (InvalidKeyError, OSError):
        return False


def read_metadata(key: str, firmware_dir: Path) -> Optional[Dict[str, Any]]:
    """Read device sidecar JSON metadata safely."""
    _, json_path = get_firmware_paths(key, firmware_dir)
    if not json_path.is_file():
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def atomic_write_json(target_path: Path, data: Dict[str, Any]) -> None:
    """Write dictionary to JSON atomically using a temp file in the same directory."""
    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    
    temp_file = tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8")
    temp_name = temp_file.name
    try:
        json.dump(data, temp_file, indent=2)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        os.replace(temp_name, target_path)
    except Exception:
        temp_file.close()
        if os.path.exists(temp_name):
            os.remove(temp_name)
        raise


def save_firmware_file(
    file_storage,
    key: str,
    firmware_dir: Path,
    version: int,
    max_size: int = 4 * 1024 * 1024,
    magic_byte: int = 0xE9
) -> Dict[str, Any]:
    """
    Validates and writes uploaded firmware binary and its sidecar metadata.
    
    - Validates magic byte (0xE9 for ESP32)
    - Validates max file size
    - Computes CRC32
    - Performs atomic file replacement for both .bin and .json
    """
    bin_path, json_path = get_firmware_paths(key, firmware_dir)
    firmware_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Validate magic byte (first byte)
    first_byte = file_storage.read(1)
    if not first_byte:
        raise InvalidFirmwareError("Uploaded file is empty.")
    if first_byte[0] != magic_byte:
        raise InvalidFirmwareError(
            f"Invalid firmware: First byte is 0x{first_byte[0]:02X}, but expected ESP32 magic byte 0x{magic_byte:02X}."
        )
    
    # Rewind to start
    file_storage.seek(0)
    
    # 2. Stream to a temporary binary file, calculating CRC32 and enforcing max_size
    temp_bin = tempfile.NamedTemporaryFile("wb", dir=firmware_dir, delete=False)
    temp_bin_name = temp_bin.name
    total_bytes = 0
    crc = 0
    
    try:
        while True:
            chunk = file_storage.read(65536)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_size:
                raise FileTooLargeError(
                    f"File size exceeds maximum allowed limit of {max_size // (1024 * 1024)} MB."
                )
            crc = zlib.crc32(chunk, crc)
            temp_bin.write(chunk)
            
        temp_bin.flush()
        os.fsync(temp_bin.fileno())
        temp_bin.close()
        
        # Atomically replace destination .bin
        os.replace(temp_bin_name, bin_path)
    except Exception:
        temp_bin.close()
        if os.path.exists(temp_bin_name):
            os.remove(temp_bin_name)
        raise

    # 3. Write sidecar JSON atomically
    metadata = {
        "version": int(version),
        "crc32": int(crc & 0xFFFFFFFF),
        "uploaded_at": datetime.now(timezone.utc).isoformat()
    }
    atomic_write_json(json_path, metadata)
    
    return metadata
