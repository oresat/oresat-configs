"""Configuration file for the Sphinx documentation builder."""

import sys
from datetime import datetime, timezone
from pathlib import Path

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use Path.resolve to make it absolute, like shown here.

sys.path.append(str(Path(__file__).parent.resolve()))
from scripts.gen_beacon_rst import gen_beacon_rst_files

sys.path.append(str(Path(__file__).parent.parent.resolve()))
from oresat_configs import __version__

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "OreSat Configs"
copyright = f"{datetime.now(timezone.utc).year}, Portland State Aerospace Society"  # noqa: A001
author = "PSAS"
release = __version__

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions: list[str] = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
]
templates_path: list[str] = []
exclude_patterns: list[str] = []
add_module_names = False

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["static"]
html_css_files = ["custom.css"]

# -- Others Options ----------------------------------------------------------

# Example configuration for intersphinx: refer to the Python standard library.
# To add links to stand python type definitions.
intersphinx_mapping = {"python": ("https://docs.python.org/3/", None)}

# -- Gen rst scripts ---------------------------------------------------------

gen_beacon_rst_files()
