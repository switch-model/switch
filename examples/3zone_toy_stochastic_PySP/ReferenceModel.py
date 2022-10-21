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
from __future__ import print_function

inputs_dir = "inputs"

###########################################################

import switch_model.utilities as utilities
import switch_model.financials as financials
import switch_model.solve
import sys, os
from pyomo.environ import *

print("loading model...")

# Ideally, we would use the main codebase to generate the model, but the
# mandatory switch argument parser is interferring with pysp's command line tools
# model = switch_model.solve.main(return_model=True)

module_list = switch_model.solve.get_module_list(args=None)
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
        for tp_cost in m.Cost_Components_Per_TP
    )


def calc_annual_costs_in_period(m, p):
    return sum(
        getattr(m, annual_cost)[p] for annual_cost in m.Cost_Components_Per_Period
    )


# In the current version of Switch, all annual costs are defined
# by First Stage decision variables, such as fixed O&M and capital
# costs, which are caused by the BuildProj, BuildTrans and BuildLocalTD
# variables, all of which are considered as first stage decisions in this
# two-stage example.
# Likewise, all timepoint defined costs are caused by Second Stage decision
# variables, such as variable O&M and fuel use costs, which are caused by
# the DispatchProj variable. These will be considered as second stage
# decisions in this example.
# Further comments on this are written in the Readme file.

model.InvestmentCost = Expression(
    rule=lambda m: sum(
        calc_annual_costs_in_period(m, p) * m.bring_annual_costs_to_base_year[p]
        for p in m.PERIODS
    )
)

model.OperationCost = Expression(
    rule=lambda m: sum(
        sum(calc_tp_costs_in_period(m, t) for t in m.TPS_IN_PERIOD[p])
        * m.bring_annual_costs_to_base_year[p]
        for p in m.PERIODS
    )
)

print("model successfully loaded...")
