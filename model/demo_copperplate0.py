#!/usr/local/bin/python

"""
Demo aspects of SWITCH-Pyomo.
"""

from pyomo.environ import *
from pyomo.opt import SolverFactory
import utilities

switch_modules = (
    'timescales', 'financials', 'load_zones', 'fuels', 'gen_tech',
    'project_build', 'project_dispatch', 'fuel_markets', 'energy_balance',
    'sys_cost')
utilities.load_switch_modules(switch_modules)
switch_model = utilities.define_AbstractModel(switch_modules)
inputs_dir = 'test_dat/copper_plate0'
switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
switch_instance = switch_model.create(switch_data)

opt = SolverFactory("cplex")

results = opt.solve(switch_instance, keepfiles=False, tee=False)
switch_instance.load(results)

results.write()
switch_instance.pprint()
