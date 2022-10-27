# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Add custom components to the Switch model to describe fixed system
costs that are needed to accurately calculate electricity costs. This
mimics the convention of switch modules that can include the following
functions:

define_components(model)
define_dynamic_components(model)
load_inputs(model, data_portal, inputs_dir)
pre_solve(instance, outdir)
post_solve(instance, outdir)

In this example, I have only implemented define_components() which adds
a administration_fees parameter to the model that specifies a fixed
annual cost of 1 million dollars and registers this cost with the
objective function.

Switch is licensed under Apache License 2.0 More info at switch-
model.org
"""

from pyomo.environ import *


def define_components(mod):
    mod.administration_fees = Param(
        mod.PERIODS, initialize=lambda m, p: 1000000, within=Any
    )
    mod.Cost_Components_Per_Period.append("administration_fees")
