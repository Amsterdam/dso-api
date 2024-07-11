"""Serializer logic for testing"""

from rest_framework_dso.fields import EmbeddedField, EmbeddedManyToManyField
from rest_framework_dso.serializers import DSOModelSerializer

from .models import Actor, Category, Location, Movie, MovieUser


class MovieUserSerializer(DSOModelSerializer):
    class Meta:
        model = MovieUser
        fields = ["name"]


class ActorSerializer(DSOModelSerializer):
    # 'last_updated_by' is not part of the fields, only available as embedded.
    last_updated_by = EmbeddedField(MovieUserSerializer)

    class Meta:
        model = Actor
        fields = ["name"]


class CategorySerializer(DSOModelSerializer):
    # 'last_updated_by' is not part of the fields, only available as embedded.
    last_updated_by = EmbeddedField(MovieUserSerializer)

    class Meta:
        model = Category
        fields = ["name"]


class MovieSerializer(DSOModelSerializer):
    """Serializer class to test DSO model logic, including embedding"""

    # Embedded fields (are not seen as regular serializer fields!)
    category = EmbeddedField(CategorySerializer)
    actors = EmbeddedManyToManyField(ActorSerializer)

    class Meta:
        model = Movie
        fields = ["name", "category_id", "date_added"]


class LocationSerializer(DSOModelSerializer):
    class Meta:
        model = Location
        fields = ["geometry"]
