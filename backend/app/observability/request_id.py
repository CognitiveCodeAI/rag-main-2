"""Request correlation IDs (E4 / audit M-7).

A request id is bound to a contextvar at the API boundary (and re-bound inside
Celery tasks), exposed on the response as ``X-Request-Id``, and injected into
every log record so a single request can be traced across the API and the
workers it enqueues.
"""

import logging
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-Id"

# Empty string => "no request bound" (rendered as "-" in logs).
_request_id: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str:
    return _request_id.get()


def bind_request_id(request_id: str) -> str:
    """Bind a request id to the current context; generate one if blank."""
    rid = request_id or new_request_id()
    _request_id.set(rid)
    return rid


class RequestIdFilter(logging.Filter):
    """Inject the current request id onto every log record as ``request_id``."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def install_request_id_logging() -> None:
    """Attach the request-id filter to active loggers and prefix their format.

    Modifies the formatters of EXISTING handlers (root + uvicorn) rather than
    adding new handlers, so log lines are not duplicated. Idempotent.
    """
    fmt = "%(asctime)s %(levelname)s [req:%(request_id)s] %(name)s: %(message)s"
    formatter = logging.Formatter(fmt)
    rid_filter = RequestIdFilter()

    logger_names = ["", "uvicorn", "uvicorn.access", "uvicorn.error", "app", "celery"]
    seen_handlers = set()
    for name in logger_names:
        logger = logging.getLogger(name)
        # Mark so the filter isn't added twice on re-entry.
        if not any(isinstance(f, RequestIdFilter) for f in logger.filters):
            logger.addFilter(rid_filter)
        for handler in logger.handlers:
            if id(handler) in seen_handlers:
                continue
            seen_handlers.add(id(handler))
            if not any(isinstance(f, RequestIdFilter) for f in handler.filters):
                handler.addFilter(rid_filter)
            handler.setFormatter(formatter)

    # If nothing has configured a root handler yet, install a basic one so app
    # logs still carry the request id.
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.addFilter(rid_filter)
        root.addHandler(handler)
        root.setLevel(logging.INFO)
