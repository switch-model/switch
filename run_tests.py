#!/usr/bin/env python

import doctest
import os
import sys
import unittest


# The unittest module does not have built-in support for finding
# doctests.  In order to run the doctests, we need a custom TestLoader
# that overrides loadTestsFromModule().
class TestLoader(unittest.TestLoader):

    def loadTestsFromModule(self, module):
        docstring = module.__doc__
        if not docstring:
            # Work around a misfeature whereby doctest complains if a
            # module contains no docstrings.
            module.__doc__ = 'Placeholder docstring'
        test_suite = doctest.DocTestSuite(module)
        if not docstring:
            # Restore the original, in case this matters.
            module.__doc__ = docstring
        return test_suite


def main():
    script_dir = os.path.join(os.getcwd(), os.path.dirname(__file__))

    # The doctests expect to be run from the "switch_mod" directory in
    # order to find test_dat.
    os.chdir(os.path.join(script_dir, 'switch_mod'))

    argv = [sys.argv[0],
            'discover',
            '--start-directory', os.path.join(script_dir, 'switch_mod'),
            '--top-level-dir', script_dir,
            '--pattern', '*.py'] + sys.argv[1:]
    unittest.TestProgram(testLoader=TestLoader(), argv=argv)


if __name__ == '__main__':
    main()
