"""Serializer logic for testing"""
from rest_framework_dso.fields import EmbeddedField, EmbeddedManyToManyField
from rest_framework_dso.serializers import DSOModelSerializer

from .models import Actor, Category, Location, Movie


class ActorSerializer(DSOModelSerializer):
    class Meta:
        model = Actor
        fields = ["name"]


class CategorySerializer(DSOModelSerializer):
    class Meta:
        model = Category
        fields = ["name"]


class MovieSerializer(DSOModelSerializer):
    """Serializer class to test DSO model logic, including embedding"""

    category = EmbeddedField(CategorySerializer)
    actors = EmbeddedManyToManyField(ActorSerializer)

    class Meta:
        model = Movie
        fields = ["name", "category_id", "date_added"]


class LocationSerializer(DSOModelSerializer):
    class Meta:
        model = Location
        fields = ["geometry"]
