from flask import Blueprint, render_template, request, flash, current_app
from app.storage import (
    generate_api_key,
    is_valid_api_key,
    normalize_api_key,
    device_exists,
    read_metadata,
    save_firmware_file,
    list_existing_firmwares,
    StorageError,
    InvalidKeyError,
    InvalidFirmwareError,
    FileTooLargeError
)

portal_bp = Blueprint("portal", __name__, template_folder="templates")

@portal_bp.route("/", methods=["GET"])
def index():
    """Render the firmware upload portal."""
    prefill_key = request.args.get("prefill_key", "")
    firmware_dir = current_app.config["FIRMWARE_DIR"]
    server_devices = list_existing_firmwares(firmware_dir)
    return render_template("upload.html", prefill_key=prefill_key, server_devices=server_devices)


@portal_bp.route("/upload", methods=["POST"])
def upload():
    firmware_dir = current_app.config["FIRMWARE_DIR"]
    max_size = current_app.config["MAX_CONTENT_LENGTH"]
    magic_byte = current_app.config["ESP32_MAGIC_BYTE"]

    if "firmware_file" not in request.files:
        flash("No firmware file was submitted.", "error")
        return render_template("upload.html"), 400

    uploaded_file = request.files["firmware_file"]
    if not uploaded_file or not uploaded_file.filename:
        flash("Please select a firmware (.bin) file to upload.", "error")
        return render_template("upload.html"), 400

    raw_key = request.form.get("api_key", "").strip()

    # Registering a new device
    if not raw_key:
        api_key = generate_api_key()
        try:
            metadata = save_firmware_file(
                file_storage=uploaded_file,
                key=api_key,
                firmware_dir=firmware_dir,
                version=1,
                max_size=max_size,
                magic_byte=magic_byte,
                filename=uploaded_file.filename
            )
        except (InvalidFirmwareError, FileTooLargeError) as e:
            flash(str(e), "error")
            return render_template("upload.html"), 400
        except StorageError as e:
            flash(f"Storage error: {e}", "error")
            return render_template("upload.html"), 500

        return render_template(
            "new_device.html",
            api_key=api_key,
            metadata=metadata,
            filename=uploaded_file.filename
        )

    # Updating an existing device
    if not is_valid_api_key(raw_key):
        flash("Invalid API key format. Expected 64 hexadecimal characters.", "error")
        return render_template("upload.html", prefill_key=raw_key), 400

    api_key = normalize_api_key(raw_key)

    if not device_exists(api_key, firmware_dir):
        flash(
            "Unrecognized API key. No existing device was found for this key. "
            "Leave the API key field blank to register a new device.",
            "error"
        )
        return render_template("upload.html", prefill_key=api_key), 404

    existing_metadata = read_metadata(api_key, firmware_dir)
    if not existing_metadata:
        flash("Device metadata is missing or corrupted.", "error")
        return render_template("upload.html", prefill_key=api_key), 500

    next_version = existing_metadata.get("version", 0) + 1

    try:
        metadata = save_firmware_file(
            file_storage=uploaded_file,
            key=api_key,
            firmware_dir=firmware_dir,
            version=next_version,
            max_size=max_size,
            magic_byte=magic_byte,
            filename=uploaded_file.filename
        )
    except (InvalidFirmwareError, FileTooLargeError) as e:
        flash(str(e), "error")
        return render_template("upload.html", prefill_key=api_key), 400
    except StorageError as e:
        flash(f"Storage error: {e}", "error")
        return render_template("upload.html", prefill_key=api_key), 500

    return render_template("update_device.html", metadata=metadata)
