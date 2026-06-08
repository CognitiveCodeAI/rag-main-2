"""Unit tests for request correlation ids (E4 / audit M-7)."""

import logging

from app.observability.request_id import (
    RequestIdFilter,
    bind_request_id,
    get_request_id,
    new_request_id,
)
from app.observability.tasking import enqueue


def test_bind_generates_id_when_blank():
    rid = bind_request_id("")
    assert rid
    assert get_request_id() == rid


def test_bind_preserves_provided_id():
    rid = bind_request_id("trace-abc")
    assert rid == "trace-abc"
    assert get_request_id() == "trace-abc"


def test_new_request_id_unique():
    assert new_request_id() != new_request_id()


def test_filter_injects_request_id_onto_record():
    bind_request_id("rid-123")
    record = logging.LogRecord("n", logging.INFO, "p", 1, "msg", None, None)
    RequestIdFilter().filter(record)
    assert record.request_id == "rid-123"


def test_filter_defaults_to_dash_when_unbound():
    bind_request_id("")  # generates one; clear by setting empty via context reset
    # Force the unbound case by directly resetting the contextvar default.
    from app.observability import request_id as mod
    mod._request_id.set("")
    record = logging.LogRecord("n", logging.INFO, "p", 1, "msg", None, None)
    RequestIdFilter().filter(record)
    assert record.request_id == "-"


def test_enqueue_propagates_request_id_via_headers():
    bind_request_id("rid-xyz")
    captured = {}

    class FakeTask:
        def apply_async(self, args=None, kwargs=None, headers=None):
            captured["args"] = args
            captured["kwargs"] = kwargs
            captured["headers"] = headers
            return "async-result"

    result = enqueue(FakeTask(), "a", 1, job_id="j1")
    assert result == "async-result"
    assert captured["args"] == ("a", 1)
    assert captured["kwargs"] == {"job_id": "j1"}
    assert captured["headers"] == {"request_id": "rid-xyz"}
