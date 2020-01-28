"""Thread locking mechanism

This makes sure that model reloads don't interfere with existing requests.
"""
import logging
import threading
from functools import wraps

from django.apps import apps
from readerwriterlock.rwlock import RWLockRead
from rest_framework.exceptions import NotFound

# This lock type gives priority to the readers: while there are readers
# (that is incoming requests), the writer thread waits to acquire this lock.
reload_lock = RWLockRead()
reload_lock_status = threading.local()
logger = logging.getLogger(__name__)


def in_write_thread() -> bool:
    """Tell whether the current thread/request is a write thread."""
    # Checking whether it's not in a read-lock, so management commands also work this way.
    return not getattr(reload_lock_status, 'in_read', False)


def lock_for_writing(func):
    """Decorator to block all other requests while this function runs.
    If there is still a request/thread busy reading, this will pause the reading until.
    """

    @wraps(func)
    def _locking_decorator(*args, **kwargs):
        logger.debug("Requesting lock to reload models, views, router and URLs")
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
        self.read_lock = reload_lock.gen_rlock()
        reload_lock_status.in_read = True

        # Acquire a read lock. This would be a pass-through unless a writer(=reload) is active.
        # In such case, this request would pause until the reload is complete.
        with self.read_lock:
            # Final edge case: ensure that the model is really the latest version.
            # If a write-lock completed, the model might have been replaced.
            # In fact, the whole view is replaced but this should be
            try:
                opts = self.model._meta
                new_model = apps.get_model(opts.app_label, opts.model_name)
                if new_model is not self.model:
                    logger.debug("Resuming request with updated model %s", request.get_full_path())
                    self.model = new_model
            except LookupError:
                # Using handle_exception() directly instead of raising the error,
                # as the super().dispatch() is the point where DRF exceptions are handled.
                return self.handle_exception(NotFound("API endpoint no longer exists"))

            return super().dispatch(request, *args, **kwargs)
