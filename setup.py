"""Setup script for SWITCH. 
Use "python setup.py install" to install a copy in the site packages directory.
Use "python setup.py develop" to activate SWITCH while preserving its current location.

"""

import os
from setuptools import setup

def read(*rnames):
    return open(os.path.join(os.path.dirname(__file__), *rnames)).read()

required = [
    "Pyomo"
]

# use 'python setup.py develop --user' to install switch
# then use 'pip install --user switch[run_tests,demand_response]' to install optional dependencies
extras = {
    'run_tests': ['testfixtures'],
    'demand_response': ['numpy', 'scipy']
}

packages = ['switch_mod']

entry_points = """
    [console_scripts]
    switch=switch_mod.main:main
"""

from distutils.cmd import Command
from distutils.core import setup


# based on https://justin.abrah.ms/python/setuppy_distutils_testing.html
class RunTests(Command):
    user_options = []
    def initialize_options(self):
        pass
    def finalize_options(self):
        pass
    def run(self):
        import sys, subprocess
        raise SystemExit(subprocess.call([sys.executable, 'run_tests.py']))

setup(
    name='SWITCH',
    version='2.0b0',
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
    install_requires=required,
    tests_require=extras['run_tests'],
    extras_require=extras,
    entry_points=entry_points,
    cmdclass={
        'test': RunTests
    }
)