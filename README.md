# ESP32 Fleet OTA Firmware Platform

A lightweight, database-free Over-The-Air (OTA) firmware deployment platform for ESP32 fleets built with Flask.

## Core Architecture & Security Model

- **Zero-Knowledge / Database-Free**: No user accounts, passwords, or SQL databases.
- **Cryptographic Device Identity**: Each device is identified purely by a 256-bit cryptographically random API key (64 hex characters generated via Python's `secrets.token_hex(32)`).
- **Hard Access Boundary**: A device presents its embedded API key in an `Authorization: Bearer <api_key>` header. Because firmware files are stored keyed directly to this token, a device can never access or query firmware belonging to any other device.
- **Atomic Filesystem Storage**: State lives entirely in a single directory (`firmware/`):
  - `firmware/<api_key>.bin`: The current firmware binary for that device.
  - `firmware/<api_key>.json`: Sidecar metadata:
    ```json
    {
      "version": 1,
      "crc32": 2847192842,
      "uploaded_at": "2026-09-05T10:15:30.123456+00:00"
    }
    ```
  All writes to sidecar files and binaries are written to temporary files within the same filesystem directory and atomically renamed into place (`os.replace`) to prevent file corruption or partial reads.
- **Strict Path Traversal Protection**: API keys are validated strictly against `^[0-9a-f]{64}$` before any filesystem lookup.
- **Log Privacy**: Built-in logging redaction automatically scrubs 64-hex keys and `Authorization: Bearer` credentials from console output and server logs.

---

## Directory Structure

```text
fleet-ota-platform/
├── app/
│   ├── __init__.py           # Flask app factory with blueprint registration & 413 error handlers
│   ├── config.py             # Configuration (FIRMWARE_DIR, MAX_CONTENT_LENGTH, MAGIC_BYTE)
│   ├── logging_config.py     # Logging filter to redact API keys and Bearer tokens
│   ├── storage.py            # Filesystem manager: atomic writes, CRC32, magic byte check
│   ├── portal/               # Human-Facing Web Upload Portal Blueprint
│   │   ├── routes.py         # Routes: GET /, POST /upload
│   │   └── templates/        # Jinja2 templates (Bootstrap 5)
│   │       ├── base.html
│   │       ├── upload.html
│   │       ├── new_device.html
│   │       └── update_device.html
│   └── api/                  # ESP32 Device-Facing API Blueprint (/api/v1)
│       ├── auth.py           # Bearer token verification decorator
│       └── routes.py         # Routes: /check-update, /download-firmware
├── firmware/                 # Local filesystem storage for binaries and JSON sidecars
├── tests/                    # Automated Pytest suite (25 tests covering all flows)
│   ├── conftest.py
│   ├── test_storage.py
│   ├── test_portal.py
│   ├── test_device_api.py
│   └── test_logging.py
├── pytest.ini
├── requirements.txt
├── run.py                    # Server entrypoint
└── README.md
```

---

## Getting Started

### Prerequisites
- Python 3.10+ (tested on Python 3.12)
- `pip`

### 1. Installation

```bash
# Clone or navigate to the repository directory
cd fleet-ota-platform

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration Options (Environment Variables)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `5000` | Port to bind Flask server |
| `HOST` | `0.0.0.0` | Host interface |
| `FIRMWARE_DIR` | `./firmware` | Directory where `.bin` and `.json` sidecars are stored |
| `MAX_CONTENT_LENGTH` | `4194304` (4MB) | Maximum allowed firmware binary upload size in bytes |
| `SECRET_KEY` | *(Built-in default)* | Flask session secret for flash messages |

### 3. Running the Server

```bash
# Activate virtual environment
source .venv/bin/activate

# Run server
python run.py
```

The portal will be accessible at:
- Web Portal: [http://localhost:5000](http://localhost:5000)
- Device API: [http://localhost:5000/api/v1](http://localhost:5000/api/v1)

### 4. Running the Automated Test Suite

```bash
pytest -v
```

---

## Web Portal Walkthrough

Open [http://localhost:5000](http://localhost:5000) in your web browser.

### Flow A: Registering a New Device
1. Select a compiled ESP32 firmware binary (`.bin`).
2. Leave the **"Existing API key"** field **blank**.
3. Click **"Upload and Deploy Firmware"**.
4. The server:
   - Validates that the file starts with the ESP32 magic byte `0xE9`.
   - Generates a cryptographically random 64-hex API key using `secrets.token_hex(32)`.
   - Computes the unsigned 32-bit CRC32 checksum.
   - Atomically saves `firmware/<key>.bin` and `firmware/<key>.json` with `version: 1` and initializes a `history` timeline.
   - Presents a confirmation screen displaying the **API key** prominently with a one-click copy button.
   - **Local Storage Persistence:** Automatically saves the API key, version, filename, and CRC32 to the browser's `localStorage` so you never lose the key.

### Flow B: Pushing an Update to an Existing Device
1. Select the new compiled ESP32 firmware binary (`.bin`).
2. Paste the device's **64-hexadecimal API key** into the "Existing API key" field (or click **"Update"** next to the device in the Local History table).
3. Click **"Upload and Deploy Firmware"**.
4. The server:
   - Strictly validates the key format against `^[0-9a-f]{64}$` before touching the disk.
   - Checks if `firmware/<key>.json` exists. If not, it immediately rejects the upload with a `404` error (preventing users from creating arbitrary keys).
   - Increments the existing version number by 1 (`v(N) -> v(N+1)`).
   - Validates the magic byte `0xE9` and max size.
   - Computes the new CRC32.
   - Appends to the revision `history` list in `firmware/<key>.json`.
   - Atomically overwrites `firmware/<key>.bin` and `firmware/<key>.json`.
   - Shows a confirmation page displaying the new version number and CRC32.
   - **Local Storage Update:** Automatically updates the device's record and revision history in the browser's `localStorage`.

### Local Storage & Fleet History
The web portal includes an interactive **Uploaded Firmwares & Local History** dashboard stored directly in your browser:
- **Device Nicknames**: Rename or label devices (e.g. "Office Sensor") for easy recognition.
- **Revision Timeline**: View the full revision history of any device (all versions, filenames, CRC32 checksums, and deployment timestamps).
- **One-Click Actions**:
  - **Update**: Prefills the upload form with the device's API key.
  - **Check Status**: Queries the live server endpoint to verify device connectivity and whether an update is available.
  - **Download Binary**: Directly downloads the active firmware binary.
- **Export & Import Backup**: Easily export your saved devices and keys to a JSON file to transfer between browsers or create backups.

---

## Device-Facing API Reference

All device API requests must be authenticated using HTTP Bearer token authorization:

```http
Authorization: Bearer <64_HEX_API_KEY>
```

### 1. Check for Available Update

Checks if a newer firmware version exists for the device.

```http
GET /api/v1/check-update?current_version=<int>
```

#### Query Parameters
- `current_version` (*integer*, required): The integer version currently running on the ESP32 device.

#### Example Request (`curl`)
```bash
curl -i -X GET "http://localhost:5000/api/v1/check-update?current_version=1" \
     -H "Authorization: Bearer 8f14e45fceea167a5a36dedd4bea2543265882b716f9f3ffb4a6dff56561f5ff"
```

#### Responses

- **`200 OK` (Update Available)**
  ```json
  {
    "update_available": true,
    "version": 2,
    "crc32": 3154817441
  }
  ```

- **`200 OK` (Already Up to Date)**
  ```json
  {
    "update_available": false,
    "version": 1,
    "crc32": 3154817441
  }
  ```

- **`400 Bad Request` (Missing or Non-Integer `current_version`)**
  ```json
  {
    "error": "Bad Request",
    "message": "Query parameter 'current_version' must be an integer."
  }
  ```

- **`401 Unauthorized` (Missing or Malformed Authorization Header)**
  ```json
  {
    "error": "Unauthorized",
    "message": "Missing Authorization header. Expected format: 'Authorization: Bearer <64-hex-key>'."
  }
  ```

- **`404 Not Found` (Unrecognized Key)**
  ```json
  {
    "error": "Not Found",
    "message": "Unrecognized API key. No device is registered with this key."
  }
  ```

---

### 2. Download Firmware Binary

Streams the raw binary bytes of the device's firmware.

```http
GET /api/v1/download-firmware
```

> **Security Note:** This endpoint does **not** accept any filename or device query parameters. The binary file returned is determined solely by the API key presented in the `Authorization` header.

#### Example Request (`curl`)
```bash
curl -X GET "http://localhost:5000/api/v1/download-firmware" \
     -H "Authorization: Bearer 8f14e45fceea167a5a36dedd4bea2543265882b716f9f3ffb4a6dff56561f5ff" \
     --output firmware_update.bin
```

#### Responses

- **`200 OK`**:
  - `Content-Type: application/octet-stream`
  - `Content-Disposition: attachment; filename=firmware_v2.bin`
  - Raw binary stream (transferred in chunks without loading entire binary into server RAM).
- **`401 Unauthorized`**: If Authorization header is missing or malformed.
- **`404 Not Found`**: If the device key is not registered or binary does not exist.

---

## ESP32 Arduino Implementation Example

Below is a complete, production-ready Arduino C++ example using `HTTPClient` and `HTTPUpdate` for ESP32.

```cpp
#include <WiFi.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <ArduinoJson.h>

const char* ssid          = "YOUR_WIFI_SSID";
const char* password      = "YOUR_WIFI_PASSWORD";

// Server configuration
const char* server_base   = "http://192.168.1.100:5000";
const char* device_api_key = "PASTE_YOUR_64_HEX_API_KEY_HERE";

// Current firmware version embedded in this build
const int CURRENT_VERSION = 1;

void checkAndApplyUpdate() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi not connected. Skipping update check.");
        return;
    }

    WiFiClient client;
    HTTPClient http;

    // 1. Check for update
    String checkUrl = String(server_base) + "/api/v1/check-update?current_version=" + String(CURRENT_VERSION);
    http.begin(client, checkUrl);
    http.addHeader("Authorization", String("Bearer ") + device_api_key);

    int httpCode = http.GET();
    if (httpCode == HTTP_CODE_OK) {
        String payload = http.getString();
        StaticJsonDocument<256> doc;
        DeserializationError err = deserializeJson(doc, payload);

        if (!err) {
            bool updateAvailable = doc["update_available"];
            int latestVersion    = doc["version"];
            uint32_t expectedCrc = doc["crc32"];

            Serial.printf("Current Version: %d, Latest Version: %d, Update Available: %s\n",
                          CURRENT_VERSION, latestVersion, updateAvailable ? "YES" : "NO");

            if (updateAvailable) {
                Serial.println("Starting OTA download and flash...");
                http.end();

                // 2. Perform OTA download and flash
                String downloadUrl = String(server_base) + "/api/v1/download-firmware";
                
                // Add Authorization header for download request
                httpUpdate.rebootOnUpdate(true);
                t_httpUpdate_return ret = httpUpdate.update(
                    client,
                    downloadUrl,
                    "",
                    [&](HTTPClient *updateHttp) {
                        updateHttp->addHeader("Authorization", String("Bearer ") + device_api_key);
                    }
                );

                switch (ret) {
                    case HTTP_UPDATE_FAILED:
                        Serial.printf("HTTP_UPDATE_FAILED Error (%d): %s\n",
                                      httpUpdate.getLastError(), httpUpdate.getLastErrorString().c_str());
                        break;
                    case HTTP_UPDATE_NO_UPDATES:
                        Serial.println("HTTP_UPDATE_NO_UPDATES");
                        break;
                    case HTTP_UPDATE_OK:
                        Serial.println("HTTP_UPDATE_OK! Rebooting...");
                        break;
                }
                return;
            }
        }
    } else {
        Serial.printf("Check update failed, HTTP code: %d\n", httpCode);
    }
    http.end();
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi connected.");

    // Check for OTA update on boot
    checkAndApplyUpdate();
}

void loop() {
    // Check for updates periodically (e.g. once every 6 hours)
    static unsigned long lastCheck = 0;
    if (millis() - lastCheck > 6 * 3600 * 1000UL) {
        lastCheck = millis();
        checkAndApplyUpdate();
    }
    delay(1000);
}
```

---

## Security Verification Checklist

- [x] **Path Traversal**: Keys validated strictly with `^[0-9a-f]{64}$` before accessing the filesystem. Any input like `../../etc/passwd` or `/etc/shadow` fails regex and is rejected immediately.
- [x] **No Account Snooping**: Endpoints accept no device selection arguments. Files are retrieved strictly via the matching Bearer key.
- [x] **No Arbitrary Key Creation**: Uploading with an unknown user-supplied key is rejected with a `404` error; only server-generated keys created via `secrets.token_hex(32)` are accepted.
- [x] **Log Scrubbing**: Active logging filter replaces all 64-hex tokens and Bearer credentials with `[REDACTED_KEY]` to prevent credentials from persisting in system logs.
- [x] **Firmware Magic Byte Check**: Every upload validates that byte 0 is `0xE9` (ESP32 image magic byte) before storing.
