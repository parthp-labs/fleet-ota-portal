import io
import zlib
import pytest
from app.storage import (
    is_valid_api_key,
    normalize_api_key,
    generate_api_key,
    get_firmware_paths,
    device_exists,
    read_metadata,
    atomic_write_json,
    save_firmware_file,
    InvalidKeyError,
    InvalidFirmwareError,
    FileTooLargeError
)

def test_is_valid_api_key():
    valid = "a" * 64
    assert is_valid_api_key(valid) is True
    valid_mixed = ("0123456789abcdefABCDEF" * 3)[:64]
    assert len(valid_mixed) == 64
    assert is_valid_api_key(valid_mixed) is True
    
    # Invalid lengths
    assert is_valid_api_key("a" * 63) is False
    assert is_valid_api_key("a" * 65) is False
    assert is_valid_api_key("") is False
    assert is_valid_api_key(None) is False
    
    # Invalid characters
    assert is_valid_api_key("g" * 64) is False
    assert is_valid_api_key("a" * 63 + "$") is False
    assert is_valid_api_key("../" + "a" * 61) is False

def test_normalize_api_key():
    upper_key = "ABCDEF" + "0" * 58
    assert normalize_api_key(upper_key) == "abcdef" + "0" * 58
    
    with pytest.raises(InvalidKeyError):
        normalize_api_key("invalid_key")

def test_generate_api_key():
    key1 = generate_api_key()
    key2 = generate_api_key()
    assert is_valid_api_key(key1)
    assert is_valid_api_key(key2)
    assert key1 != key2
    assert len(key1) == 64
    assert key1 == key1.lower()

def test_get_firmware_paths_traversal_prevention(firmware_dir):
    with pytest.raises(InvalidKeyError):
        get_firmware_paths("../../etc/passwd", firmware_dir)
        
    with pytest.raises(InvalidKeyError):
        get_firmware_paths("..%2f..%2fetc%2fpasswd", firmware_dir)

    valid_key = "f" * 64
    bin_path, json_path = get_firmware_paths(valid_key, firmware_dir)
    assert bin_path == firmware_dir / f"{valid_key}.bin"
    assert json_path == firmware_dir / f"{valid_key}.json"

def test_atomic_write_and_read_metadata(firmware_dir):
    valid_key = "1" * 64
    _, json_path = get_firmware_paths(valid_key, firmware_dir)
    data = {"version": 3, "crc32": 123456, "uploaded_at": "2026-09-05T12:00:00Z"}
    
    atomic_write_json(json_path, data)
    assert device_exists(valid_key, firmware_dir) is True
    
    loaded = read_metadata(valid_key, firmware_dir)
    assert loaded == data

def test_save_firmware_file_valid(firmware_dir, make_esp32_bin):
    key = generate_api_key()
    content = make_esp32_bin(b"HELLO_OTA")
    expected_crc = zlib.crc32(content) & 0xFFFFFFFF
    
    file_obj = io.BytesIO(content)
    meta = save_firmware_file(file_obj, key, firmware_dir, version=1)
    
    assert meta["version"] == 1
    assert meta["crc32"] == expected_crc
    
    bin_path, json_path = get_firmware_paths(key, firmware_dir)
    assert bin_path.is_file()
    assert json_path.is_file()
    assert bin_path.read_bytes() == content

def test_save_firmware_file_invalid_magic_byte(firmware_dir):
    key = generate_api_key()
    bad_content = b"\x00\x01\x02\x03"
    file_obj = io.BytesIO(bad_content)
    
    with pytest.raises(InvalidFirmwareError) as exc_info:
        save_firmware_file(file_obj, key, firmware_dir, version=1)
    assert "magic byte" in str(exc_info.value).lower()

def test_save_firmware_file_empty(firmware_dir):
    key = generate_api_key()
    file_obj = io.BytesIO(b"")
    
    with pytest.raises(InvalidFirmwareError) as exc_info:
        save_firmware_file(file_obj, key, firmware_dir, version=1)
    assert "empty" in str(exc_info.value).lower()

def test_save_firmware_file_too_large(firmware_dir, make_esp32_bin):
    key = generate_api_key()
    content = make_esp32_bin(b"A" * 2048)
    file_obj = io.BytesIO(content)
    
    with pytest.raises(FileTooLargeError):
        save_firmware_file(file_obj, key, firmware_dir, version=1, max_size=1024)
