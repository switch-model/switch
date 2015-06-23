#!/usr/local/bin/python

"""

Illustrate the use of switch to construct and run a very simple
production-cost model with a single load zone, one investment period,
and four timepoints. Includes variable generation and unit commit
decisions.

I made up two sets of incremental heat rate data for natural gas
combined cycle generation because I had trouble finding any real data
from internet searches. The data in gen_inc_heat_rates_30p_commit.tab
assumes a single incremental heat rate that intercepts the y-axis at 30
percent of the full load heat rate times committed capacity. The data in
gen_inc_heat_rates_test_high_end_avoidance.tab has a crazy high
incremental heat rate above 90 percent capacity factor, to test that the
optimization will avoid that range. Copy data from either of those files
into gen_inc_heat_rates.tab if you want to play around with the model
behavior.

For this to work, you need to ensure that the switch_mod package
directory is in your python search path. See the README for more info.

"""

from pyomo.environ import *
from pyomo.opt import SolverFactory
import switch_mod.utilities as utilities

switch_modules = (
    'switch_mod', 'local_td', 'project.unitcommit', 'fuel_cost')
utilities.load_modules(switch_modules)
switch_model = utilities.define_AbstractModel(switch_modules)
inputs_dir = 'inputs'
switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
switch_instance = switch_model.create(switch_data)

opt = SolverFactory("cplex")

results = opt.solve(switch_instance, keepfiles=False, tee=False)
switch_instance.load(results)

results.write()
switch_instance.pprint()
