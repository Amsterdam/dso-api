from django.db import models
from django.contrib.gis.db import models as gis_models

from rest_framework_dso.crs import RD_NEW


class Category(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "test_rest_framework_dso"


class Movie(models.Model):
    name = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)

    class Meta:
        app_label = "test_rest_framework_dso"
        ordering = ("name",)


class Location(models.Model):
    geometry = gis_models.PointField(srid=RD_NEW.srid)

    class Meta:
        app_label = "test_rest_framework_dso"
