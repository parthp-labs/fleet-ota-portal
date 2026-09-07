import logging
import re

HEX64_REGEX = re.compile(r'\b[0-9a-fA-F]{64}\b')
BEARER_REGEX = re.compile(r'(Bearer\s+)[0-9a-zA-Z\-_.~+/=]+', re.IGNORECASE)

class RedactingFilter(logging.Filter):
    """Filter that strips out 64-character hex tokens and Bearer credentials from all log messages."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = HEX64_REGEX.sub('[REDACTED_KEY]', record.msg)
            record.msg = BEARER_REGEX.sub(r'\1[REDACTED_KEY]', record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: HEX64_REGEX.sub('[REDACTED_KEY]', v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    HEX64_REGEX.sub('[REDACTED_KEY]', a) if isinstance(a, str) else a
                    for a in record.args
                )
        return True

def setup_logging(app):
    """Configure logging with security redaction filter."""
    redacting_filter = RedactingFilter()
    app.logger.addFilter(redacting_filter)
    
    # Also attach to werkzeug logger
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.addFilter(redacting_filter)
    
    # Attach to root logger handlers to catch any console logs
    for handler in logging.root.handlers:
        handler.addFilter(redacting_filter)
