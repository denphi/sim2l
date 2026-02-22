#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Sim2l documentation build configuration file.
"""

import os
import sys

# Get the project root dir
cwd = os.getcwd()
project_root = os.path.dirname(cwd)

# Insert the project root dir as the first element in the PYTHONPATH
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'sim2l'))

# Import version
try:
    from sim2l.version import __version__
except ImportError:
    __version__ = '2.0.0'

# -- General configuration ---------------------------------------------

# Sphinx extensions
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'nbsphinx',
]

# Add any paths that contain templates here
templates_path = ['_templates']

# The suffix of source filenames
source_suffix = '.rst'

# The master toctree document
master_doc = 'index'

# General information about the project
project = 'Sim2l'
copyright = '2024, Sim2l Contributors'
author = 'Sim2l Contributors'

# The version info
version = __version__
release = __version__

# List of patterns to ignore when looking for source files
exclude_patterns = ['_build', '**.ipynb_checkpoints', 'Thumbs.db', '.DS_Store']

# The name of the Pygments (syntax highlighting) style to use
pygments_style = 'sphinx'

# -- Options for HTML output -------------------------------------------

# The theme to use for HTML and HTML Help pages
html_theme = 'sphinx_rtd_theme'

# Theme options
html_theme_options = {
    'navigation_depth': 4,
    'collapse_navigation': False,
    'sticky_navigation': True,
    'includehidden': True,
    'titles_only': False,
    'display_version': True,
    'prev_next_buttons_location': 'bottom',
    'style_external_links': True,
}

# Add any paths that contain custom static files
html_static_path = ['_static']

# Output file base name for HTML help builder
htmlhelp_basename = 'sim2ldoc'

# Logo and favicon
# html_logo = '_static/logo.png'
# html_favicon = '_static/favicon.ico'

# -- Options for LaTeX output ------------------------------------------

latex_elements = {
    'papersize': 'letterpaper',
    'pointsize': '10pt',
}

# Grouping the document tree into LaTeX files
latex_documents = [
    (master_doc, 'sim2l.tex', 'Sim2l Documentation',
     'Sim2l Contributors', 'manual'),
]

# -- Options for manual page output ------------------------------------

# One entry per manual page
man_pages = [
    (master_doc, 'sim2l', 'Sim2l Documentation',
     [author], 1)
]

# -- Options for Texinfo output ----------------------------------------

# Grouping the document tree into Texinfo files
texinfo_documents = [
    (master_doc, 'sim2l', 'Sim2l Documentation',
     author, 'sim2l', 'Modern simulation framework with database services.',
     'Miscellaneous'),
]

# -- Extension configuration -------------------------------------------

# Napoleon settings for Google/NumPy style docstrings
napoleon_google_style = True
napoleon_numpy_style = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True

# Autodoc settings
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__'
}

# Intersphinx mapping
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
    'flask': ('https://flask.palletsprojects.com/en/2.0.x/', None),
}

# Todo extension
todo_include_todos = True

# NBSphinx settings
nbsphinx_execute = 'never'  # Don't execute notebooks during build
nbsphinx_allow_errors = True  # Continue on errors

# Mock imports for modules that might not be available during doc build
autodoc_mock_imports = ['psycopg2', 'papermill']
