import io
import pytest
from app import create_app

@pytest.fixture
def firmware_dir(tmp_path):
    """Temporary directory for firmware files."""
    fw_dir = tmp_path / "firmware"
    fw_dir.mkdir(parents=True, exist_ok=True)
    return fw_dir

@pytest.fixture
def app(firmware_dir):
    """Flask test application configured with temporary storage."""
    app = create_app({
        "TESTING": True,
        "FIRMWARE_DIR": firmware_dir,
        "MAX_CONTENT_LENGTH": 1024 * 1024,  # 1MB for fast testing
        "SECRET_KEY": "test-secret-key"
    })
    return app

@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()

@pytest.fixture
def make_esp32_bin():
    """Helper to create fake ESP32 binary data starting with magic byte 0xE9."""
    def _maker(payload=b"OTA_FIRMWARE_PAYLOAD_V1", magic=0xE9):
        return bytes([magic]) + payload
    return _maker
