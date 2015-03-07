"""
financials.py
Defines financial parameters for the SWITCH model.

SYNOPSIS
>>> from coopr.pyomo import *
>>> from timescales import *
>>> from financials import *
>>> switch_mod = AbstractModel()
>>> define_timescales(switch_mod)
>>> define_financials(switch_mod)
>>> switch_data = DataPortal(model=switch_mod)
>>> import_timescales(switch_mod, switch_data, 'test_dat')
>>> import_financials(switch_mod, switch_data, 'test_dat')
>>> switch_instance = switch_mod.create(switch_data)

Note, this can be tested with `python -m doctest -v financials.py`
"""
from coopr.pyomo import *
import os

from utilities import check_mandatory_components


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
            format(crf=crf, lp=100 * crf)
    Capital recovery factor for a loan with a 7 percent annual interest rate, paid over 20 years is 0.09439. If the principal was $100, loan payments would be $9.44
    """
    return ir/(1-(1+ir)**-t)


def crf(ir, t):
    """ An alias for capital_recovery_factor(ir, t) """
    return capital_recovery_factor(ir, t)


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
    return (1-(1+dr)**-t)/dr


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


def define_financials(switch_mod):
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

    These next parameters are derived from the above parameters and
    timescale information.

    bring_annual_costs_to_base_year[p in INVEST_PERIODS] is a
    coefficient that converts uniform costs made in each year of an
    investment period to NPV in the base financial year. This
    coefficient can be decomposed into two components. The first
    component converts a uniform stream of annual costs in the period to
    a lump sum at the beginning of the period using the function
    uniform_series_to_present_value() with the discount rate and the
    number of years per period. The second component converts a value at
    the start of a period to net present value in the base financial
    year using the function future_to_present_value() with the discount
    rate and number of years between the base financial year and the
    start of the period.

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

    switch_mod.base_financial_year = Param(within=PositiveIntegers)
    switch_mod.interest_rate = Param(within=PositiveReals)
    switch_mod.discount_rate = Param(
        within=PositiveReals, default=switch_mod.interest_rate)
    # Verify that mandatory data exists before using it.
    switch_mod.validate_minimum_financial_data = BuildCheck(
        rule=lambda mod: check_mandatory_components(
            mod, 'base_financial_year', 'interest_rate'))
    switch_mod.bring_annual_costs_to_base_year = Param(
        switch_mod.INVEST_PERIODS,
        within=PositiveReals,
        initialize=lambda mod, p: (
            uniform_series_to_present_value(
                mod.discount_rate, mod.period_length_years[p]) *
            future_to_present_value(
                mod.discount_rate,
                mod.period_start[p] - mod.base_financial_year)))
    switch_mod.bring_timepoint_costs_to_base_year = Param(
        switch_mod.TIMEPOINTS,
        within=PositiveReals,
        initialize=lambda mod, t: (
            mod.bring_annual_costs_to_base_year[mod.tp_period[t]] *
            mod.tp_weight_in_year[t]))


def import_financials(switch_mod, switch_data, inputs_directory):
    """
    Import base financial data from a .dat file. The inputs_directory should
    contain the file financials.dat that gives parameter values for
    base_financial_year, interest_rate and optionally discount_rate.

    EXAMPLE:
    >>> from coopr.pyomo import *
    >>> from timescales import *
    >>> from financials import *
    >>> switch_mod = AbstractModel()
    >>> define_timescales(switch_mod)
    >>> define_financials(switch_mod)
    >>> switch_data = DataPortal(model=switch_mod)
    >>> import_timescales(switch_mod, switch_data, 'test_dat')
    >>> import_financials(switch_mod, switch_data, 'test_dat')
    >>> switch_instance = switch_mod.create(switch_data)
    >>> switch_instance.bring_timepoint_costs_to_base_year.pprint()
    bring_timepoint_costs_to_base_year : Size=13, Index=TIMEPOINTS, Domain=PositiveReals, Default=None, Mutable=False
        Key : Value
          1 :   7674.416978
          2 :   7674.416978
          3 :   7674.416978
          4 :   7674.416978
          5 : 15348.9180021
          6 : 15348.9180021
          7 :   7674.416978
          8 :   7674.416978
          9 :   7674.416978
         10 :   7674.416978
         11 : 15348.9180021
         12 : 15348.9180021
         13 :  37691.616756
    """
    switch_data.load(filename=os.path.join(inputs_directory, 'financials.dat'))
