# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

import logging
import os
import shutil
import tempfile
import unittest

import switch_model.utilities as utilities
import switch_model.solve
from pyomo.environ import DataPortal
from testfixtures import compare

class UtilitiesTest(unittest.TestCase):

    def test_approx_equal(self):
        assert not utilities.approx_equal(1, 2)
        assert not utilities.approx_equal(1, 1.02)
        assert utilities.approx_equal(1, 1.01)
        assert utilities.approx_equal(1, 1)

    def test_save_inputs_as_dat(self):
        (model, instance) = switch_model.solve.main(
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

    def test_check_mandatory_components(self):
        from pyomo.environ import ConcreteModel, Param, Set
        from switch_model.utilities import check_mandatory_components
        mod = ConcreteModel()
        mod.set_A = Set(initialize=[1,2])
        mod.paramA_full = Param(mod.set_A, initialize={1:'a',2:'b'})
        mod.paramA_empty = Param(mod.set_A)
        mod.set_B = Set()
        mod.paramB_empty = Param(mod.set_B)
        mod.paramC = Param(initialize=1)
        mod.paramD = Param()
        check_mandatory_components(mod, 'set_A', 'paramA_full')
        check_mandatory_components(mod, 'paramB_empty')
        check_mandatory_components(mod, 'paramC')
        with self.assertRaises(ValueError):
            check_mandatory_components(mod, 'set_A', 'paramA_empty')
        with self.assertRaises(ValueError):
            check_mandatory_components(mod, 'set_A', 'set_B')
        with self.assertRaises(ValueError):
            check_mandatory_components(mod, 'paramC', 'paramD')


    def test_min_data_check(self):
        from switch_model.utilities import _add_min_data_check
        from pyomo.environ import AbstractModel, Param, Set
        mod = AbstractModel()
        _add_min_data_check(mod)
        mod.set_A = Set(initialize=[1,2])
        mod.paramA_full = Param(mod.set_A, initialize={1:'a',2:'b'})
        mod.paramA_empty = Param(mod.set_A)
        mod.min_data_check('set_A', 'paramA_full')
        self.assertIsNotNone(mod.create_instance())
        mod.min_data_check('set_A', 'paramA_empty')
        # Fiddle with the pyomo logger to suppress its error message
        logger = logging.getLogger('pyomo.core')
        orig_log_level = logger.level
        logger.setLevel(logging.FATAL)
        with self.assertRaises(ValueError):
            mod.create_instance()
        logger.setLevel(orig_log_level)


if __name__ == '__main__':
    unittest.main()
