from readerwriterlock.rwlock import RWLockRead

# This lock type gives priority to the readers: while there are readers
# (that is incoming requests), the writer thread waits to acquire this lock.
reload_lock = RWLockRead()


def pause_reader_threads(view):
    """Decorator to indicate that the view is a writer-action.
    When the view is executed, all other requests are paused.
    """
    view._pause_reader_threads = True
    return view


class WaitOnReloadMiddleware:
    """Middleware to let a request wait while a reload is happening.

    This makes sure that views don't access some older models
    while a reload is happening.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def is_write_thread(self, request):
        return (
            request.resolver_match is not None and
            getattr(request.resolver_match.func, '_pause_reader_threads', False)
        )

    def __call__(self, request):
        if self.is_write_thread(request):
            # Make sure the /reload/ is not waiting for a read lock.
            # This waits until there are no readers active.
            with reload_lock.gen_wlock():
                return self.get_response(request)
        else:
            # This blocks accessing the view while a reload() is happening.
            # This avoids reading partially regenerated models/serializers.
            with reload_lock.gen_rlock():
                return self.get_response(request)
