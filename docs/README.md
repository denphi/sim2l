# Sim2l Documentation

This directory contains the Sphinx documentation for Sim2l.

## Building Locally

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Build HTML Documentation

```bash
cd docs
make html
```

The built documentation will be in `_build/html/`. Open `_build/html/index.html` in your browser.

### Build PDF Documentation

```bash
make latexpdf
```

### Clean Build Files

```bash
make clean
```

## Read the Docs

The documentation is automatically built and hosted on Read the Docs at:
https://sim2l.readthedocs.io

### Configuration

- `.readthedocs.yaml` - Read the Docs configuration
- `conf.py` - Sphinx configuration
- `requirements.txt` - Documentation build dependencies

## Documentation Structure

- `index.rst` - Main index with navigation
- `quickstart.rst` - Quick start guide
- `mcp.rst` - MCP server installation, tools, authentication, and configuration
- `database_services.rst` - Complete database services documentation
- `file_management.rst` - File management guide
- `examples.rst` - Code examples
- `api/` - API reference documentation
- `services/` - Individual service documentation

## Writing Documentation

### Adding New Pages

1. Create a new `.rst` file in the `docs/` directory
2. Add it to the appropriate `toctree` in `index.rst`
3. Rebuild the documentation

### RST Syntax

See https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html

### Code Examples

```rst
.. code-block:: python

    from sim2l import configure
    configure(use_run_database=True)
```

### API Documentation

```rst
.. automodule:: sim2l.database
   :members:
```

## Live Preview

For live preview while writing:

```bash
pip install sphinx-autobuild
sphinx-autobuild docs docs/_build/html
```

Then open http://127.0.0.1:8000 in your browser.
