#!/usr/local/bin/python
# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Illustrate the use of switch to construct and run a toy model
with three load zones and two investment period where the first
investment period has more temporal resolution than the second.

Note, the results from this have not been fully evaluated.

For this to work, you need to ensure that the switch_mod package
directory is in your python search path. See the README for more info.

"""

from pyomo.environ import *
from pyomo.opt import SolverFactory
from switch_mod.utilities import define_AbstractModel

switch_model = define_AbstractModel(
    'switch_mod', 'local_td', 'project.no_commit', 'fuel_markets',
    'trans_build', 'trans_dispatch')
switch_instance = switch_model.load_inputs(inputs_dir="inputs")

opt = SolverFactory("cplex")
results = opt.solve(switch_instance, keepfiles=False, tee=False)
switch_model.save_results(results, switch_instance, "outputs")

results.write()
switch_instance.pprint()
