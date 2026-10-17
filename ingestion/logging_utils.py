"""Minimal logger setup shared by ingestion scripts, independent from backend/app.

The credential-masking pieces below deliberately duplicate backend/app/core/logging.py instead of
importing it, to keep this package free of any dependency on the backend. Keep the two in step.
"""
import logging
import os
import re

DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


NOISY_THIRD_PARTY_LOGGERS = ["pdfminer", "pdfplumber", "PIL", "httpx", "httpcore"]

# Held at WARNING in every environment because they write credentials into the log: hpack/h2
# log HTTP/2 header values at DEBUG (an `apikey` header included), and httpx logs each request's
# full URL at INFO - which carries the Gemini API key as `?key=` (embedding_client.py,
# ocr_fallback.py). httpx/httpcore were already silenced above as noise; hpack and h2 were not.
CREDENTIAL_LEAKING_LOGGERS = ["hpack", "h2", "httpcore", "httpx"]

_REDACTED = "<REDACTED>"
_REDACTIONS = (
    (re.compile(r"""(?i)(b?['"]?(?:apikey|api-key|x-api-key|authorization)['"]?\s*(?:[:=]|,)\s*b?['"]?)"""
                r"""(?:bearer\s+)?[^'"\s,)}\]]+"""), r"\1" + _REDACTED),
    (re.compile(r"(?i)([?&](?:key|apikey|api_key|access_token|token)=)[^&\s'\"]+"), r"\1" + _REDACTED),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer " + _REDACTED),
    (re.compile(r"sb_secret_[A-Za-z0-9_-]+"), "sb_secret_" + _REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"), _REDACTED),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), _REDACTED),
)


def redact_secrets(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _redact_arg(value):  # noqa: ANN001, ANN202 - any log argument
    """Numbers, booleans and None pass through untouched (formatters may depend on their type, e.g.
    uvicorn's int(status_code)); anything else is replaced by its masked string form only if
    masking actually changed it, so ordinary arguments keep their original type."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    masked = redact_secrets(text)
    return value if masked == text else masked


def _redact_args(args):  # noqa: ANN001, ANN202 - LogRecord.args: tuple, mapping or None
    if isinstance(args, tuple):
        return tuple(_redact_arg(a) for a in args)
    if isinstance(args, dict):
        return {k: _redact_arg(v) for k, v in args.items()}
    return args


class SecretRedactingFilter(logging.Filter):
    """Masks credentials in the formatted message and any traceback. See
    backend/app/core/logging.py for why it sits on handlers, not loggers."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Mask the format string and each argument separately, keeping the arguments' types.
        # Collapsing the record to a pre-formatted string (args=None) is NOT safe as the default:
        # uvicorn's access-log formatter unpacks record.args into its five fields, and every access
        # line then failed with "--- Logging error ---" (found by this module's own test run).
        try:
            original = record.getMessage()
        except Exception:  # noqa: BLE001 - malformed record: fall through to the flattening path
            original = None
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        record.args = _redact_args(record.args)
        if original is not None:
            try:
                masked = record.getMessage()
            except Exception:  # noqa: BLE001
                masked = None
            # A credential split across the format string and an argument (e.g. "apikey: %s" with
            # a bare value) is only recognisable in the joined text - flatten in that case only.
            if masked is None or masked != redact_secrets(original):
                record.msg, record.args = redact_secrets(original), None
        else:
            record.msg, record.args = redact_secrets(str(record.msg)), None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_secrets(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_secrets(record.stack_info)
        return True


def configure_logging() -> None:
    environment = os.getenv("ENVIRONMENT", "development")
    level = logging.DEBUG if environment == "development" else logging.INFO
    logging.basicConfig(level=level, format=DEFAULT_LOG_FORMAT)

    for logger_name in NOISY_THIRD_PARTY_LOGGERS + CREDENTIAL_LEAKING_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, SecretRedactingFilter) for f in handler.filters):
            handler.addFilter(SecretRedactingFilter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
