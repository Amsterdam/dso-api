from rest_framework.renderers import JSONRenderer


class HALJSONRenderer(JSONRenderer):
    media_type = "application/hal+json"
