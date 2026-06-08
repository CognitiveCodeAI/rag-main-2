"""Celery enqueue helper that propagates the request correlation id (E4)."""

from app.observability.request_id import get_request_id


def enqueue(task, *args, **kwargs):
    """Enqueue a Celery task, propagating the current request id via headers.

    Drop-in replacement for ``task.delay(*args, **kwargs)``. A ``task_prerun``
    signal in app.worker re-binds the id inside the worker, so the whole
    API→worker chain shares one correlation id in the logs.
    """
    return task.apply_async(
        args=args,
        kwargs=kwargs,
        headers={"request_id": get_request_id()},
    )
