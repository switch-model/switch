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
    long_description=read("README"),
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
    # We pin the upper limit for Pyomo and Python because there have been cases
    # where Pyomo introduced non-backward compatible changes or started crashing
    # with a new version of Python (e.g., Pyomo <=6.4.2 crashed on Python 3.11).
    # There's still some chance users will end up with an incompatible mix with
    # these or with other packages (e.g., newer versions of testfixtures don't
    # work on older versions of Python without adding mock, and testfixtures
    # 6.3.0 fails on Python >= 3.10), but we don't have an easy way to identify
    # compatible mixes and we don't want to be overly restrictive.
    # Note: testfixtures requires a separate mock installation if running with
    # Python 3.7.0 or 3.7.1, so we require a higher version to avoid this. (Newer
    # versions of Pyomo need 3.8+ anyway.)
    python_requires=">=3.7.2, <3.13.0a0",
    install_requires=[
        # In principle, we could accept Pyomo 5.6.9, but it tends to install
        # a non-compatible version of pyutilib (needs 5.8.0 but accepts 6.0.0
        # and then breaks). On the other hand, Pyomo 5.7 requires pyutilib 6.0.0
        # and Pyomo 6.0 doesn't require pyutilib at all. So we now use Pyomo 6.0+
        # and skip pyutilib.
        "Pyomo >=6.0.0, <=6.7.2",
        # pint is needed by Pyomo 6.4.1, 6.7.1 and probably others (but not
        # 6.0.0) when running our tests. But it isn't listed as a Pyomo
        # dependency, so we add it explicitly. (Still true as of Pyomo 6.7.1).
        "pint",
        # used for standard tests
        "testfixtures",
        # used for input upgrades and some reporting
        "pandas",
    ],
    extras_require={
        # packages used for advanced demand response, progressive hedging
        "advanced": [
            "numpy",
            "scipy",
            "rpy2",
            "sympy",
        ],
        "dev": ["ipdb"],
        "plotting": [
            # We have previously had to work around incompatibilities between
            # different versions of plotnine and matplotlib
            # (https://stackoverflow.com/a/73797154/) but they seem to be
            # resolved now.
            "plotnine",
            "matplotlib",
        ],
        "database_access": ["psycopg2-binary"],
    },
    entry_points={"console_scripts": ["switch = switch_model.main:main"]},
)
