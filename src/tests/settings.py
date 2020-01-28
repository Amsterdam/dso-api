from dso_api.settings import *

# The reason the settings are defined here, is to make them independent
# of the regular project sources. Otherwise, the project needs to have
# knowledge of the test framework.

INSTALLED_APPS += [
    "tests.test_rest_framework_dso",
]

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
