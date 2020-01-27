import io
import os
import re

from setuptools import find_packages
from setuptools import setup


def read(filename):
    filename = os.path.join(os.path.dirname(__file__), filename)
    text_type = type(u"")
    with io.open(filename, mode="r", encoding="utf-8") as fd:
        return re.sub(text_type(r":[a-z]+:`~?(.*?)`"), text_type(r"``\1``"), fd.read())


setup(
    name="schematools",
    version="0.1.0",
    url="https://github.com/Amsterdam/schematools",
    license="Mozilla Public 2.0",
    author="Jan Murre",
    author_email="jan.murre@catalyz.nl",
    description="Tooling to work with Amsterdam schema files.",
    long_description=read("README.rst"),
    packages=find_packages(exclude=("tests",)),
    install_requires=[
        "Django",
        "django-postgres-unlimited-varchar",
        "django-environ",
        "requests",
        "jsonschema",
        "click",
        "psycopg2",
        "ndjson",
        "shapely",
    ],
    extras_require={"tests": ["pytest"]},
    entry_points="""
        [console_scripts]
        schema=schematools.cli:schema
    """,
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "License :: OSI Approved :: MPL-2.0",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
)
