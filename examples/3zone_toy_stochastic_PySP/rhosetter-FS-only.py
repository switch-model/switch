# Copyright 2016 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Implement a cost-proportional method of setting variable-specific  rho values
for the progressive hedging algorithm only for first stage variables in a two
stage stochastic problem formulation. Automatically  retrieve cost parameters
from the active objective function for those variables.

See CP(*) strategy described in Watson, J. P., & Woodruff, D. L.  (2011).
Progressive hedging innovations for a class of stochastic  mixed-integer
resource allocation problems. Computational  Management Science.

Note, sympy is a pre-requisite. Install via `sudo pip install sympy`

Implementation notes-------------------------------------------------------

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

import StringIO
from re import findall
from sympy import sympify

def ph_rhosetter_callback(ph, scenario_tree, scenario):
    # This Rho coefficient is set to 1.0 to implement the CP(1.0) strategy
    # that Watson & Woodruff report as a good trade off between convergence 
    # to the extensive form optimum and number of PH iterations.
    rho_coefficient = 1.0

    scenario_instance = scenario._instance
    symbol_map = scenario_instance._ScenarioTreeSymbolMap
    
    # This component name must match the expression used for first stage
    # costs defined in the ReferenceModel. 
    FSCostsExpr = scenario_instance.find_component("InvestmentCost")

    string_out = StringIO.StringIO()
    FSCostsExpr.expr.to_string(ostream=string_out)
    FSCostsExpr_as_str = string_out.getvalue()
    string_out.close()

    # Find indexed variables like BuildCap[2030, CA_LADWP] using a regular
    # expression. See python documentation. The first part (?<=[^a-zA-Z])
    # ensures search pattern is not preceeded by a letter. The regex returns
    # two parts because I used two sets of parenthesis. I don't care about the
    # second parenthesis that returns the indexed bits, just the larger part

    pattern = "(?<=[^a-zA-Z])([a-zA-Z][a-zA-Z_0-9]*(\[[^]]*\])?)"
    component_by_alias = {}
    variable_list = findall(pattern, FSCostsExpr_as_str)
    for (cname, index_as_str) in variable_list:
        component = scenario_instance.find_component(cname)
        alias = "x" + str(id(component))
        component_by_alias[alias] = component
        FSCostsExpr_as_str = FSCostsExpr_as_str.replace(cname, alias)
    
    # After the variables+indexes have clean names, 
    # parse the equation with sympify
    FSCostsExpr_parsed = sympify(FSCostsExpr_as_str)

    for (alias, component) in component_by_alias.iteritems():
        variable_id = symbol_map.getSymbol(component)
        coefficient = FSCostsExpr_parsed.coeff(alias)
        set_rho = False

        # Replace the for loop in the rhosetter.py script for a single
        # if statement to only set variables at the root node.
        root_node = scenario_tree.findRootNode()
        if variable_id in root_node._standard_variable_ids:
            ph.setRhoOneScenario(
                root_node,
                scenario,
                variable_id,
                coefficient * rho_coefficient)
            set_rho = True
            break
        if set_rho == False:
            print("Warning! Could not find tree node for variable {}; rho not set.".format(component.cname()))
