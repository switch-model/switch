# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

import os
import shutil
import tempfile
import unittest

import switch_mod.utilities as utilities
import switch_mod.solve
from pyomo.environ import DataPortal
from testfixtures import compare

class UtilitiesTest(unittest.TestCase):

    def test_approx_equal(self):
        assert not utilities.approx_equal(1, 2)
        assert not utilities.approx_equal(1, 1.02)
        assert utilities.approx_equal(1, 1.01)
        assert utilities.approx_equal(1, 1)

    def test_save_inputs_as_dat(self):
        (model, instance) = switch_mod.solve.main(
            args=["--inputs-dir", os.path.join('examples', '3zone_toy', 'inputs')],
            return_model=True, return_instance=True
        )
        temp_dir = tempfile.mkdtemp(prefix="switch_test_")
        try:
            dat_path = os.path.join(temp_dir, "complete_inputs.dat")
            utilities.save_inputs_as_dat(model, instance, save_path=dat_path)
            reloaded_data = DataPortal(model=model)
            reloaded_data.load(filename=dat_path)
            compare(reloaded_data.data(), instance.DataPortal.data())
        finally:
            shutil.rmtree(temp_dir)
    

if __name__ == '__main__':
    unittest.main()
