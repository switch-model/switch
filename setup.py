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

from get_and_record_version import get_and_record_version

repo_path = os.path.dirname(os.path.realpath(__file__))
__version__ = get_and_record_version(repo_path)

def read(*rnames):
    return open(os.path.join(os.path.dirname(__file__), *rnames)).read()

setup(
    name='switch_model',
    version=__version__,
    maintainer='Switch Authors',
    maintainer_email='authors@switch-model.org',
    url='http://switch-model.org',
    license='Apache License 2.0',
    platforms=["any"],
    description='Switch Power System Planning Model',
    long_description=read('README'),
    long_description_content_type="text/markdown",
    classifiers=[
        # from https://pypi.org/classifiers/
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Education',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX :: Linux',
        'Operating System :: Unix',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Topic :: Scientific/Engineering',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    packages=find_packages(include=['switch_model', 'switch_model.*']),
	package_data = {
		'switch_model': ['data/*']
	},
    keywords=[
        'renewable', 'power', 'energy', 'electricity',
        'production cost', 'capacity expansion',
        'planning', 'optimization'
    ],
    install_requires=[
        'Pyomo>=4.4.1', # We need a version that works with glpk 4.60+
        'pint',         # needed by Pyomo when we run our tests, but not included
        'testfixtures', # used for standard tests
        'pandas',       # used for input upgrades and testing that functionality
        'setuptools', # For parsing version numbers; it is part of almost all python distributions, but not guaranteed. 
    ],
    extras_require={
        # packages used for advanced demand response, progressive hedging
        # note: rpy2 discontinued support for Python 2 as of rpy2 2.9.0
        'advanced': [
            'numpy', 'scipy',
            'rpy2<2.9.0;python_version<"3.0"',
            'rpy2;python_version>="3.0"',
            'sympy'
        ],
        'dev': ['ipdb'],
        'plotting': ['plotnine'],
        'database_access': ['psycopg2-binary']
    },
    entry_points={
        'console_scripts': ['switch = switch_model.main:main']
    },
)
