from django.db import models
from django.contrib.gis.db import models as gis_models

from rest_framework_dso.crs import RD_NEW


class NonTemporalMixin:
    @classmethod
    def is_temporal(cls):
        return False


class Category(models.Model, NonTemporalMixin):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "test_rest_framework_dso"


class Movie(models.Model, NonTemporalMixin):
    name = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    date_added = models.DateTimeField(null=True)

    class Meta:
        app_label = "test_rest_framework_dso"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Location(models.Model, NonTemporalMixin):
    geometry = gis_models.PointField(srid=RD_NEW.srid)

    class Meta:
        app_label = "test_rest_framework_dso"
