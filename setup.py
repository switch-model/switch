"""Setup script for Switch.

Use "pip install --upgrade ." to install a copy in the site packages directory.

Use "pip install --upgrade --editable ." to install Switch to be run from its
current location.

Optional dependencies can be added during the initial install or later by
running a command like this:
pip install --upgrade --editable .[advanced,database_access]

Use "pip uninstall switch" to uninstall switch from your system.
"""

import os
from setuptools import setup, find_packages

# Get the version number. Strategy #3 from https://packaging.python.org/single_source_version/
version_path = os.path.join(os.path.dirname(__file__), "switch_model", "version.py")
version = {}
with open(version_path) as f:
    exec(f.read(), version)
__version__ = version["__version__"]


def read(*rnames):
    return open(os.path.join(os.path.dirname(__file__), *rnames)).read()


setup(
    name="switch_model",
    version=__version__,
    maintainer="Switch Authors",
    maintainer_email="authors@switch-model.org",
    url="http://switch-model.org",
    license="Apache License 2.0",
    platforms=["any"],
    description="Switch Power System Planning Model",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    classifiers=[
        # from https://pypi.org/classifiers/
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Education",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Natural Language :: English",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Unix",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    packages=find_packages(include=["switch_model", "switch_model.*"]),
    keywords=[
        "renewable",
        "power",
        "energy",
        "electricity",
        "production cost",
        "capacity expansion",
        "planning",
        "optimization",
    ],
    python_requires='>=3.7',
    install_requires=[
        "Pyomo>=6.1,<6.4.1",  # 6.1 Has all the bug fixes we need
        "pint",  # needed by Pyomo when we run our tests, but not included
        "testfixtures",  # used for standard tests
        "pandas",  # used for input upgrades and testing that functionality
        "gurobipy",  # used to provided python bindings for Gurobi for faster solving
        "pyyaml",  # used to read configurations for switch
        # Following libraries used for graphing
        "matplotlib",
        "seaborn",
        "plotnine",
        "scipy",
        "pillow",  # Image processing to make plots stick together
    ],
    extras_require={
        # packages used for advanced demand response, progressive hedging
        # note: rpy2 discontinued support for Python 2 as of rpy2 2.9.0
        "advanced": [
            "numpy",
            "scipy",
            'rpy2<2.9.0;python_version<"3.0"',
            'rpy2;python_version>="3.0"',
            "sympy",
        ],
        # These packages are installed when one runs 'pip install --editable .[dev]'
        "dev": ["ipdb", "black", "psycopg2-binary"],
        # On Windows at least, installing these will only work via conda.
        # Run conda install -c conda-forge geopandas shapely [... all the other packages]
        "maps_INSTALL_WITH_CONDA": ["geopandas", "shapely", "cartopy", "plotnine"]
    },
    entry_points={
        "console_scripts": [
            "switch = switch_model.__main__:main",
        ]
    },
)
