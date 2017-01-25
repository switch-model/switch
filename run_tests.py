#!/usr/bin/env python
# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

import doctest
import os
import sys
import unittest


class TestLoader(unittest.TestLoader):

    # unittest.main does not allow multiple "--start-directory"
    # options, but we can make it scan multiple separate directories
    # by overriding discover().  This allows us to have a "tests"
    # directory that's separate from "switch_mod".
    #
    # We don't want to scan for *.py files in the parent directory in
    # case any of those are throwaway scripts that have unexpected
    # effects when imported.
    def discover(self, start_dir, pattern, top_level_dir):
        test_suite = unittest.TestSuite()
        for subdir in ('switch_mod', 'tests'):
            test_suite.addTests(
                super(TestLoader, self).discover(
                    os.path.join(top_level_dir, subdir),
                    pattern, top_level_dir))
        return test_suite

    # The unittest module does not have built-in support for finding
    # doctests.  In order to run the doctests, we need a custom
    # TestLoader that overrides loadTestsFromModule().
    def loadTestsFromModule(self, module):
        test_suite = super(TestLoader, self).loadTestsFromModule(module)

        docstring = module.__doc__
        if not docstring:
            # Work around a misfeature whereby doctest complains if a
            # module contains no docstrings.
            module.__doc__ = 'Placeholder docstring'
        test_suite.addTests(doctest.DocTestSuite(module))
        if not docstring:
            # Restore the original, in case this matters.
            module.__doc__ = docstring
        return test_suite


def main():
    script_dir = os.path.join(os.getcwd(), os.path.dirname(__file__))
    argv = [sys.argv[0],
            'discover',
            '--top-level-dir', script_dir,
            '--pattern', '*.py'] + sys.argv[1:]
    unittest.TestProgram(testLoader=TestLoader(), argv=argv)


if __name__ == '__main__':
    main()
