# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

import unittest

import switch_mod.utilities as utilities


class UtilitiesTest(unittest.TestCase):

    def test_approx_equal(self):
        assert not utilities.approx_equal(1, 2)
        assert not utilities.approx_equal(1, 1.02)
        assert utilities.approx_equal(1, 1.01)
        assert utilities.approx_equal(1, 1)


if __name__ == '__main__':
    unittest.main()
