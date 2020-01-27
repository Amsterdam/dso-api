from __future__ import annotations

from collections import UserDict
import json
import typing

import jsonschema

SUPPORTED_REFS = {
    "https://geojson.org/schema/Geometry.json",
    "https://geojson.org/schema/Point.json",
    "https://geojson.org/schema/Polygon.json",
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/id",
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/class",
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/dataset",
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/year",
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/uri",
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/schema"
}


class SchemaType(UserDict):
    @property
    def id(self) -> str:
        return self["id"]

    @property
    def type(self) -> str:
        return self["type"]

    def json(self) -> dict:
        return json.dumps(self.data)


class DatasetType(UserDict):
    pass


class DatasetSchema(SchemaType):
    """The schema of a dataset.
    This is a collection of JSON Schema's within a single file.
    """

    @classmethod
    def from_file(cls, filename: str):
        """Open an Amsterdam schema from a file."""
        with open(filename) as fh:
            return cls(json.load(fh))

    @classmethod
    def from_dict(cls, obj: dict):
        """ Parses given dict and validates the given schema """
        # XXX validation not added yet
        return cls(obj)

    @property
    def tables(self) -> typing.List[DatasetTableSchema]:
        """Access the tables within the file"""
        return [DatasetTableSchema(i, _parent_schema=self) for i in self["tables"]]

    def get_table_by_id(self, table_id: str) -> DatasetTableSchema:
        for table in self.tables:
            if table.id == table_id:
                return table
        raise ValueError(f"Schema of table '{table_id}' does not exist in {self}")


class DatasetTableSchema(SchemaType):
    """The table within a dataset.
    This table definition follows the JSON Schema spec.
    """

    def __init__(self, *args, _parent_schema=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._parent_schema = _parent_schema

    @property
    def fields(self):
        for name, spec in self["schema"]["properties"].items():
            if '$ref' in spec:
                ref = spec.pop('$ref')
                if ref not in SUPPORTED_REFS:
                    raise jsonschema.exceptions.ValidationError(f"Unknown: {ref}")

                # typedef = self.resolve(spec.pop('$ref'))
                # assert False, typedef
                spec = spec.copy()
                spec['type'] = ref

            yield DatasetFieldSchema(name=name, **spec)

    def validate(self, row: dict):
        """Validate a record against the schema."""
        jsonschema.validate(row, self.data["schema"])

    def _resolve(self, ref):
        """Resolve the actual data type of a remote URI reference."""
        return jsonschema.RefResolver(ref, referrer=self)


class DatasetFieldSchema(DatasetType):
    """ A single field (column) in a table """

    @property
    def name(self) -> str:
        return self['name']

    @property
    def type(self) -> str:
        return self['type']

    @property
    def is_primary(self):
        return self.name == "id" and self.type.endswith("/definitions/id")


class DatasetRow(DatasetType):
    """ An actual instance of data """

    def validate(self, schema: DatasetSchema):
        table = schema.get_table_by_id(self["table"])
        table.validate(self.data)
