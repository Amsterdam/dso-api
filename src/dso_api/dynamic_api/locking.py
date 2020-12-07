"""Thread locking mechanism

This makes sure that model reloads don't interfere with existing requests.
"""
import logging
import threading
from functools import wraps

from django.apps import apps
from django.urls import resolve
from readerwriterlock.rwlock import RWLockRead
from rest_framework.exceptions import NotFound

# This lock type gives priority to the readers: while there are readers
# (that is incoming requests), the writer thread waits to acquire this lock.
reload_lock = RWLockRead()
reload_lock_status = threading.local()
logger = logging.getLogger(__name__)


def in_read_thread() -> bool:
    """Tell whether the current thread/request is a write thread."""
    # Checking whether it's not in a read-lock, so management commands also work this way.
    return getattr(reload_lock_status, "in_read", None)


def lock_for_writing(func):
    """Decorator to block all other requests while this function runs.
    If there is still a request/thread busy reading, this will pause the reading until.
    """

    @wraps(func)
    def _locking_decorator(*args, **kwargs):
        logger.debug("Requesting lock to reload models, views, router and URLs")

        # Avoid deadlocks when the same thread/request tries to lock for read+write.
        if in_read_thread():
            raise RuntimeError(
                "Can't lock for writing within a read thread, "
                "this would deadlock the thread."
            )

        with reload_lock.gen_wlock():
            logger.debug("Acquired write lock to perform reload")
            return func(*args, **kwargs)

    return _locking_decorator


class ReadLockMixin:
    """View mixin to avoid a read while the write-lock is active.

    This will pause the request until the write-lock has been completed.
    When there is no write lock, the view will run immediately.
    """

    def dispatch(self, request, *args, **kwargs):
        # Acquire a read lock. This would be a pass-through unless a writer(=reload) is active.
        # In such case, this request would pause until the reload is complete.
        if kwargs.pop("_skip_lock", False):
            return super().dispatch(request, *args, **kwargs)

        try:
            reload_lock_status.in_read = True
            with reload_lock.gen_rlock():
                # Final edge case: ensure that the model is really the latest version.
                # If a write-lock completed, the model might have been replaced.
                # In fact, the whole view is replaced but this should be a problem.
                opts = self.model._meta
                try:
                    # Can't use apps.get_model() as dynamic apps have no AppConfig.
                    new_model = apps.all_models[opts.app_label][opts.model_name]
                except LookupError:
                    # Using handle_exception() directly instead of raising the error,
                    # as the super().dispatch() is the point where DRF exceptions are handled.
                    response = self.handle_exception(
                        NotFound("API endpoint no longer exists")
                    )
                    self.headers = {}
                    self.finalize_response(request, response, *args, **kwargs)
                    return response
                else:
                    # Detected that reload updated the model
                    if new_model is not self.model:
                        return self._reloaded_view_dispatch(request, *args, **kwargs)

                return super().dispatch(request, *args, **kwargs)
        finally:
            reload_lock_status.in_read = False

    def _reloaded_view_dispatch(self, request, *args, **kwargs):
        """Redirect the request when all models/views/serializers were recreated."""
        # Trying to call super() on this view risks using old serializers/filtersets.
        # Instead, re-resolve the newly generated view class, and call that instead.
        logger.debug(
            "Re-fetching view for updated model %s",
            request.get_full_path(),
        )

        # Fetch the newly generated view.
        match = resolve(request.path)  # raises 404 if view was removed.
        request.resolver_match = match
        view = match.func

        # Call this new view to handle the request
        return view(request, *match.args, **match.kwargs, _skip_lock=True)
