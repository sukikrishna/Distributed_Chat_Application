import os
import sys
import sphinx_rtd_theme

sys.path.insert(0, os.path.abspath('../../src'))

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'Chap Application'
copyright = '2025, Manasvi Goyal and Sukanya Krishna'
author = 'Manasvi Goyal and Sukanya Krishna'
release = '0.1'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration
# Enable the theme
html_theme = "sphinx_rtd_theme"

# Enable necessary extensions
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',  # Supports Google-style docstrings
    'sphinx.ext.viewcode'   # Adds links to source code
]

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_static_path = ['_static']
