#!/usr/local/bin/python

"""

Illustrate the use of switch to construct and run a very simple model
with a single load zone, one investment period, and one timepoint.

For this to work, you need to ensure that the switch_mod package
directory is in your python search path. See the README for more info.

"""

from pyomo.environ import *
from pyomo.opt import SolverFactory
import switch_mod.utilities as utilities

switch_modules = (
    'timescales', 'financials', 'load_zones', 'local_td', 'fuels',
    'gen_tech', 'project.build', 'project.dispatch', 'fuel_markets',
    'energy_balance', 'sys_cost')
utilities.load_modules(switch_modules)
switch_model = utilities.define_AbstractModel(switch_modules)
inputs_dir = 'test_dat/copper_plate0'
switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
switch_instance = switch_model.create(switch_data)

opt = SolverFactory("cplex")

results = opt.solve(switch_instance, keepfiles=False, tee=False)
switch_instance.load(results)

results.write()
switch_instance.pprint()
