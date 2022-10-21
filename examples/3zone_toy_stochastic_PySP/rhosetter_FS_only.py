# Copyright 2016 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
(Benjamin): This script is based on rhosetter.py, but modified to set Rho
values only for the variables contained in the first stage costs Expression.
For medium to large scale problems setting Rho for every varible takes up
a significant amount of time, both in parsing the objective function with
sympify and in going through the scenario tree looking for the variable.
The progressive hedging algorithm only requires Rho values to be set (or
to have a default value) for variables located in branch nodes.

In this bilevel power grid planning problem example, first stage costs
include all investment in generation and transmission, while second stage
costs include operational expenses, such as variable O&M and fuel costs.
Therefore, Rho values must only be set for investment variables, which are
located in the root node. This sped up the rho setting process for a small-
medium sized system scale problem (the Chile grid) by a factor of 10. For
larger systems, the benefit increases.

TODO: Implement this in a more generalized way in order to support multistage
optimizations.

"""
# The rhosetter module should be in the same directory as this file.
from rhosetter import set_rho_values


def ph_rhosetter_callback(ph, scenario_tree, scenario):
    # This component name must match the expression used for first stage
    # costs defined in the ReferenceModel.
    cost_expr = scenario._instance.find_component("InvestmentCost")
    set_rho_values(ph, scenario_tree, scenario, cost_expr)
