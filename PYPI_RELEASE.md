# PyPI Release Guide for sim2l

This guide explains how to build and publish sim2l to PyPI.

## Prerequisites

1. **Install build tools:**
   ```bash
   pip install --upgrade pip setuptools wheel build twine
   ```

2. **Create PyPI account:**
   - Register at https://pypi.org/account/register/
   - Register at https://test.pypi.org/account/register/ (for testing)

3. **Configure API tokens:**
   - Create API token at https://pypi.org/manage/account/token/
   - Create API token at https://test.pypi.org/manage/account/token/

## Building the Distribution

1. **Clean previous builds:**
   ```bash
   rm -rf build/ dist/ *.egg-info
   ```

2. **Build the package:**
   ```bash
   python -m build
   ```

   This creates:
   - `dist/sim2l-X.X.X.tar.gz` (source distribution)
   - `dist/sim2l-X.X.X-py3-none-any.whl` (wheel distribution)

3. **Check the package:**
   ```bash
   twine check dist/*
   ```

## Testing on TestPyPI

1. **Upload to TestPyPI:**
   ```bash
   twine upload --repository testpypi dist/*
   ```

   Or with token:
   ```bash
   twine upload --repository testpypi dist/* -u __token__ -p pypi-YOUR_TEST_TOKEN
   ```

2. **Test installation:**
   ```bash
   pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple sim2l
   ```

3. **Verify the package works:**
   ```bash
   python -c "import sim2l; print(sim2l.__version__)"
   sim2l --help
   ```

## Publishing to PyPI

1. **Upload to PyPI:**
   ```bash
   twine upload dist/*
   ```

   Or with token:
   ```bash
   twine upload dist/* -u __token__ -p pypi-YOUR_PYPI_TOKEN
   ```

2. **Verify on PyPI:**
   - Check package page: https://pypi.org/project/sim2l/

3. **Test installation from PyPI:**
   ```bash
   pip install sim2l
   ```

## Version Management

Before releasing, update the version in `sim2l/version.py`:

```python
__version__ = "X.Y.Z"
```

Version numbering follows [Semantic Versioning](https://semver.org/):
- **MAJOR** version for incompatible API changes
- **MINOR** version for new functionality (backwards compatible)
- **PATCH** version for bug fixes (backwards compatible)

## Release Checklist

- [ ] Update version in `sim2l/version.py`
- [ ] Update CHANGELOG.md with release notes
- [ ] Run all tests: `pytest`
- [ ] Build the package: `python -m build`
- [ ] Check the package: `twine check dist/*`
- [ ] Upload to TestPyPI and test
- [ ] Upload to PyPI
- [ ] Create GitHub release with tag `vX.Y.Z`
- [ ] Update documentation on Read the Docs

## GitHub Actions Automation (Optional)

Create `.github/workflows/publish.yml` for automated releases:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    - name: Build package
      run: python -m build
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*
```

Add your PyPI API token to GitHub Secrets as `PYPI_API_TOKEN`.

## Troubleshooting

**Error: "File already exists"**
- You cannot overwrite existing versions on PyPI
- Increment the version number and rebuild

**Error: "Invalid distribution"**
- Run `twine check dist/*` to identify issues
- Common issues: missing README.md, invalid metadata

**Import errors after installation**
- Verify package structure with `tar -tzf dist/sim2l-X.X.X.tar.gz`
- Check that `__init__.py` files exist in all package directories

## Support

For issues or questions:
- GitHub Issues: https://github.com/denphi/sim2l/issues
- Documentation: https://sim2l.readthedocs.io
