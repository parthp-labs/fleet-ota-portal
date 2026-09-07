import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")
    print(f"Starting ESP32 Fleet OTA Platform on http://{host}:{port}")
    print(f"Firmware storage directory: {app.config['FIRMWARE_DIR']}")
    app.run(host=host, port=port, debug=debug)
