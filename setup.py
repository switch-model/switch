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
    # Pyomo <=6.4.2 crashes on Python 3.11, so we rule that out until they
    # resolve it
    python_requires=">=3.7.0, <3.11.0a0",
    install_requires=[
        # Most of our code is compatible with Pyomo 5.5.1+, but Pyomo <=5.6.8
        # has a bug that makes it fail to report when values are out of domain
        # for a parameter. So we must require a later version than 5.6.8, which
        # was the highest version we previously supported, so all users will
        # need to upgrade their Pyomo version.
        # In principle, we could accept Pyomo 5.6.9 with pyutilib 5.8.0 (works
        # OK in testing), but we block that because Pyomo 5.6.9 says it's
        # willing to work with pyutilib 6.0.0, but isn't actually compatible.
        # We have to allow pyutilib 6.0.0 for the later versions of Pyomo and
        # setuptools doesn't give us a way to say Pyomo 5.6.9 should only be
        # installed with pyutilib 5.8.0, so we just block Pyomo 5.6.9.
        "Pyomo >=5.7.0, <=6.4.2",
        # Pyomo 5.7 specifies that it needs pyutilib >=6.0.0. We've seen cases
        # cases where Pyomo released a later pyutilib that broke an earlier
        # Pyomo (e.g., Pyomo 5.6.x with Pyutilib 6.0.0), so we had to
        # retroactively pin the pyutilib version. Pyomo 6.0 phased out the
        # pyutilib dependency, but we still pin at 6.0.0, just in case the user
        # installs Pyomo 5.7 and Pyutilib releases an incompatible update.
        "pyutilib ==6.0.0",
        # pint is needed by Pyomo when running our tests, but isn't installed by
        # Pyomo.
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
            # plotnine before <= 0.9.0 is not compatible with matplotlib >= 3.6
            # later versions of plotnine may be, but for now we require that
            # matplotlib be below 3.6.0 to ensure compatibility.
            # See https://stackoverflow.com/a/73797154/
            "plotnine<=0.9.0",
            "matplotlib<3.6.0a0",
        ],
        "database_access": ["psycopg2-binary"],
    },
    entry_points={"console_scripts": ["switch = switch_model.main:main"]},
)
