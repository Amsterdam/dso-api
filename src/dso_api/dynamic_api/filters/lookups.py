"""Additional ORM lookups to implement the various DSO filter operators."""

from django.db import models
from django.db.models import expressions, lookups


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
            if field_type in ["CharField", "TextField"]:
                return (
                    f"({lhs}) IS NULL OR LOWER({lhs}) != LOWER({rhs}))",
                    list(lhs_params + lhs_params)
                    + [rhs.lower() if isinstance(rhs, str) else rhs for rhs in rhs_params],
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
            if field_type in ["CharField", "TextField"]:
                return f"LOWER({lhs}) != LOWER({rhs})", list(lhs_params) + [
                    rhs.lower() if isinstance(rhs, str) else rhs for rhs in rhs_params
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
        return f"LOWER({lhs}) LIKE {rhs}", lhs_params + [rhs.lower() for rhs in rhs_params]

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
        field_type = self.lhs.output_field.get_internal_type()
        if field_type in ["CharField", "TextField"]:
            lhs, lhs_params = self.process_lhs(compiler, connection)
            rhs, rhs_params = self.process_rhs(compiler, connection)
            return f"LOWER({lhs}) = LOWER({rhs})", lhs_params + rhs_params
        else:
            return f"{lhs} = {rhs}", lhs_params + rhs_params
