from django.contrib.gis.db import models
from django_postgres_unlimited_varchar import UnlimitedCharField


JSON_TYPE_TO_DJANGO = {
    "string": (UnlimitedCharField, {}),
    "integer": (models.IntegerField, {}),
    "number": (models.FloatField, {}),
    "boolean": (models.BooleanField, {}),
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/id": (
        models.IntegerField,
        {},
    ),
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/schema": (
        UnlimitedCharField,
        {},
    ),
    "https://geojson.org/schema/Geometry.json": (models.PolygonField, {}),
    "https://geojson.org/schema/Point.json": (models.PointField, {}),
}


def fetch_models_from_schema(dataset):
    result = []
    for table in dataset.tables:
        fields = {}
        for field in table.fields:
            kls, kw = JSON_TYPE_TO_DJANGO[field.type]
            if field.is_primary:
                kw["primary_key"] = True
            fields[field.name] = kls(**kw)
        model_name = f"{dataset.id.capitalize()}{table.id.capitalize()}"

        meta_cls = type(
            "Meta",
            (object,),
            {
                "managed": False,
                "db_table": f"{dataset.id}_{table.id}",
                "app_label": dataset.id,
            },
        )
        model_cls = type(
            model_name,
            (models.Model,),
            {**fields, "__module__": "dynapi.models", "Meta": meta_cls},
        )
        result.append(model_cls)

    return result
