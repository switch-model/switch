# Copyright 2016 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Implement a cost-proportional method of setting variable-specific rho values for
the progressive hedging  algorithm. Automatically retrieve cost parameters from
the active objective function.  See CP(*) strategy described in Watson, J. P., &
Woodruff, D. L. (2011). Progressive hedging innovations for a class of
stochastic mixed-integer resource allocation problems. Computational Management
Science.

Note, sympy is a pre-requisite. Install via `sudo pip install sympy`

Implementation notes: I couldn't find hooks in Pyomo to extract the cost
coefficient for each decision variable. The best I  could get was a text
representation of the objective expression, a formula which is not simplified
into an ultimate cost vector.  I use sympy to parse the text of the equation,
simplify it, and extract coefficients for each variable. The only problem is
that the variables are formatted  with indexes (ex. foo[2020,bar]) and sympy
can't parse those. So, I replace them with unique ids (ex. x123456) before
giving the formula to sympy, and reverse the process after sympy has finished
parsing.

"""

import StringIO
from re import findall
from sympy import sympify
from pyomo.environ import Objective

def ph_rhosetter_callback(ph, scenario_tree, scenario):
    # This Rho coefficient is set to 1.0 to implement the CP(1.0) strategy
    # that Watson & Woodruff report as a good trade off between convergence 
    # to the extensive form optimum and number of PH iterations.
    rho_coefficient = 1.0

    scenario_instance = scenario._instance
    symbol_map = scenario_instance._ScenarioTreeSymbolMap
    objective = scenario_instance.component_data_objects(
        Objective, active=True, descend_into=True )
    objective = objective.next()
    
    string_out = StringIO.StringIO()
    objective.expr.to_string(ostream=string_out)
    objective_as_str = string_out.getvalue()
    string_out.close()

    # Find indexed variables like BuildCap[2030, CA_LADWP] using a regular
    # expression. See python documentation. The first part (?<=[^a-zA-Z])
    # ensures search pattern is not preceeded by a letter. The regex returns two
    # parts because I used two sets of parenthesis. I don't care about the
    # second parenthesis that returns the indexed bits, just the larger part

    pattern = "(?<=[^a-zA-Z])([a-zA-Z][a-zA-Z_0-9]*(\[[^]]*\])?)"
    component_by_alias = {}
    variable_list = findall(pattern, objective_as_str)
    for (cname, index_as_str) in variable_list:
        component = scenario_instance.find_component(cname)
        alias = "x" + str(id(component))
        component_by_alias[alias] = component
        objective_as_str = objective_as_str.replace(cname, alias)

    # After the variables+indexes have clean names, 
    # parse the equation with sympify
    obj_expr = sympify(objective_as_str)

    for (alias, component) in component_by_alias.iteritems():
        variable_id = symbol_map.getSymbol(component)
        coefficient = obj_expr.coeff(alias)
        set_rho = False
        for tree_node in scenario._node_list:
            if variable_id in tree_node._standard_variable_ids:
                ph.setRhoOneScenario(
                    tree_node,
                    scenario,
                    variable_id,
                    coefficient * rho_coefficient)
                set_rho = True
                break
        if set_rho == False:
            print("Warning! Could not find tree node for variable {}; rho not set.".format(component.cname()))

