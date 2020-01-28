import environ
import django
from django.conf import settings


def pytest_configure():
    settings.configure(
        DATABASES={
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
        },
        DEBUG=True,
    )
    django.setup()
