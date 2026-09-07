from functools import wraps
from flask import request, jsonify, current_app
from app.storage import is_valid_api_key, normalize_api_key, device_exists, read_metadata, get_firmware_paths


def require_device_auth(f):
    """
    Decorator for device endpoints requiring Authorization: Bearer <64-hex-api-key>.
    Returns 401 on missing or malformed header/token format.
    Returns 404 if the device key is not found on disk.
    Passes (api_key, metadata) to the decorated view.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        print(request.headers)
        if not auth_header:
            return jsonify({
                "error": "Unauthorized",
                "message": "Missing Authorization header. Expected format: 'Authorization: Bearer <64-hex-key>'."
            }), 401

        parts = auth_header.strip().split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({
                "error": "Unauthorized",
                "message": "Malformed Authorization header. Expected format: 'Authorization: Bearer <64-hex-key>'."
            }), 401

        raw_key = parts[1]
        if not is_valid_api_key(raw_key):
            return jsonify({
                "error": "Unauthorized",
                "message": "Invalid API key format. Expected exactly 64 hexadecimal characters."
            }), 401

        api_key = normalize_api_key(raw_key)
        firmware_dir = current_app.config["FIRMWARE_DIR"]

        if not device_exists(api_key, firmware_dir):
            return jsonify({
                "error": "Not Found",
                "message": "Unrecognized API key. No device is registered with this key."
            }), 404

        metadata = read_metadata(api_key, firmware_dir)
        if metadata is None:
            return jsonify({
                "error": "Not Found",
                "message": "Device metadata is missing or corrupted."
            }), 404

        return f(api_key, metadata, *args, **kwargs)

    return decorated_function
