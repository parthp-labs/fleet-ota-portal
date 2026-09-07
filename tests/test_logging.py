import logging
from app.logging_config import RedactingFilter

def test_redacting_filter_replaces_hex64_and_bearer():
    filter_instance = RedactingFilter()
    dummy_key = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    
    # Test record message containing hex key
    record1 = logging.LogRecord(
        name="test", level=logging.INFO, pathname="test.py", lineno=1,
        msg=f"Device registered with key {dummy_key}", args=(), exc_info=None
    )
    filter_instance.filter(record1)
    assert dummy_key not in record1.msg
    assert "[REDACTED_KEY]" in record1.msg

    # Test record with Bearer authorization
    record2 = logging.LogRecord(
        name="test", level=logging.INFO, pathname="test.py", lineno=1,
        msg=f"Received Authorization: Bearer {dummy_key}", args=(), exc_info=None
    )
    filter_instance.filter(record2)
    assert dummy_key not in record2.msg
    assert "Bearer [REDACTED_KEY]" in record2.msg
