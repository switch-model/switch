"""

Defines model components to describe system costs for the SWITCH-Pyomo
model.


SYNOPSIS
>>> import switch_mod.utilities as utilities
>>> switch_modules = ('timescales', 'financials', 'load_zones', 'fuels',\
    'gen_tech', 'project_build', 'project_dispatch', 'trans_build',\
    'trans_dispatch', 'energy_balance', 'sys_cost')
>>> utilities.load_modules(switch_modules)
>>> switch_model = utilities.define_AbstractModel(switch_modules)
>>> inputs_dir = 'test_dat'
>>> switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
>>> switch_instance = switch_model.create(switch_data)

Note, this can be tested with `python -m doctest sys_cost.py`
within the source directory.

Switch-pyomo is licensed under Apache License 2.0 More info at switch-model.org
"""

from pyomo.environ import *
from financials import uniform_series_to_present_value, future_to_present_value


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to summarize net
    present value of all system costs. Unless otherwise stated, all
    terms describing power are in units of MW and all terms describing
    energy are in units of MWh. Future costs (both hourly and annual)
    are in real dollars relative to the base_year and are converted to
    net present value in the base year within this module.

    TotalSystemCost is an expression that summarizes total system costs
    using the model components in the two lists cost_components_tp and
    cost_components_annual. Components in the first list are indexed by
    timepoint and components in the second are indexed by period.

    Minimize_System_Cost is the objective function that seeks to minimize
    TotalSystemCost.

    """

    def calc_tp_costs_in_period(m, t):
        return sum(
            getattr(m, tp_cost)[t] * m.tp_weight_in_year[t]
            for tp_cost in m.cost_components_tp)

    # Note: multiply annual costs by a conversion factor if running this
    # model on an intentional subset of annual data whose weights do not
    # add up to a full year: sum(tp_weight_in_year) / hours_per_year
    # This would also require disabling the validate_time_weights check.
    def calc_annual_costs_in_period(m, p):
        return sum(
            getattr(m, annual_cost)[p]
            for annual_cost in m.cost_components_annual)

    def calc_sys_costs_per_period(m, p):
        return (
            # All annual payments in the period
            (
                calc_annual_costs_in_period(m, p) +
                sum(calc_tp_costs_in_period(m, t) for t in m.PERIOD_TPS[p])
            ) *
            # Conversion to lump sum at beginning of period
            uniform_series_to_present_value(m.discount_rate,
                                            m.period_length_years[p]) *
            # Conversion to base year
            future_to_present_value(
                m.discount_rate, (m.period_start[p] - m.base_financial_year))
        )

    mod.SystemCostPerPeriod = Expression(
        mod.INVEST_PERIODS,
        initialize=calc_sys_costs_per_period)
    mod.Minimize_System_Cost = Objective(
        rule=lambda m: sum(m.SystemCostPerPeriod[p] for p in m.INVEST_PERIODS),
        sense=minimize)


def load_data(mod, switch_data, inputs_dir):
    """

    This empty function is included to provide a uniform interface. If
    you needed any additional data for this module, you would import it
    here.

    """
