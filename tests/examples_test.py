# Copyright 2016 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

import os
import shutil
import tempfile
import unittest

import switch_mod.solve

# This runs all the Switch examples (in the 'examples' directory) as
# test cases.


TOP_DIR = os.path.dirname(os.path.dirname(__file__))


def find_example_dirs():
    examples_dir = os.path.join(TOP_DIR, 'examples')
    for dirpath, dirnames, filenames in os.walk(examples_dir):
        for dirname in dirnames:
            path = os.path.join(dirpath, dirname)
            if os.path.exists(os.path.join(path, 'inputs', 'modules')):
                yield path


def make_test(example_dir):
    def test_example():
        temp_dir = tempfile.mkdtemp(prefix='switch_test_')
        try:
            # TODO(mseaborn): Check that the outputs match some
            # expectations rather than just ignoring them.
            switch_mod.solve.main([
                '--inputs-dir', os.path.join(example_dir, 'inputs'),
                '--outputs-dir', temp_dir])
        finally:
            shutil.rmtree(temp_dir)

    name = os.path.relpath(example_dir, TOP_DIR)
    return unittest.FunctionTestCase(
        test_example, description='Example: %s' % name)


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for example_dir in find_example_dirs():
        suite.addTest(make_test(example_dir))
    return suite
