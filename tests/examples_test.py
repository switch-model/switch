# Copyright 2016 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

import os
import shutil
import sys
import tempfile
import unittest

import switch_mod.solve
import switch_mod.utilities

# This runs all the Switch examples (in the 'examples' directory) as
# test cases.


TOP_DIR = os.path.dirname(os.path.dirname(__file__))

UPDATE_EXPECTATIONS = False


def read_file(filename):
    with open(filename, "r") as fh:
        return fh.read()


def write_file(filename, data):
    with open(filename, "w") as fh:
        fh.write(data)


def find_example_dirs():
    examples_dir = os.path.join(TOP_DIR, 'examples')
    for dirpath, dirnames, filenames in os.walk(examples_dir):
        for dirname in dirnames:
            path = os.path.join(dirpath, dirname)
            if os.path.exists(os.path.join(path, 'inputs', 'modules.txt')):
                yield path


def get_expectation_path(example_dir):
    expectation_file = os.path.join(example_dir, 'outputs',
                                        'total_cost.txt')
    if not os.path.isfile( expectation_file ):
        return False
    else:
        return expectation_file


def make_test(example_dir):
    def test_example():
        temp_dir = tempfile.mkdtemp(prefix='switch_test_')
        try:
            switch_mod.solve.main([
                '--inputs-dir', os.path.join(example_dir, 'inputs'),
                '--outputs-dir', temp_dir])
            total_cost = read_file(os.path.join(temp_dir, 'total_cost.txt'))
        finally:
            shutil.rmtree(temp_dir)
        expectation_file = get_expectation_path(example_dir)
        if UPDATE_EXPECTATIONS:
            write_file(expectation_file, total_cost)
        else:
            expected = float(read_file(expectation_file))
            actual = float(total_cost)
            if not switch_mod.utilities.approx_equal(expected, actual,
                                                     tolerance=0.0001):
                raise AssertionError(
                    'Mismatch for total_cost (the objective function value):\n'
                    'Expected value:  {}\n'
                    'Actual value:    {}\n'
                    'Run "tests/examples_test.py --update" to update the '
                    'expectations if this change is expected.'
                    .format(expected, actual))

    name = os.path.relpath(example_dir, TOP_DIR)
    return unittest.FunctionTestCase(
        test_example, description='Example: %s' % name)


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for example_dir in find_example_dirs():
        if get_expectation_path(example_dir):
            suite.addTest(make_test(example_dir))
    return suite


if __name__ == '__main__':
    if sys.argv[1:2] == ['--update']:
        UPDATE_EXPECTATIONS = True
        sys.argv.pop(1)
    unittest.main()
