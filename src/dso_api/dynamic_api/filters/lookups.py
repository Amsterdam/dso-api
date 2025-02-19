"""Additional ORM lookups to implement the various DSO filter operators."""

from django.db import models
from django.db.models import expressions, lookups
from django.contrib.postgres.fields import ArrayField

@models.CharField.register_lookup
@models.TextField.register_lookup
class IsEmpty(lookups.Lookup):
    lookup_name = "isempty"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)

        # This generates  (lhs = '') is false  or  (lhs = '') is not false.
        # Both take into account the SQL rule that  (null = '')
        # returns null instead of false.
        not_negation = "NOT " if len(rhs_params) == 1 and rhs_params[0] == "True" else ""
        return f"({lhs} = '') IS {not_negation}FALSE", []


@models.Field.register_lookup
@models.ForeignObject.register_lookup
class NotEqual(lookups.Lookup):
    """Allow fieldname__not=... lookups in querysets."""

    lookup_name = "not"
    can_use_none_as_rhs = True

    def as_sql(self, compiler, connection):
        """Generate the required SQL."""
        # Need to extract metadata from lhs, so parsing happens inline
        lhs = self.lhs  # typically a Col(alias, target) object
        if hasattr(lhs, "resolve_expression"):
            lhs = lhs.resolve_expression(compiler.query)

        lhs_field = lhs
        while isinstance(lhs_field, expressions.Func):
            # Allow date_field__day__not=12 to return None values
            lhs_field = lhs_field.source_expressions[0]
        lhs_nullable = lhs_field.target.null

        # Generate the SQL-prepared values
        lhs, lhs_params = self.process_lhs(compiler, connection, lhs=lhs)  # (field, [])
        rhs, rhs_params = self.process_rhs(compiler, connection)  # ("%s", [value])

        field_type = self.lhs.output_field.get_internal_type()
        if lhs_nullable and rhs is not None:
            # Allow field__not=value to return NULL fields too.

            if field_type in ["CharField", "TextField"] and not self.lhs.field.primary_key:
                return (
                    f"({lhs}) IS NULL OR UPPER({lhs}) != UPPER({rhs}))",
                    list(lhs_params + lhs_params)
                    + [rhs.upper() if isinstance(rhs, str) else rhs for rhs in rhs_params],
                )
            else:
                return (
                    f"({lhs} IS NULL OR {lhs} != {rhs})",
                    list(lhs_params + lhs_params) + rhs_params,
                )

        elif rhs_params and rhs_params[0] is None:
            # Allow field__not=None to work.
            return f"{lhs} IS NOT NULL", lhs_params
        else:
            if field_type in ["CharField", "TextField"] and not self.lhs.field.primary_key:
                return f"UPPER({lhs}) != UPPER({rhs})", list(lhs_params) + [
                    rhs.upper() if isinstance(rhs, str) else rhs for rhs in rhs_params
                ]
            else:
                return f"{lhs} != {rhs}", list(lhs_params) + rhs_params


@models.CharField.register_lookup
@models.TextField.register_lookup
class Wildcard(lookups.Lookup):
    """Allow fieldname__wildcard=... lookups in querysets."""

    lookup_name = "like"

    def as_sql(self, compiler, connection):
        """Generate the required SQL."""
        # lhs = "table"."field"
        # rhs = %s
        # lhs_params = []
        # lhs_params = ["prep-value"]

        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        if self.lhs.field.primary_key:
            return f"{lhs} LIKE {rhs}", lhs_params + rhs_params
        else:
            return f"UPPER({lhs}) LIKE {rhs}", lhs_params + [rhs.upper() for rhs in rhs_params]

    def get_db_prep_lookup(self, value, connection):
        """Apply the wildcard logic to the right-hand-side value"""
        return "%s", [_sql_wildcards(value)]


def _sql_wildcards(value: str) -> str:
    """Translate our wildcard syntax to SQL syntax."""
    return (
        value
        # Escape % and _ first.
        .replace("\\", "\\\\")
        .replace("%", r"\%")
        .replace("_", r"\_")
        # Replace wildcard chars with SQL LIKE ones.
        .replace("*", "%")
        .replace("?", "_")
    )


@models.ForeignKey.register_lookup
class CaseInsensitiveExact(lookups.Lookup):
    lookup_name = "iexact"

    def as_sql(self, compiler, connection):
        """Generate the required SQL."""
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        if not self.lhs.field.primary_key:
            return f"UPPER({lhs}) = UPPER({rhs})", lhs_params + rhs_params
        else:
            return f"{lhs} = {rhs}", lhs_params + rhs_params


@ArrayField.register_lookup
class ArrayContainsCaseInsensitive(lookups.Lookup):
    """
    Override the default "contains" lookup for ArrayFields such that it does a case-insensitive
    search. It also supports passing a comma separated string of values (or an iterable) 
    and returns matches only when the array field contains ALL of these values.
    """
    lookup_name = "contains"

    def as_sql(self, compiler, connection):
        # Process the left-hand side expression (the array column)
        lhs, lhs_params = self.process_lhs(compiler, connection)

        # If the lookup value is a comma-separated string, split it;
        # otherwise assume it is an iterable of values or a single value.
        if isinstance(self.rhs, str):
            # Split value on commas and filter out any empty strings.
            values = [val.strip() for val in self.rhs.split(",") if val.strip()]
        else:
            try:
                iter(self.rhs)
            except TypeError:
                values = [self.rhs]
            else:
                values = list(self.rhs)

        # Convert each search value to uppercase for case-insensitive matching.
        values = [v.upper() for v in values]

        # Transform the values in the array column to uppercase; this is done by unnesting the
        # array, applying UPPER() to each element, and reconstructing an array.
        lhs_sql = f"(ARRAY(SELECT UPPER(x) FROM unnest({lhs}) AS x))"

        # Build a comma-separated set of placeholders for each search value.
        placeholders = ", ".join(["%s"] * len(values))

        # The resulting SQL uses the array "contains" operator @> to ensure that all provided
        # values are present (case-insensitively) in the array field.
        sql = f"{lhs_sql} @> ARRAY[{placeholders}]"
        return sql, lhs_params + values
