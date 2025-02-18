from __future__ import division


def calibrate(m, base_data, dr_elasticity_scenario=3):
    """
    Accept a list of tuples showing [base hourly loads], and [base hourly
    prices] for each location (load_zone) and date (time_series). Store these
    for later reference by bid().
    """
    # import numpy; we delay till here to avoid interfering with unit tests
    global np
    import numpy as np
    
    global base_load_dict, base_price_dict, elasticity_scenario
    # build dictionaries (indexed lists) of base loads and prices
    # store the load and price vectors as numpy arrays (vectors) for faster
    # calculation later
    base_load_dict = {
        (z, ts): np.array(base_loads, float)
        for (z, ts, base_loads, base_prices) in base_data
    }
    base_price_dict = {
        (z, ts): np.array(base_prices, float)
        for (z, ts, base_loads, base_prices) in base_data
    }
    elasticity_scenario = dr_elasticity_scenario


def bid(m, load_zone, time_series, tp_duration_hrs, prices):
    """
    Accept a vector of current prices, for a particular location (load_zone) and
    day (time_series). Return a tuple showing hourly load levels and willingness
    to pay for those loads (relative to the loads achieved at the base_price).

    This version assumes that part of the load is price elastic with constant
    elasticity of 0.1 and no substitution between hours (this part is called
    "elastic load" below), and the rest of the load is inelastic in total
    volume, but schedules itself to the cheapest hours (this part is called
    "shiftable load").

    This version does not provide reserves.
    """

    elasticity = 0.1
    shiftable_share = 0.1 * elasticity_scenario  # 1-3

    # convert energy prices to a numpy vector, and make non-zero
    # to avoid errors when raising to a negative power
    p = np.maximum(1.0, np.array(prices["energy"], float))

    # get vectors of base loads and prices for this location and date
    # (previously saved by calibrate())
    bl = base_load_dict[load_zone, time_series]
    bp = base_price_dict[load_zone, time_series]

    # spread shiftable load among all minimum-cost hours (possibly just one),
    # shaped like the original load during those hours (so base prices result in base loads)
    mins = p == np.min(p)
    shiftable_load = np.zeros(len(p))
    shiftable_load[mins] = shiftable_share * np.sum(bl) * bl[mins] / sum(bl[mins])

    # the shiftable load is inelastic, so wtp is the same high number, regardless of when the load is served
    # so _relative_ wtp is always zero
    shiftable_load_wtp = 0

    elastic_base_load = (1.0 - shiftable_share) * bl
    elastic_load = elastic_base_load * (p / bp) ** (-elasticity)

    # Report _relative_ consumer surplus (cs) for the elastic load. This is the
    # surplus created by moving prices from baseline (bp) to current level (p).
    # This is the integral of the load (quantity) function from p to bp. In
    # general, if quantity in one hour depends on price in another hour, this
    # should be a line integral between these price vectors. However, for the
    # formulation used here, the hours are independent, so we can just sum the
    # integrals for each hour. For the direction of the integral: If p < bp,
    # consumer surplus decreases as we move from p to bp, so cs_p - cs_bp (given
    # by this integral) is positive.

    # With ebl = elastic_base_load and e = elasticity, the integral for this
    # example is calculated as:

    # Integral(ebl * (p/bp)**(-e),  p=p, p=bp)
    # = ebl * bp**e          * Integral(p**(-e), p=p, p=bp) 
    # = ebl * bp**e          * (bp**(1-e) - p**(1-e)) / (1-e)
    # = ebl * bp * bp**(e-1) * (bp**(1-e) - p**(1-e)) / (1-e)
    # = ebl * bp *       (1 - (p/bp)**(1-e))          / (1-e)

    elastic_load_cs_diff = np.sum(
        (1 - (p / bp) ** (1 - elasticity)) * bp * elastic_base_load / (1 - elasticity)
    )

    # wtp is the sum of consumer surplus and the amount actually paid, so
    # relative wtp is the sum of relative consumer surplus (above) and relative
    # expenditure, i.e., the difference between the amount actually paid for
    # elastic load under current price, vs base price
    base_elastic_load_paid = np.sum(bp * elastic_base_load)
    elastic_load_paid = np.sum(p * elastic_load)
    elastic_load_paid_diff = elastic_load_paid - base_elastic_load_paid

    demand = shiftable_load + elastic_load
    n_steps = len(p)

    # calculate average wtp per hour for this timeseries (note that all the 
    # calculations so far have been in strange units: prices are $/MWh and loads
    # are MW (MWh/h), so cs integrals and expenditure sums are $/h * n_timesteps)
    wtp = (shiftable_load_wtp + elastic_load_cs_diff + elastic_load_paid_diff) / n_steps

    # TODO: make 'energy up' reserve bid equal to the difference between current
    # demand and demand at some arbitrarily high price (that's how far down it
    # could be reduced) and 'energy down' equal to the difference between
    # current bid and the amount that would be consumed at $0 or price minimum
    # (maximum amount demand could be increased quickly on request)
    quantities = {
        "energy": demand,
        "energy up": 0.0 * demand,
        "energy down": 0.0 * demand,
    }

    return (quantities, wtp)
