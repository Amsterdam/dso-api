from django.conf import settings
from django.urls import include, path
import django_healthchecks.urls
import dso_api.dynamic_api.urls

urlpatterns = [
    path('status/health/', include(django_healthchecks.urls)),
    path('v1/', include(dso_api.dynamic_api.urls)),
]


if 'debug_toolbar' in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns.extend([
        path('__debug__/', include(debug_toolbar.urls)),
    ])
