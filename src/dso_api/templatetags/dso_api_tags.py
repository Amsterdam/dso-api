from django.template import Library, TemplateSyntaxError

register = Library()


@register.simple_tag
def print_scopes(*schema_objects):
    """Print a list of scopes from the combined schema objects."""
    all_auth = set()
    for schema_object in schema_objects:
        if schema_object == "":
            raise TemplateSyntaxError("Variable not found for {% print_scopes %}")

        auth = schema_object.auth  # can't use .scopes for DatabaseSchemaLoader
        if isinstance(auth, str):
            all_auth.add(auth)
        else:
            # Handle inconsistencies in auth objects here for now.
            # Should be fixed in schematools
            for scope in auth:
                if isinstance(scope, dict):
                    all_auth.add(scope.get("name", scope["id"]))
                else:
                    all_auth.add(str(scope))

    return ", ".join(all_auth - {"OPENBAAR", "Openbaar"}) or "Geen; dit is openbare data."
