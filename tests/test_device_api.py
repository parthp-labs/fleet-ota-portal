import io
import zlib
from app.storage import save_firmware_file, generate_api_key

def test_check_update_unauthorized(client):
    # No header
    res1 = client.get("/api/v1/check-update?current_version=1")
    assert res1.status_code == 401
    assert res1.json["error"] == "Unauthorized"

    # Malformed header (not Bearer)
    res2 = client.get("/api/v1/check-update?current_version=1", headers={"Authorization": "Basic 1234"})
    assert res2.status_code == 401

    # Malformed token (not 64 hex)
    res3 = client.get("/api/v1/check-update?current_version=1", headers={"Authorization": "Bearer invalid_key"})
    assert res3.status_code == 401

def test_check_update_not_found(client):
    # Valid 64-hex token, but not registered
    unregistered_key = "b" * 64
    res = client.get(
        "/api/v1/check-update?current_version=1",
        headers={"Authorization": f"Bearer {unregistered_key}"}
    )
    assert res.status_code == 404
    assert res.json["error"] == "Not Found"

def test_check_update_invalid_query_params(client, firmware_dir, make_esp32_bin):
    key = generate_api_key()
    save_firmware_file(io.BytesIO(make_esp32_bin(b"FW")), key, firmware_dir, version=1)

    # Missing current_version
    res1 = client.get("/api/v1/check-update", headers={"Authorization": f"Bearer {key}"})
    assert res1.status_code == 400

    # Non-integer current_version
    res2 = client.get("/api/v1/check-update?current_version=abc", headers={"Authorization": f"Bearer {key}"})
    assert res2.status_code == 400

def test_check_update_success(client, firmware_dir, make_esp32_bin):
    key = generate_api_key()
    fw_bytes = make_esp32_bin(b"DEVICE_FIRMWARE_V2")
    crc = zlib.crc32(fw_bytes) & 0xFFFFFFFF
    save_firmware_file(io.BytesIO(fw_bytes), key, firmware_dir, version=2)

    # Case 1: Device is at v1, server is at v2 -> update available
    res1 = client.get(
        "/api/v1/check-update?current_version=1",
        headers={"Authorization": f"Bearer {key}"}
    )
    assert res1.status_code == 200
    assert res1.json == {
        "update_available": True,
        "version": 2,
        "crc32": crc
    }

    # Case 2: Device is at v2, server is at v2 -> no update available
    res2 = client.get(
        "/api/v1/check-update?current_version=2",
        headers={"Authorization": f"Bearer {key}"}
    )
    assert res2.status_code == 200
    assert res2.json == {
        "update_available": False,
        "version": 2,
        "crc32": crc
    }

    # Case 3: Device is at v3, server is at v2 -> no update available
    res3 = client.get(
        "/api/v1/check-update?current_version=3",
        headers={"Authorization": f"Bearer {key}"}
    )
    assert res3.status_code == 200
    assert res3.json["update_available"] is False

def test_download_firmware_unauthorized(client):
    res = client.get("/api/v1/download-firmware")
    assert res.status_code == 401

def test_download_firmware_not_found(client):
    unregistered_key = "c" * 64
    res = client.get(
        "/api/v1/download-firmware",
        headers={"Authorization": f"Bearer {unregistered_key}"}
    )
    assert res.status_code == 404

def test_download_firmware_success(client, firmware_dir, make_esp32_bin):
    key = generate_api_key()
    fw_bytes = make_esp32_bin(b"RAW_BINARY_DATA_FOR_ESP32")
    save_firmware_file(io.BytesIO(fw_bytes), key, firmware_dir, version=1)

    res = client.get(
        "/api/v1/download-firmware",
        headers={"Authorization": f"Bearer {key}"}
    )
    assert res.status_code == 200
    assert res.data == fw_bytes
    assert res.mimetype == "application/octet-stream"
    assert "attachment" in res.headers.get("Content-Disposition", "")

def test_check_update_case_insensitive_key(client, firmware_dir, make_esp32_bin):
    key = generate_api_key()
    fw_bytes = make_esp32_bin(b"FW_BYTES")
    save_firmware_file(io.BytesIO(fw_bytes), key, firmware_dir, version=1)

    # Send key with uppercase letters
    upper_key = key.upper()
    res = client.get(
        "/api/v1/check-update?current_version=0",
        headers={"Authorization": f"Bearer {upper_key}"}
    )
    assert res.status_code == 200
    assert res.json["update_available"] is True

