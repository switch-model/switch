"""

Add custom components to the SWITCH-Pyomo model to describe fixed system
costs that are needed to accurately calculate electricity costs. This
mimics the convention of switch modules that can include the following
functions:

define_components(model)
load_data(model, data_portal, inputs_dir)
save_results(model, instance, outdir)

In this example, I have only implemented define_components() which adds
a administration_fees parameter to the model that specifies a fixed
annual cost of 1 million dollars and registers this cost with the
objective function.

Switch-pyomo is licensed under Apache License 2.0 More info at switch-
model.org
"""

from pyomo.environ import *


def define_components(mod):
    mod.administration_fees = Param(
        mod.PERIODS,
        initialize=lambda m, p: 1000000)
    mod.cost_components_annual.append('administration_fees')
