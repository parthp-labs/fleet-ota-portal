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
    magic_byte: int = 0xE9,
    filename: Optional[str] = None
) -> Dict[str, Any]:
    bin_path, json_path = get_firmware_paths(key, firmware_dir)
    firmware_dir.mkdir(parents=True, exist_ok=True)

    header = file_storage.read(1)
    if not header:
        raise InvalidFirmwareError("Uploaded file is empty.")
    if header[0] != magic_byte:
        raise InvalidFirmwareError(
            f"Invalid firmware: Expected ESP32 magic byte 0x{magic_byte:02X}, got 0x{header[0]:02X}."
        )

    file_storage.seek(0)

    # Stream chunks to a temp file, computing CRC32 on the fly and enforcing size limit
    temp_bin = tempfile.NamedTemporaryFile("wb", dir=firmware_dir, delete=False)
    temp_name = temp_bin.name
    total_bytes = 0
    crc = 0

    try:
        while chunk := file_storage.read(65536):
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
        os.replace(temp_name, bin_path)
    except Exception:
        temp_bin.close()
        if os.path.exists(temp_name):
            os.remove(temp_name)
        raise

    # Preserve audit history across releases
    existing = read_metadata(key, firmware_dir)
    history = []
    if existing and isinstance(existing.get("history"), list):
        history = list(existing["history"])
    elif existing and "version" in existing:
        history.append({
            "version": existing.get("version"),
            "crc32": existing.get("crc32"),
            "uploaded_at": existing.get("uploaded_at"),
            "filename": existing.get("filename", "firmware.bin")
        })

    now = datetime.now(timezone.utc).isoformat()
    clean_name = Path(filename).name if filename else "firmware.bin"

    history.append({
        "version": int(version),
        "crc32": int(crc & 0xFFFFFFFF),
        "uploaded_at": now,
        "filename": clean_name
    })

    metadata = {
        "version": int(version),
        "crc32": int(crc & 0xFFFFFFFF),
        "uploaded_at": now,
        "filename": clean_name,
        "history": history
    }
    atomic_write_json(json_path, metadata)
    return metadata


def list_existing_firmwares(firmware_dir: Path) -> list:
    """
    List all valid firmware devices currently stored on the filesystem.
    Reads sidecars and returns a list of device dictionaries sorted by uploaded_at descending.
    """
    if not firmware_dir.is_dir():
        return []

    devices = []
    for json_file in firmware_dir.glob("*.json"):
        key = json_file.stem
        if not is_valid_api_key(key):
            continue

        bin_file = firmware_dir / f"{key}.bin"
        if not bin_file.is_file():
            continue

        meta = read_metadata(key, firmware_dir)
        if not meta or not isinstance(meta, dict):
            continue

        size_bytes = 0
        try:
            size_bytes = bin_file.stat().st_size
        except OSError:
            pass

        history = meta.get("history", [])
        if not history and "version" in meta:
            history = [{
                "version": meta.get("version"),
                "crc32": meta.get("crc32"),
                "uploaded_at": meta.get("uploaded_at"),
                "filename": meta.get("filename", f"firmware_{key[:8]}.bin")
            }]

        devices.append({
            "apiKey": key,
            "version": int(meta.get("version", 1)),
            "crc32": int(meta.get("crc32", 0)),
            "uploadedAt": meta.get("uploaded_at", ""),
            "filename": meta.get("filename", f"firmware_{key[:8]}.bin"),
            "sizeBytes": size_bytes,
            "history": history
        })

    # Sort descending by uploadedAt
    devices.sort(key=lambda d: d.get("uploadedAt", ""), reverse=True)
    return devices
