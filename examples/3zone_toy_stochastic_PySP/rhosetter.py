# Copyright 2016-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Implement a cost-proportional method of setting variable-specific  rho values
for the progressive hedging algorithm only for first stage variables in a two
stage stochastic problem formulation. Automatically  retrieve cost parameters
from the active objective function for those variables.

See CP(*) strategy described in Watson, J. P., & Woodruff, D. L.  (2011).
Progressive hedging innovations for a class of stochastic  mixed-integer
resource allocation problems. Computational  Management Science.

"""
from __future__ import print_function
from pyomo.environ import Objective
from switch_model.utilities import iteritems

try:
    from pyomo.repn import generate_standard_repn  # Pyomo >=5.6

    newPyomo = True
except ImportError:
    from pyomo.repn import generate_canonical_repn  # Pyomo <=5.6

    newPyomo = False


def ph_rhosetter_callback(ph, scenario_tree, scenario):
    # Derive coefficients from active objective
    cost_expr = next(
        scenario._instance.component_data_objects(
            Objective, active=True, descend_into=True
        )
    )
    set_rho_values(ph, scenario_tree, scenario, cost_expr)


def set_rho_values(ph, scenario_tree, scenario, cost_expr):
    """
    Set values for rho for this model, based on linear coefficients in the
    provided expression.
    """

    # This Rho coefficient is set to 1.0 to implement the CP(1.0) strategy
    # that Watson & Woodruff report as a good trade off between convergence
    # to the extensive form optimum and number of PH iterations.
    rho_coefficient = 1.0

    scenario_instance = scenario._instance
    symbol_map = scenario_instance._ScenarioTreeSymbolMap

    if newPyomo:
        standard_repn = generate_standard_repn(cost_expr.expr)
        if standard_repn.nonlinear_vars or standard_repn.quadratic_vars:
            raise ValueError("This code does not work with nonlinear models.")
    else:
        standard_repn = generate_canonical_repn(cost_expr.expr)
        standard_repn.linear_vars = standard_repn.variables
        standard_repn.linear_coefs = standard_repn.linear

    cost_coefficients = {}
    var_names = {}
    for (variable, coef) in zip(standard_repn.linear_vars, standard_repn.linear_coefs):
        variable_id = symbol_map.getSymbol(variable)
        cost_coefficients[variable_id] = coef
        var_names[variable_id] = variable.name
    return (cost_coefficients, var_names)

    for variable_id in cost_coefficients:
        set_rho = False
        for tree_node in scenario._node_list:
            if variable_id in tree_node._standard_variable_ids:
                ph.setRhoOneScenario(
                    tree_node,
                    scenario,
                    variable_id,
                    cost_coefficients[variable_id] * rho_coefficient,
                )
                set_rho = True
                break
        if not set_rho:
            print(
                "Warning! Could not find tree node for variable {}; rho not set.".format(
                    var_names[variable_id]
                )
            )
