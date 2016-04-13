"""Setup script for SWITCH. 
Use "python setup.py install" to install a copy in the site packages directory.
Use "python setup.py develop" to activate SWITCH while preserving its current location.
"""

import os
from setuptools import setup

def read(*rnames):
    return open(os.path.join(os.path.dirname(__file__), *rnames)).read()

requires = [
    "Pyomo"
]

packages = ['switch_mod']

setup(
    name='SWITCH',
    version='2.0.b0',
    maintainer='Matthias Fripp',
    maintainer_email='mfripp@hawaii.edu',
    url='http://switch-model.org',
    license='Apache',
    platforms=["any"],
    description='SWITCH Power System Planning Model',
    long_description=read('README'),
    classifiers=[
    'Development Status :: 4 - Beta',
    'Intended Audience :: End Users/Desktop',
    'Intended Audience :: Science/Research',
    'License :: OSI Approved :: Apache Software License',
    'Natural Language :: English',
    'Operating System :: Microsoft :: Windows',
    'Operating System :: Unix',
    'Programming Language :: Python',
    'Programming Language :: Unix Shell',
    'Topic :: Scientific/Engineering',
    'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    packages=packages,
    keywords=[
        'renewable', 'power', 'energy', 'electricity', 
        'production cost', 'capacity expansion', 
        'planning', 'optimization'
    ],
    install_requires=requires,
    entry_points="""
    [console_scripts]
    switch=switch_mod.main:main
    """
    )