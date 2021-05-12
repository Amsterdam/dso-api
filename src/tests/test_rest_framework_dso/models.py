"""Models for testing"""
from django.contrib.gis.db import models as gis_models
from django.db import models

from rest_framework_dso.crs import RD_NEW


class NonTemporalMixin:
    @classmethod
    def is_temporal(cls):
        return False


class MovieUser(models.Model, NonTemporalMixin):
    """Used to test double-nested relations (both FK and M2M)"""

    name = models.CharField(max_length=100)

    class Meta:
        app_label = "test_rest_framework_dso"


class Category(models.Model, NonTemporalMixin):
    """Used to test FK relations."""

    name = models.CharField(max_length=100)
    last_updated_by = models.ForeignKey(
        MovieUser, related_name="categories_updated", null=True, on_delete=models.SET_NULL
    )

    class Meta:
        app_label = "test_rest_framework_dso"


class Actor(models.Model, NonTemporalMixin):
    """Used to test M2M relations"""

    name = models.CharField(max_length=100)
    last_updated_by = models.ForeignKey(MovieUser, null=True, on_delete=models.SET_NULL)

    class Meta:
        app_label = "test_rest_framework_dso"


class Movie(models.Model, NonTemporalMixin):
    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        Category, related_name="movies", on_delete=models.SET_NULL, null=True
    )
    actors = models.ManyToManyField(Actor, blank=True, related_name="movies")
    date_added = models.DateTimeField(null=True)
    url = models.URLField(null=True)

    class Meta:
        app_label = "test_rest_framework_dso"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Location(models.Model, NonTemporalMixin):
    geometry = gis_models.PointField(srid=RD_NEW.srid)

    class Meta:
        app_label = "test_rest_framework_dso"
