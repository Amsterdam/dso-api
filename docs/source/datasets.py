#!/bin/env python
import os
import re
import psycopg2
import psycopg2.extras
from string_utils import slugify


BASE_PATH = "/docs/source/"
re_camel_case = re.compile(
    r"(((?<=[^A-Z])[A-Z])|([A-Z](?![A-Z]))|((?<=[a-z])[0-9])|(?<=[0-9])[a-z])"
)
_comparison_lookups = ["exact", "gte", "gt", "lt", "lte", "not", "isnull"]
_identifier_lookups = [
    "exact",
    "in",
    "not",
    "isnull",
]  # needs ForeignObject.register_lookup()


def get_datasets():
    connection = psycopg2.connect(dsn=os.environ.get("DATABASE_URL"))
    with connection.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        cursor.execute("SELECT * FROM datasets_dataset")
        for dataset in cursor:
            yield dataset


def create_dataset_docs(dataset):
    # Header.
    metadata = dataset["schema_data"]
    doc = [make_title(metadata["title"].capitalize(), "=")]

    # Status.
    doc.append(f"Status: {metadata.get('status', 'Beschikbaar')}\n")

    # Tables.
    if len(metadata["tables"]):
        for table in metadata["tables"]:
            doc.append(f"- `{table['id'].capitalize()} Tabel`_")

        doc.append("\n")
        for table in metadata["tables"]:
            # print(dataset['name'], table['id'])
            doc.append(make_title(f"{table['id'].capitalize()} Tabel", "-"))
            doc.append(
                f"URI: `/v1/{to_snake_case(dataset['name'])}/{to_snake_case(table['id'])}/ "
                "</v1/{to_snake_case(dataset['name'])}/{to_snake_case(table['id'])}/>`_\n"
            )
            for field_id, field in table["schema"]["properties"].items():
                if field_id == "schema":
                    continue
                doc.append(f"*{toCamelCase(field_id)}*: {field.get('description', '')}")
                doc.append(" Filters:\n")
                doc.append(generate_filters(toCamelCase(field_id), field) + "\n")

            # Relations
            relations = [
                relation_name
                for relation_name, field in table["schema"]["properties"].items()
                if field.get("relation") is not None
            ]
            if len(relations):
                doc.append(
                    "The following fields can be expanded with ?_expandScope=...:\n"
                )
                for relation in relations:
                    doc.append(f"- {toCamelCase(relation)}")
                doc.append("\nExpand everything using _expand=true.")

            doc.append("Use ?_fields=field,field2 to limit which fields to receive")
            doc.append("Use ?_sort=field,field2,-field3 to sort on fieldsname")

    filename = os.path.join(
        BASE_PATH, "datasets", f"{to_snake_case(dataset['name'])}.rst"
    )
    with open(filename, "w") as output:
        output.write("\n".join(doc))
    return to_snake_case(dataset["name"])


def generate_filters(field_id, field):
    output = []
    if "type" not in field:
        if "$ref" in field and "geojson.org" in field["$ref"]:
            return f"- {field_id} = GeoJSON | POLYGON(x y ...)"
        return ""

    lookups = {
        "string": f"- {field_id} = string with lookups",
        "boolean": f"- {field_id} = true | false",
        "time": f"- {field_id} = hh:mm[:ss[.ms]]",
        "date": f"- {field_id} = yyyy-mm-dd or yyyy-mm-ddThh:mm[:ss[.ms]]",
    }
    if field["type"] in lookups:
        output.append(lookups[field["type"]])
    else:
        if field["type"] in ["integer", "number"]:
            integer_filters(field_id, output)
        elif field["type"] == "array":
            array_filters(field_id, field, output)
    return "\n".join(output)


def integer_filters(field_id, output):
    for filter in _comparison_lookups + ["in"]:
        output.append(f"- {field_id}[{filter}] = number")


def array_filters(field_id, field, output):
    if "entity" in field and field["entity"]["type"] == "string":
        output.append(f"- {field_id}[cotnains] = comma separated list of strings")
    elif field["items"]["type"] == "string":
        output.append(f"- {field_id}[cotnains] = comma separated list of strings")
    elif field["items"]["type"] == "object":
        for item_id, item in field["items"]["properties"].items():
            output.append(generate_filters(f"{field_id}.{toCamelCase(item_id)}", item))


def generate_datasets():
    documents = []
    for dataset in get_datasets():
        documents.append(create_dataset_docs(dataset=dataset))

    dataset_links = "\n".join([f"   datasets/{document}.rst" for document in documents])
    index_file = os.path.join(BASE_PATH, "_templates", "index.tpl")
    index = open(index_file, "r")
    index_data = index.read()
    index.close()
    with open(os.path.join(BASE_PATH, "index.rst"), "w") as index:
        data = index_data.replace("{datasets}", dataset_links)
        print(data)
        index.write(data)


# ---------- INTERNAL ---
def make_title(text, symbol):
    return "\n{text}\n{underscore}\n".format(text=text, underscore=symbol * len(text))


def toCamelCase(name):
    """
    Unify field/column/dataset name from Space separated/Snake Case/Camel case
    to camelCase.
    """
    name = " ".join(name.split("_"))
    words = re_camel_case.sub(r" \1", name).strip().lower().split(" ")
    return "".join(w.lower() if i == 0 else w.title() for i, w in enumerate(words))


def to_snake_case(name):
    """
    Convert field/column/dataset name from Space separated/Snake Case/Camel case
    to snake_case.
    """
    # Convert to field name, avoiding snake_case to snake_case issues.
    name = toCamelCase(name)
    return slugify(re_camel_case.sub(r" \1", name).strip().lower(), separator="_")


if __name__ == "__main__":
    generate_datasets()
