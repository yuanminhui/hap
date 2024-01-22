"""Sphinx configuration."""
project = "HAP"
author = "Yuan Minhui"
copyright = "2024, Yuan Minhui"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_click",
    "myst_parser",
]
autodoc_typehints = "description"
html_theme = "furo"
