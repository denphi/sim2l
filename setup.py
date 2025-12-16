"""Setup configuration for sim2l package"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

# Read version
version_file = Path(__file__).parent / "sim2l" / "version.py"
version = {}
exec(version_file.read_text(), version)

setup(
    name="sim2l",
    version=version["__version__"],
    description="Simulation framework with database-backed persistence",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="sim2l Development Team",
    author_email="sim2l@example.com",
    url="https://github.com/your-org/sim2l",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.20",
        "pint>=0.20",
        "pyyaml>=5.4",
        "papermill>=2.3",
        "jsonpickle>=2.0",
        "pillow>=8.0",
        "mendeleev>=0.9",
        "ipython>=7.0",
        "click>=8.0",
        "tabulate>=0.8",
        # Database services
        "flask>=2.0",
        "requests>=2.25",
        "psycopg2-binary>=2.9",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=3.0",
            "black>=22.0",
            "flake8>=4.0",
            "mypy>=0.950",
        ],
        "docs": [
            "sphinx>=4.0",
            "sphinx-rtd-theme>=1.0",
        ],
        "notebooks": [
            "scrapbook>=0.5",  # For notebook-based simulations
        ],
    },
    entry_points={
        "console_scripts": [
            "sim2l=sim2l.cli.main:cli",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering",
    ],
    include_package_data=True,
    package_data={
        "sim2l": ["repository/schema.sql"],
    },
)
