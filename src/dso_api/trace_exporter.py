from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.ext.django.middleware import REQUEST_THREAD_LOCAL_KEY
from opencensus.trace import execution_context


def _get_django_request():
    """Get Django request from thread local.

    :rtype: str
    :returns: Django request.
    """
    return execution_context.get_opencensus_attr(REQUEST_THREAD_LOCAL_KEY)


def callback_function(envelope):
    envelope.data.baseData.properties["os_type"] = "linux"
    request = _get_django_request()
    breakpoint()
    return True


class DSOAzureExporter(AzureExporter):
    def __init__(self, **options):
        super(DSOAzureExporter, self).__init__(**options)
        self.add_telemetry_processor(callback_function)
