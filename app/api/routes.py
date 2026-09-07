from flask import Blueprint, request, jsonify, send_file, current_app
from app.api.auth import require_device_auth
from app.storage import get_firmware_paths

device_api_bp = Blueprint("device_api", __name__, url_prefix="/api/v1")


@device_api_bp.route("/check-update", methods=["GET"])
@require_device_auth
def check_update(api_key, metadata):
    """
    Check if a firmware update is available for the authenticated device.
    Query params:
        current_version (int): The firmware version currently running on the device.
    """
    current_version_str = request.args.get("current_version")
    if current_version_str is None:
        return jsonify({
            "error": "Bad Request",
            "message": "Missing required query parameter 'current_version'."
        }), 400

    try:
        print(current_version_str)
        current_version = int(current_version_str)
    except (ValueError, TypeError):
        return jsonify({
            "error": "Bad Request",
            "message": "Query parameter 'current_version' must be an integer."
        }), 400

    stored_version = metadata.get("version", 0)
    stored_crc32 = metadata.get("crc32", 0)
    update_available = stored_version > current_version

    return jsonify({
        "update_available": update_available,
        "version": stored_version,
        "crc32": stored_crc32
    }), 200


@device_api_bp.route("/download-firmware", methods=["GET"])
@require_device_auth
def download_firmware(api_key, metadata):
    """
    Stream raw bytes of the firmware binary for the authenticated device.
    The file served is determined strictly and exclusively by the Bearer token API key.
    """
    firmware_dir = current_app.config["FIRMWARE_DIR"]
    bin_path, _ = get_firmware_paths(api_key, firmware_dir)

    if not bin_path.is_file():
        return jsonify({
            "error": "Not Found",
            "message": "Firmware binary file not found on server."
        }), 404

    # send_file streams the file directly in chunks without buffering entire content in memory
    return send_file(
        bin_path,
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=f"firmware_v{metadata.get('version', 1)}.bin"
    )
