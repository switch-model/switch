# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines financial parameters for the SWITCH-Pyomo model.

"""
from pyomo.environ import *
import os
import pandas as pd

dependencies = 'switch_model.timescales'

def capital_recovery_factor(ir, t):
    """

    The capital recovery factor is a coefficient applied to a loan to
    determine annual payments. This function needs an interest rate ir
    and the number of compounding periods that payments are split
    across.

    Example: Calculate annual loan payments for a 20-year loan with a 7
    percent interest rate on $100.

    >>> crf = capital_recovery_factor(.07,20)
    >>> print ("Capital recovery factor for a loan with a 7 percent annual " +
    ...        "interest rate, paid over 20 years is {crf:0.5f}. If the " +
    ...        "principal was $100, loan payments would be ${lp:0.2f}").\
            format(crf=crf, lp=100 * crf) # doctest: +NORMALIZE_WHITESPACE
    Capital recovery factor for a loan with a 7 percent annual interest\
    rate, paid over 20 years is 0.09439. If the principal was $100, loan\
    payments would be $9.44
    """
    return 1/t if ir == 0 else ir/(1-(1+ir)**-t)


def uniform_series_to_present_value(dr, t):
    """
    Returns a coefficient to convert a uniform series of payments over t
    periods to a present value in the first period using a discount rate
    of dr. This is mathematically equivalent to  the inverse of the
    capital recovery factor, assuming the same rate and number of
    periods is used for both calculations. In practice, you typically
    use an interest rate for a capital recovery factor and a discount
    rate for this.
    Example usage:
    >>> print ("Net present value of a $10 / yr annuity paid for 20 years, " +
    ...        "assuming a 5 percent discount rate is ${npv:0.2f}").\
        format(npv=10 * uniform_series_to_present_value(.05,20))
    Net present value of a $10 / yr annuity paid for 20 years, assuming a 5 percent discount rate is $124.62

    Test for calculation validity compared to CRF using 7 decimal points
    >>> round(uniform_series_to_present_value(.07,20),7) == \
        round(1/capital_recovery_factor(.07,20),7)
    True
    """
    return t if dr == 0 else (1-(1+dr)**-t)/dr


def future_to_present_value(dr, t):
    """
    Returns a coefficient to convert money from some future value to
    t-years previously, with an annual discount rate of dr.
    Example:
    >>> round(future_to_present_value(.07,10),7)
    0.5083493
    """
    return (1+dr)**-t


def present_to_future_value(ir, t):
    """
    Returns a coefficient to convert money from one point in time to
    t years in the future, with an annual interest rate of ir. This is
    the inverse of future_to_present_value if calculated with the same
    rate and number of years.
    Example:
    >>> round(present_to_future_value(.07,10),7)
    1.9671514
    >>> round(present_to_future_value(.07,10)*\
        future_to_present_value(.07,10),7) == 1
    True
    """
    return (1+ir)**t

def define_dynamic_lists(mod):
    """
    There are two lists of costs components that form the cost-minimization
    objective function. Other modules may add elements to these lists.

    Cost_Components_Per_TP is a list of components that contribute to overall
    system costs in each timepoint. Each component in this list needs to be
    indexed by timepoint and specified in non-discounted real dollars per hour
    (not $/timepoint). The objective function will apply weights and
    discounting to these terms. If this indexing is not convenient for native
    model components, I advise writing an Expression object indexed by [t]
    that contains logic to access or summarize native model components.

    Cost_Components_Per_Period is a list of components that contribute to
    overall system costs on an annual basis. Each component in this list
    needs to be indexed by period and specified in non-discounted real
    dollars over a typical year in the period. The objective function
    will apply discounting to these terms. If this indexing is not
    convenient for native model components, I advise writing an
    Expression object indexed by [p] that contains logic to access or
    summarize native model components.

    """
    mod.Cost_Components_Per_TP = []
    mod.Cost_Components_Per_Period = []

def define_components(mod):
    """

    Augments a Pyomo abstract model object with sets and parameters that
    describe financial conversion factors such as interest rates,
    discount rates, as well as constructing more useful coefficients
    from those terms.

    base_financial_year is used for net present value calculations. All
    dollar amounts reported by SWITCH are in real dollars of this base
    year. Future dollars are brought back to this dollar-year via the
    discount_rate.

    interest_rate is real interest rate paid on a loan from a bank. In
    economic equilibrium conditions, this will be equal to the discount
    rate. We have specified it separately from discount rate so people
    can independently explore the impacts of different choices of
    discount rates without making assumptions about loan conditions.

    discount_rate is the annual real discount rate used to convert
    future dollars into net present value for purposes of comparison. It
    is mathematically similar to interest rate, but has very different
    meanings.

    From an investor perspective, discount rate can represent the
    opportunity cost of capital and should subsequently be set to the
    average return on economy-wide private investment. An investor could
    either spend money on a given project that will yield future
    returns, or invest money in a broad portfolio with an expected rate
    of return. Applying that expected rate of return to discount the
    future earnings from the project is a mathematical convenience for
    comparing those two options. This method implicitly assumes that
    rate of return will be constant during the relevant period of time,
    and that all earnings can be re-invested. These assumptions that
    capital can continue exponential growth are not always justifiable.

    From a consumption welfare perspective, discount rate is meant to
    represent three things: individuals' time preference of money,
    increase in expected future earnings, and elasticity of marginal
    social utility (how much happier you expect to be from increased
    future earnings). According to economic theory, in equilibrium
    conditions, the consumption welfare discount rate will be equal to
    the opportunity cost of capital discount rate. In practice, the
    opportunity cost of capital discount rate tends to be much larger
    than consumption welfare discount rate, likely because the financial
    returns to capital are not spread equally across society. In my 34
    lifetime in the USA, the economy has grown tremendously while median
    income have not changed.

    For more background on the meaning of discount rates, see
        http://ageconsearch.umn.edu/bitstream/59156/2/Scarborough,%20Helen.pdf

    When using a discount rate for long-term economic planning of a
    commodity such as electricity for a broad society, it is worth
    considering that if you use a high discount rate, you are implicitly
    assuming that society will have increased ability to pay in the
    future. A discount rate of 7 percent roughly doubles value every
    decade, and means that a bill of $200 one decade from now is
    equivalent to a bill of $100 today.

    While quite alarming in theory, in practice the choice of discount
    rate had virtually no impact on the future costs that SWITCH-WECC
    reports when I performed sensitivity runs in the range of 0-10
    percent discount rates. This is likely due to steadily increasing
    load and decreasing emission targets in our scenarios providing few
    opportunities of any benefit from delaying investments.

    In general, if you are converting value of money forward in time
    (from a present to a future value), use an interest rate. If you are
    converting value of money back in time, use a discount rate.

    These next two parameters are derived from the above parameters and
    timescale information.

    bring_annual_costs_to_base_year[p in PERIODS] is a coefficient that
    converts uniform costs made in each year of an investment period to
    NPV in the base financial year. This coefficient can be decomposed
    into two components. The first component converts a uniform stream
    of annual costs in the period to a lump sum at the beginning of the
    period using the function uniform_series_to_present_value() with the
    discount rate and the number of years per period. The second
    component converts a value at the start of a period to net present
    value in the base financial year using the function
    future_to_present_value() with the discount rate and number of years
    between the base financial year and the start of the period.

    bring_timepoint_costs_to_base_year[t in TIMEPOINTS] is a coefficient
    that converts a cost incurred in a timepoint to a net present value
    in the base year. In the context of Switch, a single timepoint is
    expected to represent a condition that repeats in multiple years in
    an investment period, and costs associated with the timepoint are
    treated as uniform annual costs during that period. The coefficient
    bring_timepoint_costs_to_base_year is determined by two components.
    The first is bring_annual_costs_to_base_year[p], which is described
    above. The second is the number of hours that a timepoint represents
    within a year. Timepoints typically represent something that occurs
    on the order of hours, so most costs are specified in terms of
    hours. Consequently, the NPV of most variable costs can be
    calculated by multiplying hourly unit costs by this coefficient and
    the dispatch decision.

    """

    mod.base_financial_year = Param(within=PositiveIntegers)
    mod.interest_rate = Param(within=NonNegativeReals)
    mod.discount_rate = Param(
        within=NonNegativeReals, default=mod.interest_rate)
    mod.min_data_check('base_financial_year', 'interest_rate')
    mod.bring_annual_costs_to_base_year = Param(
        mod.PERIODS,
        within=PositiveReals,
        initialize=lambda m, p: (
            uniform_series_to_present_value(
                m.discount_rate, m.period_length_years[p]) *
            future_to_present_value(
                m.discount_rate,
                m.period_start[p] - m.base_financial_year)))
    mod.bring_timepoint_costs_to_base_year = Param(
        mod.TIMEPOINTS,
        within=PositiveReals,
        initialize=lambda m, t: (
            m.bring_annual_costs_to_base_year[m.tp_period[t]] *
            m.tp_weight_in_year[t]))


def define_dynamic_components(mod):
    """

    Adds components to a Pyomo abstract model object to summarize net
    present value of all system costs. Other modules will register cost
    components into dynamic lists that are used here to calculate total
    system costs. This function is called after define_components() so
    that other modules have a chance to add entries to the dynamic
    lists.

    Unless otherwise stated, all terms describing power are in units of
    MW and all terms describing energy are in units of MWh. Future costs
    (both hourly and annual) are in real dollars relative to the
    base_year and are converted to net present value in the base year
    within this module.

    SystemCostPerPeriod[p in PERIODS] is an expression that sums
    total system costs in each period based on the two lists
    Cost_Components_Per_TP and Cost_Components_Per_Period. Components in the
    first list are indexed by timepoint and components in the second are
    indexed by period.

    Minimize_System_Cost is the objective function that seeks to minimize
    TotalSystemCost.

    """

    def calc_tp_costs_in_period(m, t):
        return sum(
            getattr(m, tp_cost)[t] * m.tp_weight_in_year[t]
            for tp_cost in m.Cost_Components_Per_TP)

    # Note: multiply annual costs by a conversion factor if running this
    # model on an intentional subset of annual data whose weights do not
    # add up to a full year: sum(tp_weight_in_year) / hours_per_year
    # This would also require disabling the validate_time_weights check.
    def calc_annual_costs_in_period(m, p):
        return sum(
            getattr(m, annual_cost)[p]
            for annual_cost in m.Cost_Components_Per_Period)

    def calc_sys_costs_per_period(m, p):
        return (
            # All annual payments in the period
            (
                calc_annual_costs_in_period(m, p) +
                sum(calc_tp_costs_in_period(m, t) for t in m.TPS_IN_PERIOD[p])
            ) *
            # Conversion from annual costs to base year
            m.bring_annual_costs_to_base_year[p]
        )

    mod.SystemCostPerPeriod = Expression(
        mod.PERIODS,
        rule=calc_sys_costs_per_period)
    # starting with Pyomo 4.2, it is impossible to call Objective.reconstruct() 
    # or calculate terms like Objective / <some other model component>,
    # so it's best to define a separate expression and use that for these purposes.
    mod.SystemCost = Expression(
        rule=lambda m: sum(m.SystemCostPerPeriod[p] for p in m.PERIODS))
    mod.Minimize_System_Cost = Objective(
        rule=lambda m: m.SystemCost,
        sense=minimize)


def load_inputs(mod, switch_data, inputs_dir):
    """
    Import base financial data from a .dat file. The inputs_dir should
    contain the file financials.dat that gives parameter values for
    base_financial_year, interest_rate and optionally discount_rate.
    """
    switch_data.load(filename=os.path.join(inputs_dir, 'financials.dat'))

def post_solve(instance, outdir):
    m = instance
    # Overall electricity costs
    normalized_dat = [
        {
        	"PERIOD": p,
        	"SystemCostPerPeriod_NPV": value(m.SystemCostPerPeriod[p]),
        	"SystemCostPerPeriod_Real": value(
        	    m.SystemCostPerPeriod[p] / m.bring_annual_costs_to_base_year[p]
        	),
        	"EnergyCostReal_per_MWh": value(
        	    m.SystemCostPerPeriod[p] / m.bring_annual_costs_to_base_year[p] /
        	    sum(m.zone_total_demand_in_period_mwh[z,p] for z in m.LOAD_ZONES)
        	),
        	"SystemDemand_MWh": value(sum(
        	    m.zone_total_demand_in_period_mwh[z,p] for z in m.LOAD_ZONES
        	))
        } for p in m.PERIODS
    ]
    df = pd.DataFrame(normalized_dat)
    df.set_index(["PERIOD"], inplace=True)
    df.to_csv(os.path.join(outdir, "electricity_cost.csv"))
    # Itemized annual costs
    annualized_costs = [
        {
        	"PERIOD": p,
        	"Component": annual_cost,
        	"Component_type": "annual",
        	"AnnualCost_NPV": value(
        	    getattr(m, annual_cost)[p] * m.bring_annual_costs_to_base_year[p]
        	),
        	"AnnualCost_Real": value(getattr(m, annual_cost)[p])
        } for p in m.PERIODS for annual_cost in m.Cost_Components_Per_Period
    ] + [
        {
        	"PERIOD": p,
        	"Component": tp_cost,
        	"Component_type": "timepoint",
        	"AnnualCost_NPV": value(sum(
        	    getattr(m, tp_cost)[t] * m.tp_weight_in_year[t]
        	    for t in m.TPS_IN_PERIOD[p]
        	) * m.bring_annual_costs_to_base_year[p]),
        	"AnnualCost_Real": value(sum(
        	    getattr(m, tp_cost)[t] * m.tp_weight_in_year[t]
        	    for t in m.TPS_IN_PERIOD[p]
        	))
        } for p in m.PERIODS for tp_cost in m.Cost_Components_Per_TP
    ]
    df = pd.DataFrame(annualized_costs)
    df.set_index(["PERIOD", "Component"], inplace=True)
    df.to_csv(os.path.join(outdir, "costs_itemized.csv"))
