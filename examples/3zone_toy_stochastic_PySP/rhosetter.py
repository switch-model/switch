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

"""
from pyomo.repn import generate_canonical_repn
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

    def coef_via_sympify(CostExpression):
        # This function may be depricated, and is the only place that uses
        # these packages, so put their definition here to make them more optional.
        import StringIO
        from re import findall
        from sympy import sympify

        string_out = StringIO.StringIO()
        CostExpression.expr.to_string(ostream=string_out)
        CostExpression_as_str = string_out.getvalue()
        string_out.close()

        # Find indexed variables like BuildCap[2030, CA_LADWP] using a regular
        # expression. See python documentation. The first part (?<=[^a-zA-Z])
        # ensures search pattern is not preceeded by a letter. The regex returns
        # two parts because I used two sets of parenthesis. I don't care about the
        # second parenthesis that returns the indexed bits, just the larger part

        pattern = "(?<=[^a-zA-Z])([a-zA-Z][a-zA-Z_0-9]*(\[[^]]*\])?)"
        component_by_alias = {}
        variable_list = findall(pattern, CostExpression_as_str)
        for (cname, index_as_str) in variable_list:
            component = scenario_instance.find_component(cname)
            alias = "x" + str(id(component))
            component_by_alias[alias] = component
            CostExpression_as_str = CostExpression_as_str.replace(cname, alias)
    
        # We can parse with sympify now that the var+indexes have clean names
        CostExpression_parsed = sympify(CostExpression_as_str)

        cost_coefficients = {}
        var_names = {}
        for (alias, component) in component_by_alias.iteritems():
            variable_id = symbol_map.getSymbol(component)
            cost_coefficients[variable_id] = CostExpression_parsed.coeff(alias)
            var_names[variable_id] = component.name
        return (cost_coefficients, var_names)

    
    def coef_via_pyomo(CostExpression):
        canonical_repn = generate_canonical_repn(CostExpression.expr)
        cost_coefficients = {}
        var_names = {}
        for (index, variable) in enumerate(canonical_repn.variables):
            variable_id = symbol_map.getSymbol(variable)
            cost_coefficients[variable_id] = canonical_repn.linear[index]
            var_names[variable_id] = variable.name
        return (cost_coefficients, var_names)
    
    
    def test(CostExpression):
        from testfixtures import compare

        (coefficients_sympify, var_names_sympify) = coef_via_sympify(CostExpression) 
        (coefficients_pyomo, var_names_pyomo) = coef_via_pyomo(CostExpression)

        compare(var_names_sympify, var_names_pyomo)
        # I have to use sorted because keys come out as randomly orderd tuples
        # and compare got hung up on inconsequential differences their ordering.
        compare(sorted(coefficients_sympify.keys()), sorted(coefficients_pyomo.keys()))

        # I rolled my own compare tool for cost_coefficients because compare
        # insists on numeric equality, and the sympify's round-trip of
        # binary->text->binary results in slight rounding errors.
        from switch_model.utilities import approx_equal
        for vid in coefficients_pyomo.keys():
            assert(approx_equal(coefficients_sympify[vid], coefficients_pyomo[vid],
                                tolerance=.000001))

    # This test passed, so I'm disabling the slower sympify function for now.
    # test(objective)
    (cost_coefficients, var_names) = coef_via_pyomo(objective)
    
    for variable_id in cost_coefficients:
        set_rho = False
        for tree_node in scenario._node_list:
            if variable_id in tree_node._standard_variable_ids:
                ph.setRhoOneScenario(
                    tree_node,
                    scenario,
                    variable_id,
                    cost_coefficients[variable_id] * rho_coefficient)
                set_rho = True
                break
        if set_rho == False:
            print("Warning! Could not find tree node for variable {}; rho not set.".format(var_names[variable_id]))
