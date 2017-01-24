# Copyright 2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""

This package defines financial utility functions that are used in multiple
modules, the objective function of the model, and modules that calculate
fuel costs in different ways.

The default objective function is to minimize total discounted costs.

"""

core_modules = [
    'switch_mod.financials.minimize_cost']

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
