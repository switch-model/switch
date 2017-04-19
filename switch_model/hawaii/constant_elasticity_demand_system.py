def calibrate(base_data, dr_elasticity_scenario=3):
    """Accept a list of tuples showing [base hourly loads], and [base hourly prices] for each 
    location (load_zone) and date (time_series). Store these for later reference by bid().
    """
    # import numpy; we delay till here to avoid interfering with unit tests 
    global np
    import numpy as np

    global base_load_dict, base_price_dict, elasticity_scenario
    # build dictionaries (indexed lists) of base loads and prices
    # store the load and price vectors as numpy arrays (vectors) for faste calculation later
    base_load_dict = {
        (z, ts): np.array(base_loads, float)
        for (z, ts, base_loads, base_prices) in base_data
    }
    base_price_dict = {
        (z, ts): np.array(base_prices, float)
        for (z, ts, base_loads, base_prices) in base_data
    }
    elasticity_scenario = dr_elasticity_scenario

def bid(load_zone, time_series, prices):
    """Accept a vector of current prices, for a particular location (load_zone) and day (time_series).
    Return a tuple showing hourly load levels and willingness to pay for those loads (relative to the 
    loads achieved at the base_price).
    
    This version assumes that part of the load is price elastic with constant elasticity of 0.1 and no 
    substitution between hours (this part is called "elastic load" below), and the rest of the load is inelastic 
    in total volume, but schedules itself to the cheapest hours (this part is called "shiftable load")."""

    elasticity = 0.1
    shiftable_share = 0.1 * elasticity_scenario # 1-3

    # convert prices to a numpy vector, and make non-zero 
    # to avoid errors when raising to a negative power
    p = np.maximum(1.0, np.array(prices, float))

    # get vectors of base loads and prices for this location and date
    bl = base_load_dict[load_zone, time_series]
    bp = base_price_dict[load_zone, time_series]


    # spread shiftable load among all minimum-cost hours, 
    # shaped like the original load during those hours (so base prices result in base loads)
    mins = (p == np.min(p))
    shiftable_load = np.zeros(len(p))
    shiftable_load[mins] = bl[mins] * shiftable_share * np.sum(bl) / sum(bl[mins])
    
    # the shiftable load is inelastic, so wtp is the same high number, regardless of when the load is served
    # so _relative_ wtp is always zero
    shiftable_load_wtp = 0  
    
    elastic_base_load = (1.0 - shiftable_share) * bl
    elastic_load =  elastic_base_load * (p/bp) ** (-elasticity)
    # _relative_ consumer surplus for the elastic load is the integral 
    # of the load (quantity) function from p to bp; note: the hours are independent.
    # if p < bp, consumer surplus decreases as we move from p to bp, so cs_p - cs_p0 
    # (given by this integral) is positive.
    elastic_load_cs_diff = np.sum((1 - (p/bp)**(1-elasticity)) * bp * elastic_base_load / (1-elasticity))
    # _relative_ amount actually paid for elastic load under current price, vs base price
    base_elastic_load_paid = np.sum(bp * elastic_base_load)
    elastic_load_paid = np.sum(p * elastic_load)
    elastic_load_paid_diff = elastic_load_paid - base_elastic_load_paid
    
    demand = shiftable_load + elastic_load
    wtp = shiftable_load_wtp + elastic_load_cs_diff + elastic_load_paid_diff
    
    return (demand, wtp)
