import io
import re
from app.storage import get_firmware_paths, read_metadata

def test_portal_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Firmware Deployment Portal" in response.data
    assert b"firmware_file" in response.data
    assert b"api_key" in response.data

def test_upload_new_device(client, firmware_dir, make_esp32_bin):
    fw_data = make_esp32_bin(b"VERSION_1_CODE")
    data = {
        "firmware_file": (io.BytesIO(fw_data), "firmware.bin"),
        "api_key": ""
    }
    response = client.post("/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Device Registration Successful!" in html
    assert "Save This API Key Immediately!" in html
    
    # Extract generated key from html
    match = re.search(r'id="apiKeyDisplay"[^>]*>\s*([0-9a-f]{64})\s*<', html)
    assert match is not None, "Generated API key was not found in response HTML"
    new_key = match.group(1)
    
    # Check filesystem
    bin_path, json_path = get_firmware_paths(new_key, firmware_dir)
    assert bin_path.is_file()
    assert json_path.is_file()
    assert bin_path.read_bytes() == fw_data
    
    meta = read_metadata(new_key, firmware_dir)
    assert meta["version"] == 1
    assert "crc32" in meta
    assert "uploaded_at" in meta

def test_upload_update_device(client, firmware_dir, make_esp32_bin):
    # 1. First upload a new device
    fw1 = make_esp32_bin(b"VERSION_1")
    res1 = client.post("/upload", data={
        "firmware_file": (io.BytesIO(fw1), "firmware.bin"),
        "api_key": ""
    }, content_type="multipart/form-data")
    assert res1.status_code == 200
    key = re.search(r'id="apiKeyDisplay"[^>]*>\s*([0-9a-f]{64})\s*<', res1.data.decode("utf-8")).group(1)
    
    # 2. Deploy update with the key
    fw2 = make_esp32_bin(b"VERSION_2")
    res2 = client.post("/upload", data={
        "firmware_file": (io.BytesIO(fw2), "firmware_v2.bin"),
        "api_key": key
    }, content_type="multipart/form-data")
    
    assert res2.status_code == 200
    html2 = res2.data.decode("utf-8")
    assert "Firmware Update Succeeded!" in html2
    assert "v2" in html2
    # Ensure API key is NOT re-exposed on confirmation page
    assert key not in html2

    # Check filesystem
    bin_path, _ = get_firmware_paths(key, firmware_dir)
    assert bin_path.read_bytes() == fw2
    meta = read_metadata(key, firmware_dir)
    assert meta["version"] == 2

def test_upload_unrecognized_key_rejected(client, firmware_dir, make_esp32_bin):
    # A valid-format 64-hex key that was never registered
    fake_key = "a" * 64
    fw = make_esp32_bin(b"PAYLOAD")
    response = client.post("/upload", data={
        "firmware_file": (io.BytesIO(fw), "firmware.bin"),
        "api_key": fake_key
    }, content_type="multipart/form-data")
    
    assert response.status_code == 404
    html = response.data.decode("utf-8")
    assert "Unrecognized API key" in html
    
    # Verify no device was created
    _, json_path = get_firmware_paths(fake_key, firmware_dir)
    assert not json_path.exists()

def test_upload_malformed_key_rejected(client, make_esp32_bin):
    fw = make_esp32_bin(b"PAYLOAD")
    response = client.post("/upload", data={
        "firmware_file": (io.BytesIO(fw), "firmware.bin"),
        "api_key": "short_or_invalid_key"
    }, content_type="multipart/form-data")
    
    assert response.status_code == 400
    html = response.data.decode("utf-8")
    assert "Invalid API key format" in html

def test_upload_invalid_magic_byte_rejected(client):
    bad_bin = b"\x00\x11\x22\x33"  # Does not start with 0xE9
    response = client.post("/upload", data={
        "firmware_file": (io.BytesIO(bad_bin), "firmware.bin"),
        "api_key": ""
    }, content_type="multipart/form-data")
    
    assert response.status_code == 400
    html = response.data.decode("utf-8")
    assert "ESP32 magic byte" in html

def test_upload_no_file(client):
    response = client.post("/upload", data={"api_key": ""}, content_type="multipart/form-data")
    assert response.status_code == 400
