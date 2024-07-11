"""Logic for remote API endpoints.

The factory functions :func:`remote_serializer_factory` and :func:`remote_viewset_factory`
can be imported directly from the top-level package.
"""

from .serializers import remote_serializer_factory
from .views import remote_viewset_factory

__all__ = ("remote_serializer_factory", "remote_viewset_factory")
