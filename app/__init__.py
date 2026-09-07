from pathlib import Path
from flask import Flask, jsonify, request, render_template, flash
from werkzeug.exceptions import RequestEntityTooLarge
from app.config import Config
from app.logging_config import setup_logging

def create_app(test_config=None):
    """Application factory for the ESP32 Fleet OTA Platform."""
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    # Ensure firmware storage directory exists
    firmware_dir = Path(app.config["FIRMWARE_DIR"])
    firmware_dir.mkdir(parents=True, exist_ok=True)

    # Setup security logging filter
    setup_logging(app)

    # Register blueprints
    from app.portal.routes import portal_bp
    from app.api.routes import device_api_bp

    app.register_blueprint(portal_bp)
    app.register_blueprint(device_api_bp)

    # Handle 413 Payload Too Large nicely for both JSON API and web forms
    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(e):
        max_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        if request.path.startswith("/api/"):
            return jsonify({
                "error": "Payload Too Large",
                "message": f"Uploaded firmware exceeds maximum allowed size of {max_mb}MB."
            }), 413
        flash(f"Uploaded file exceeds the maximum allowed size of {max_mb}MB.", "error")
        return render_template("upload.html"), 413

    return app
