"""Setup script for SWITCH. 

Use "pip install --upgrade ." to install a copy in the site packages directory.

Use "pip install --upgrade --editable ." to install SWITCH to be run from its 
current location.

Optional dependencies can be added during the initial install or later by 
running a command like this: 
pip install --upgrade --editable .[advanced,database_access]

Use "pip uninstall switch" to uninstall switch from your system.
"""

import os
from setuptools import setup

def read(*rnames):
    return open(os.path.join(os.path.dirname(__file__), *rnames)).read()

setup(
    name='SWITCH',
    version='2.0.0b0',
    maintainer='Matthias Fripp',
    maintainer_email='mfripp@hawaii.edu',
    url='http://switch-model.org',
    license='Apache v2',
    platforms=["any"],
    description='SWITCH Power System Planning Model',
    long_description=read('README'),
    classifiers=[
    'Development Status :: 4 - Beta',
    'Environment :: Console',
    'Intended Audience :: Education',
    'Intended Audience :: End Users/Desktop',
    'Intended Audience :: Science/Research',
    'License :: OSI Approved :: Apache Software License',
    'Natural Language :: English',
    'Operating System :: Microsoft :: Windows',
    'Operating System :: MacOS :: MacOS X',
    'Operating System :: Unix',
    'Programming Language :: Python',
    'Programming Language :: Unix Shell',
    'Topic :: Scientific/Engineering',
    'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    packages=['switch_mod'],
    keywords=[
        'renewable', 'power', 'energy', 'electricity', 
        'production cost', 'capacity expansion', 
        'planning', 'optimization'
    ],
    install_requires=[
        'Pyomo>=4.4.1', # We need a version that works with glpk 4.60+
        'testfixtures'  # used for standard tests
    ],
    extras_require={
        # packages used for advanced demand response, progressive hedging
        # and input-file upgrades
        'advanced': ['numpy', 'scipy', 'rpy2', 'sympy', 'pandas'],
        'database_access': ['psycopg2']
    },
    entry_points={
        'console_scripts': ['switch = switch_mod.main:main']
    },
)
