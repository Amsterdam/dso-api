from schematools.contrib.django.models import DynamicModel


class SealedDynamicModel(DynamicModel):
    """Extended DynamicModel from schematools, to block accessing deferred fields."""

    class Meta:
        abstract = True

    def refresh_from_db(self, using=None, fields=None):
        """Block accessing extra fields for a model.

        This avoids getting a performance issue due to the use of .only(),
        since Django will still query those fields when they are read.

        Overriding this method is easier and more robust than implementing django-seal.
        While django-seal offers similar functionality, this doesn't need overriding
        the queryset/manager and queryset iterator.
        """
        if fields and fields[0] not in self.__dict__:
            raise RuntimeError(
                f"Deferred attribute access: field '{fields[0]}' "
                f"was excluded by .only() but was still accessed."
            )

        return super().refresh_from_db(using=using, fields=fields)
