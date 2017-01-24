"""Setup script for SWITCH. 
Use "python setup.py install" to install a copy in the site packages directory.
Use "python setup.py develop" to activate SWITCH while preserving its current location.
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
        'PyUtilib',
        'Pyomo>=4.3.11377', # We minimally need the glpk bugfix version
        'nose',
        'ply',
        'six',
        'testfixtures',
        'sympy',
        'numpy'
    ],
    extras_require={
        'r': ['rpy2'],
        'psql': ['psycopg2']
    },
    entry_points={
        'console_scripts': ['switch = switch_mod.main:main']
    }
)