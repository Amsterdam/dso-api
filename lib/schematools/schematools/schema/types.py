from collections import UserDict
from dataclasses import dataclass
import json
import typing

import jsonschema

from . import refs


class SchemaType(UserDict):
    @property
    def id(self):
        return self["id"]

    @property
    def type(self):
        return self["type"]

    def json(self):
        return json.dumps(self.data)


class DatasetType(UserDict):
    pass


class DatasetSchema(SchemaType):
    """ The schema of a dataset """

    @classmethod
    def from_dict(cls, obj: dict):
        """ Parses given dict and validates the given schema """
        # XXX validation not added yet
        return cls(obj)

    @property
    def tables(self) -> typing.List["DatasetTableSchema"]:
        return [DatasetTableSchema(i) for i in self["tables"]]

    def get_table_by_id(self, table_id: str) -> "DatasetTableSchema":
        for table in self.tables:
            if table.id == table_id:
                return table
        raise ValueError(f"Schema of table '{table_id}' does not exist in {self}")


class DatasetTableSchema(SchemaType):
    """ The class within a dataset """

    @property
    def fields(self):
        return [
            DatasetFieldSchema(name=name, type=self.resolve(spec))
            for name, spec in self["schema"]["properties"].items()
        ]

    def validate(self, row: dict):
        jsonschema.validate(row, self.data["schema"])

    def resolve(self, spec):
        # when $ref, ignore everything else
        if "$ref" in spec:
            type_ = spec["$ref"]
            if type_ not in refs.REFS:
                raise jsonschema.exceptions.ValidationError(f"Unknown: {type_}")
            return type_
        return spec["type"]


@dataclass
class DatasetFieldSchema:
    """ A field in a datatype """

    name: str
    type: str

    @property
    def is_primary(self):
        return self.name == "id" and self.type.endswith("/definitions/id")


class DatasetRow(DatasetType):
    """ An actual instance of data """

    def validate(self, schema: DatasetSchema):
        table = schema.get_table_by_id(self["table"])
        table.validate(self.data)
