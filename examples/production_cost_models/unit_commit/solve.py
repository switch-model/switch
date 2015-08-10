#!/usr/local/bin/python
# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

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

In both versions of incremental heat rate tables, I gave natural gas
combustion turbines a very minor heat rate penalty to discourage
committing more capacity than is needed. I changed the incremental heat
rate to 99 percent of the full load heat rate, with 1 percent of the
fuel use incurred at 0 electricity output.

For this to work, you need to ensure that the switch_mod package
directory is in your python search path. See the README for more info.

"""

from pyomo.environ import *
from switch_mod.utilities import define_AbstractModel
import switch_mod.utilities

switch_model = define_AbstractModel(
    'switch_mod', 'local_td', 'project.unitcommit', 'fuel_cost')
switch_instance = switch_model.load_inputs(inputs_dir="inputs")

opt = switch_mod.utilities.default_solver()

results = opt.solve(switch_instance, keepfiles=False, tee=False)
switch_model.save_results(results, switch_instance, "outputs")

# Dump all results
# switch_instance.load(results)
results.write()
switch_instance.pprint()
