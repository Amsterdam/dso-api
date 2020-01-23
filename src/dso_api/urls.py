from django.conf import settings
from django.urls import include, path
import django_healthchecks.urls

urlpatterns = [
    path('status/health/', include(django_healthchecks.urls)),
]


if 'debug_toolbar' in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns.extend([
        path('__debug__/', include(debug_toolbar.urls)),
    ])
