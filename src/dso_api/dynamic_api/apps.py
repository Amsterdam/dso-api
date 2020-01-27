from django.apps import AppConfig


class DynamicAPIApp(AppConfig):
    name = 'dso_api.dynamic_api'

    def ready(self):
        # Tell the router to reload, and initialize the missing URL patterns
        # now that we're ready to read the model data.
        from dso_api.dynamic_api.urls import router

        router.reload()
