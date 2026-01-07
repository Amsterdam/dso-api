from django.template import Library, TemplateSyntaxError

register = Library()


@register.simple_tag
def print_scopes(*schema_objects):
    """Print a list of scopes from the combined schema objects."""
    all_auth = set()
    for schema_object in schema_objects:
        if schema_object == "":
            raise TemplateSyntaxError("Variable not found for {% print_scopes %}")

        all_auth.update(schema_object.auth)

    return ", ".join(sorted(all_auth - {"OPENBAAR", "Openbaar"})) or "Geen; dit is openbare data."
