# Copyright 2016 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Generate a model for use with the PySP pyomo module, either for use with the
runef or runph commands. Both these scripts require a single .py file that
creates a pyomo model object named "model".

The inputs_dir parameter must match the inputs directory being used for the
current simulation.

The example in which this model generator is framed doesn't use the
fuel_markets module. This script is tailored to treat all the Switch model's
annual costs as resulting from the first stage decisions and the timepoint
costs as product of the second stage decision variables. This ReferenceModel
will produce incorrect results if the fuel_markets module is included in the
simulation, which includes fuel costs in the annual components of the
objective function. That would include second stage decisions in the
calculation of the first stage costs, resulting in different RootNode costs
per scenario, which is incongruent.

"""

inputs_dir = "inputs"

###########################################################

import switch_mod.utilities as utilities
import switch_mod.financials as financials
import sys, os
from pyomo.environ import *

print "loading model..."

try:
    module_fh = open(os.path.join(inputs_dir, 'modules'), 'r')
except IOError, exc:
    sys.exit('Failed to open input file: {}'.format(exc))
module_list = [line.rstrip('\n') for line in module_fh]
module_list.insert(0,'switch_mod')
model = utilities.create_model(module_list, args=[])
# The following code augments the model object with Expressions for the 
# Stage costs, which both runef and runph scripts need in order to build 
# the stochastic objective function. In this particular example, only
# two stages are considered: Investment and Operation. These Expression
# names must match exactly the StageCostVariable parameter defined for
# each Stage in the ScenarioStructure.dat file. 

# The following two functions are defined explicitely, because since they
# are nested inside another function in the financials module, they can't
# be called from this script.

def calc_tp_costs_in_period(m, t):
        return sum(
            getattr(m, tp_cost)[t] * m.tp_weight_in_year[t]
            for tp_cost in m.cost_components_tp)

def calc_annual_costs_in_period(m, p):
        return sum(
            getattr(m, annual_cost)[p]
            for annual_cost in m.cost_components_annual)

# In the current version of Switch-Pyomo, all annual costs are defined 
# by First Stage decision variables, such as fixed O&M and capital 
# costs, which are caused by the BuildProj, BuildTrans and BuildLocalTD
# variables, all of which are considered as first stage decisions in this
# two-stage example.
# Likewise, all timepoint defined costs are caused by Second Stage decision
# variables, such as variable O&M and fuel use costs, which are caused by
# the DispatchProj variable. These will be considered as second stage
# decisions in this example.
# Further comments on this are written in the Readme file.

model.InvestmentCost = Expression(rule=lambda m: sum(
                calc_annual_costs_in_period(m, p) * financials.uniform_series_to_present_value(
                m.discount_rate, m.period_length_years[p]) * financials.future_to_present_value(
                m.discount_rate, (m.period_start[p] - m.base_financial_year)) for p in m.PERIODS))
model.OperationCost = Expression(rule=lambda m: sum(
                sum(calc_tp_costs_in_period(m, t) for t in m.PERIOD_TPS[p]) * financials.uniform_series_to_present_value(
                m.discount_rate, m.period_length_years[p]) * financials.future_to_present_value(
                m.discount_rate, (m.period_start[p] - m.base_financial_year)) for p in m.PERIODS))

print "model successfully loaded..."