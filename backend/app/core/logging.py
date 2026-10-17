import logging
import re

DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# Third-party loggers that write request credentials into the log, held at WARNING in EVERY
# environment, development included.
#
# - hpack (and h2 under it) logs each HTTP/2 header it encodes at DEBUG, values included. On
#   2026-10-17 that put the Supabase service-role key on screen from a local development run:
#   `b'apikey'=b'sb_secret_...'`, marked "sensitive:False" by hpack itself.
# - httpx logs every request at INFO as 'HTTP Request: POST <full url> ...'. Every Gemini call
#   used to carry its API key as a query parameter (`?key=...`), so at the INFO level production
#   runs at, each Gemini call wrote the Google API key into the log. The key now travels in the
#   x-goog-api-key header (gemini_client.py), so the URL no longer holds it at all; the logger
#   level and the `key=` / AIza rules below remain as defence in depth.
# - httpcore logs connection and request internals at DEBUG.
#
# WARNING still lets their real failures through (connection errors, protocol violations).
CREDENTIAL_LEAKING_LOGGERS = ("hpack", "h2", "httpcore", "httpx")

# Loggers whose handlers exist before the app is imported (the uvicorn CLI and gunicorn both
# configure logging first), so the redaction filter has to be attached to their handlers too, not
# only to the root logger's.
SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn.error", "gunicorn.access")

_REDACTED = "<REDACTED>"
# Order matters: the header and query-string rules keep their label and replace only the value,
# and must run before the bare-token rules so a value is never half-replaced.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # A credential header in any of the shapes it reaches a log in: plain `apikey: v`, a query
    # or form `apikey=v`, a dict repr `'apikey': 'v'`, and hpack's bytes reprs `b'apikey'=b'v'` and
    # `(b'apikey', b'v')`. Group 1 keeps the name and the punctuation before the value.
    (re.compile(r"""(?i)(b?['"]?(?:x-goog-api-key|apikey|api-key|x-api-key|authorization)['"]?\s*(?:[:=]|,)\s*b?['"]?)"""
                r"""(?:bearer\s+)?[^'"\s,)}\]]+"""), r"\1" + _REDACTED),
    # A credential in a URL query string, e.g. Gemini's ?key=...
    (re.compile(r"(?i)([?&](?:key|apikey|api_key|access_token|token)=)[^&\s'\"]+"), r"\1" + _REDACTED),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer " + _REDACTED),
    (re.compile(r"sb_secret_[A-Za-z0-9_-]+"), "sb_secret_" + _REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"), _REDACTED),  # any JWT
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), _REDACTED),  # Google API key
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
    """Handler filter that rewrites each record with credentials masked - the formatted message
    AND any traceback, since an exception message can quote a URL or a header just as a log
    message can. Attached to handlers rather than loggers because a logger's filters do not apply
    to records propagated up from its children; a handler's filters see everything it emits.

    A second line of defence behind the logger levels above, for whatever else might one day log
    a credential. Never drops a record."""

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


def _attach_redaction(handler: logging.Handler) -> None:
    if not any(isinstance(f, SecretRedactingFilter) for f in handler.filters):
        handler.addFilter(SecretRedactingFilter())


def configure_logging(environment: str) -> None:
    level = logging.DEBUG if environment == "development" else logging.INFO
    logging.basicConfig(level=level, format=DEFAULT_LOG_FORMAT)
    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)

    for name in CREDENTIAL_LEAKING_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    for name in ("", *SERVER_LOGGERS):
        for handler in logging.getLogger(name).handlers:
            _attach_redaction(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
