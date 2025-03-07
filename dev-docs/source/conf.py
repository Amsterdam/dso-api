# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
from datetime import date

import django

sys.path.insert(0, os.path.abspath("../../src"))
os.environ["DJANGO_DEBUG"] = "false"
os.environ["DJANGO_SETTINGS_MODULE"] = "dso_api.settings"
os.environ["SCHEMA_URL"] = "https://schemas.data.amsterdam.nl/"

django.setup()


# -- Project information -----------------------------------------------------

project = "Amsterdam DSO-API"
copyright = f"{date.today().year}, Gemeente Amsterdam"  # noqa: DTZ011
author = (
    "Team Datadiensten van het Dataplatform"
    " onder de Directie Digitale Voorzieningen, Gemeente Amsterdam"
)

# The full version, including alpha/beta/rc tags
release = "v1"


# -- General configuration ---------------------------------------------------

nitpicky = True

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.graphviz",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx_rtd_theme",
    "sphinxcontrib_django",
]


# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# The default page
master_doc = "index"

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# readthedocs doesn't have GDAL, so django.contrib.gis can't be imported
autodoc_mock_imports = ["django.contrib.gis.gdal"]

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_rtd_theme"
html_theme_options = {"includehidden": False}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

html_baseurl = os.environ.get("READTHEDOCS_CANONICAL_URL", "/")

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "django": (
        f"http://docs.djangoproject.com/en/{django.VERSION[0]}.{django.VERSION[1]}/",
        f"http://docs.djangoproject.com/en/{django.VERSION[0]}.{django.VERSION[1]}/_objects/",
    ),
}
