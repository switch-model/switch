"""
cancel out the basic system load and replace it with a convex combination of bids

note: the demand_module (or some subsidiary module) may store calibration data
at the module level (not in the model), so this module should only be used with one 
model at a time. An alternative approach would be to receive a calibration_data 
object back from demand_module.calibrate(), then add that to the model and pass
it back to the bid function when needed.

note: we also take advantage of this assumption and store a reference to the
current demand_module in this module (rather than storing it in the model itself)
"""

import os, sys
from pprint import pprint
from pyomo.environ import *
import switch_mod.utilities as utilities
demand_module = None    # will be set via command-line options

import util
from util import get

def define_arguments(argparser):
    argparser.add_argument("--dr-flat-pricing", action='store_true', default=False,
        help="Charge a constant (average) price for electricity, rather than varying hour by hour")
    argparser.add_argument("--dr-total-cost-pricing", action='store_true', default=False,
        help="Include both marginal and non-marginal(fixed) costs when setting prices")
    argparser.add_argument("--dr-elasticity-scenario", type=int, default=3,
        help="Choose a scenario of customer elasticity (1-3), defined in the demand_module")
    argparser.add_argument("--dr-demand-module", default=None,
        help="Name of module to use for demand-response bids. This should also be "
        "specified in the modules list, and should provide calibrate() and bid() functions. "
        "Pre-written options include constant_elasticity_demand_system or r_demand_system. "
        "Specify one of these in the modules list and use --help again to see module-specific options.")

def define_components(m):

    ###################
    # Choose the right demand module.
    # NOTE: we assume only one model will be run at a time, so it's safe to store
    # the setting in this module instead of in the model.
    ##################

    global demand_module
    if m.options.dr_demand_module is None:
        raise RuntimeError(
            "No demand module was specified for the demand_response system; unable to continue. "
            "Please use --dr-demand-module <module_name> in options.txt, scenarios.txt or on "
            "the command line. "
            "You should also add this module to the list of modules to load "
            " via modules.txt or --include-module <module_name>."
        )
    if m.options.dr_demand_module not in sys.modules:
        raise RuntimeError(
            "Demand module {mod} cannot be used because it has not been loaded. "
            "Please add this module to the the modules list (usually modules.txt) "
            "or specify --include-module {mod} in options.txt or on the command line."
            "".format(mod=m.options.dr_demand_module)
        )
    demand_module = sys.modules[m.options.dr_demand_module]
    
    # Make sure the model has a dual suffix
    if not hasattr(m, "dual"):
        m.dual = Suffix(direction=Suffix.IMPORT)
    
    ###################
    # Unserved load, with a penalty.
    # to ensure the model is always feasible, no matter what demand bids we get
    ##################

    # cost per MWh for unserved load (high)
    m.dr_unserved_load_penalty_per_mwh = Param(default=10000)
    # amount of unserved load during each timepoint
    m.DRUnservedLoad = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    # total cost for unserved load
    m.DR_Unserved_Load_Penalty = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        sum(m.DRUnservedLoad[lz, tp] * m.dr_unserved_load_penalty_per_mwh for lz in m.LOAD_ZONES)
    )
    # add the unserved load to the model's energy balance
    m.LZ_Energy_Components_Produce.append('DRUnservedLoad')
    # add the unserved load penalty to the model's objective function
    m.cost_components_tp.append('DR_Unserved_Load_Penalty')

    ###################
    # Price Responsive Demand bids
    ##################
    
    # list of all bids that have been received from the demand system
    m.DR_BID_LIST = Set(initialize = [], ordered=True)
    # we need an explicit indexing set for everything that depends on DR_BID_LIST
    # so we can reconstruct it (and them) each time we add an element to DR_BID_LIST
    # (not needed, and actually doesn't work -- reconstruct() fails for sets)
    # m.DR_BIDS_LZ_TP = Set(initialize = lambda m: m.DR_BID_LIST * m.LOAD_ZONES * m.TIMEPOINTS)
    # m.DR_BIDS_LZ_TS = Set(initialize = lambda m: m.DR_BID_LIST * m.LOAD_ZONES * m.TIMESERIES)
    
    # data for the individual bids; each load_zone gets one bid for each timeseries,
    # and each bid covers all the timepoints in that timeseries. So we just record 
    # the bid for each timepoint for each load_zone.
    m.dr_bid = Param(m.DR_BID_LIST, m.LOAD_ZONES, m.TIMEPOINTS, mutable=True)

    # price used to get this bid (only kept for reference)
    m.dr_price = Param(m.DR_BID_LIST, m.LOAD_ZONES, m.TIMEPOINTS, mutable=True)

    # the private benefit of serving each bid
    m.dr_bid_benefit = Param(m.DR_BID_LIST, m.LOAD_ZONES, m.TIMESERIES, mutable=True)

    # weights to assign to the bids for each timeseries when constructing an optimal demand profile
    m.DRBidWeight = Var(m.DR_BID_LIST, m.LOAD_ZONES, m.TIMESERIES, within=NonNegativeReals)
    
    # def DR_Convex_Bid_Weight_rule(m, lz, ts):
    #     if len(m.DR_BID_LIST) == 0:
    #         print "no items in m.DR_BID_LIST, skipping DR_Convex_Bid_Weight constraint"
    #         return Constraint.Skip
    #     else:
    #         print "constructing DR_Convex_Bid_Weight constraint"
    #         return (sum(m.DRBidWeight[b, lz, ts] for b in m.DR_BID_LIST) == 1)
    # 
    # choose a convex combination of bids for each zone and timeseries
    m.DR_Convex_Bid_Weight = Constraint(m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, lz, ts: 
        Constraint.Skip if len(m.DR_BID_LIST) == 0 
            else (sum(m.DRBidWeight[b, lz, ts] for b in m.DR_BID_LIST) == 1)
    )
    
    # Since we don't have differentiated prices for each zone, we have to use the same
    # weights for all zones. (Otherwise the model will try to micromanage load in each
    # zone, but that won't be reflected in the prices we report.)
    # Note: LOAD_ZONES is not an ordered set, so we have to use a trick to get a single
    # arbitrary one to refer to (next(iter(m.LOAD_ZONES)) would also work).
    m.DR_Load_Zone_Shared_Bid_Weight = Constraint(
        m.DR_BID_LIST, m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, b, lz, ts: 
            m.DRBidWeight[b, lz, ts] == m.DRBidWeight[b, list(m.LOAD_ZONES)[0], ts]
    )

    # For flat-price models, we have to use the same weight for all timeseries within the
    # same year (period), because there is only one price for the whole period, so it can't
    # induce different adjustments in individual timeseries.
    if m.options.dr_flat_pricing:
        m.DR_Flat_Bid_Weight = Constraint(
            m.DR_BID_LIST, m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, b, lz, ts: 
                m.DRBidWeight[b, lz, ts] 
                == m.DRBidWeight[b, lz, m.tp_ts[m.PERIOD_TPS[m.ts_period[ts]].first()]]
        )
                
    
    # Optimal level of demand, calculated from available bids (negative, indicating consumption)
    m.FlexibleDemand = Expression(m.LOAD_ZONES, m.TIMEPOINTS, 
        rule=lambda m, lz, tp:
            sum(m.DRBidWeight[b, lz, m.tp_ts[tp]] * m.dr_bid[b, lz, tp] for b in m.DR_BID_LIST)
    )

    # # FlexibleDemand reported as an adjustment (negative equals more demand)
    # # We have to do it this way because there's no way to remove the lz_demand_mw from the model
    # # without changing the core code.
    # m.DemandPriceResponse = Expression(m.LOAD_ZONES, m.TIMEPOINTS, 
    #     rule=lambda m, lz, tp: m.lz_demand_mw[lz, tp] - m.FlexibleDemand[lz, tp]
    # )
    
    # private benefit of the electricity consumption 
    # (i.e., willingness to pay for the current electricity supply)
    # reported as negative cost, i.e., positive benefit
    # also divide by number of timepoints in the timeseries
    # to convert from a cost per timeseries to a cost per timepoint.
    m.DR_Welfare_Cost = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        (-1.0) 
        * sum(m.DRBidWeight[b, lz, m.tp_ts[tp]] * m.dr_bid_benefit[b, lz, m.tp_ts[tp]] 
            for b in m.DR_BID_LIST for lz in m.LOAD_ZONES) 
        * m.tp_duration_hrs[tp] / m.ts_num_tps[m.tp_ts[tp]]
    )

    # add the private benefit to the model's objective function
    m.cost_components_tp.append('DR_Welfare_Cost')

    # annual costs, recovered via baseline prices
    # but not included in switch's calculation of costs
    m.other_costs = Param(m.PERIODS, mutable=True, default=0.0)
    m.cost_components_annual.append('other_costs')
    
    # variable to store the baseline data
    m.base_data = None

def post_iterate(m):
    print "\n\n======================================================="
    print "Solved model"
    print "======================================================="
    print "Total cost: ${v:,.0f}".format(v=value(m.SystemCost))
    print "marginal costs (first day):"
    print [
        electricity_marginal_cost(m, lz, tp) 
            for lz in m.LOAD_ZONES
                for tp in m.TS_TPS[m.TIMESERIES[1]]
    ]
    print "marginal costs (second day):"
    print [
        electricity_marginal_cost(m, lz, tp) 
            for lz in m.LOAD_ZONES
                for tp in m.TS_TPS[m.TIMESERIES[2]]
    ]

    # if m.iteration_number % 5 == 0:
    #     # save time by only writing results every 5 iterations
    # write_results(m)

    # Retrieve SystemCost before calling update_demand()
    # because that breaks SystemCost until the next solve
    old_SystemCost = getattr(m, "last_SystemCost", None)
    new_SystemCost = value(m.SystemCost)
    m.last_SystemCost = new_SystemCost
    if m.iteration_number > 0:
        # store cost of current solution before it gets altered by update_demand()
        current_cost = value(sum(
            (
                sum(
                    electricity_marginal_cost(m, lz, tp) * electricity_demand(m, lz, tp)
                        for lz in m.LOAD_ZONES 
                ) + m.DR_Welfare_Cost[tp]
            ) * m.bring_timepoint_costs_to_base_year[tp]
                for ts in m.TIMESERIES
                    for tp in m.TS_TPS[ts]
        ))
    
    update_demand(m)

    if m.iteration_number > 0:
        # get an estimate of best possible net cost of serving load
        # (if we could completely serve the last bid at the prices we quoted,
        # that would be an optimum; the actual cost may be higher but never lower)
        b = m.DR_BID_LIST.last()
        best_cost = value(sum(
            sum(
                electricity_marginal_cost(m, lz, tp) * m.dr_bid[b, lz, tp] 
                - m.dr_bid_benefit[b, lz, ts] * m.tp_duration_hrs[tp] / m.ts_num_tps[ts]
                    for lz in m.LOAD_ZONES 
            ) * m.bring_timepoint_costs_to_base_year[tp]
                for ts in m.TIMESERIES
                    for tp in m.TS_TPS[ts]
        ))
        print "last_SystemCost={}, SystemCost={}, ratio={}".format(
            old_SystemCost, new_SystemCost, new_SystemCost/old_SystemCost)
        print "lower bound={}, current cost={}, ratio={}".format(
            best_cost, current_cost, current_cost/best_cost)
        print "discount factors: " + " ".join([
            "{}={}".format(p, m.bring_timepoint_costs_to_base_year[m.PERIOD_TPS[p].first()])
                for p in m.PERIODS
        ])

    # Check for convergence (no progress during the last iteration)
    converged = (m.iteration_number > 0 and new_SystemCost == old_SystemCost)
        
    return converged

def update_demand(m):
    """
    This should be called after solving the model, in order to calculate new bids
    to include in future runs. The first time through, it also uses the fixed demand
    and marginal costs to calibrate the demand system, and then replaces the fixed
    demand with the flexible demand system.
    """
    first_run = (m.base_data is None)
    outputs_dir = m.options.outputs_dir
    tag = m.options.scenario_name

    print "attaching new demand bid to model"
    if first_run:
        calibrate_model(m)

        util.create_table(
            output_file=os.path.join(outputs_dir, "bid_weights_{t}.tsv".format(t=tag)), 
            headings=("iteration", "load_zone", "timeseries", "bid_num", "weight")
        )
    else:   # not first run
        # print "m.DRBidWeight (first day):"
        # print [(b, lz, ts, value(m.DRBidWeight[b, lz, ts])) 
        #     for b in m.DR_BID_LIST
        #     for lz in m.LOAD_ZONES
        #     for ts in m.TIMESERIES]
        print "m.DRBidWeight:"
        pprint([(lz, ts, [(b, value(m.DRBidWeight[b, lz, ts])) for b in m.DR_BID_LIST])
            for lz in m.LOAD_ZONES
            for ts in m.TIMESERIES])
        #print "DR_Convex_Bid_Weight:"
        #m.DR_Convex_Bid_Weight.pprint()

        # store the current bid weights for future reference
        # This should be done before adding the new bid.
        util.append_table(m, m.LOAD_ZONES, m.TIMESERIES, m.DR_BID_LIST, 
            output_file=os.path.join(outputs_dir, "bid_weights_{t}.tsv".format(t=tag)), 
            values=lambda m, lz, ts, b: (len(m.DR_BID_LIST), lz, ts, b, m.DRBidWeight[b, lz, ts])
        )

    # get new bids from the demand system at the current prices
    bids = get_bids(m)
    
    print "adding bids to model"
    # print "first day (lz, ts, prices, demand, wtp) ="
    # pprint(bids[0])
    # add the new bids to the model
    add_bids(m, bids)
    print "m.dr_bid_benefit (first day):"
    pprint([(b, lz, ts, value(m.dr_bid_benefit[b, lz, ts])) 
        for b in m.DR_BID_LIST
        for lz in m.LOAD_ZONES
        for ts in [m.TIMESERIES.first()]])
    
    # print "m.dr_bid (first day):"
    # print [(b, lz, ts, value(m.dr_bid[b, lz, ts]))
    #     for b in m.DR_BID_LIST
    #     for lz in m.LOAD_ZONES 
    #     for ts in m.TS_TPS[m.TIMESERIES.first()]]
    
    if first_run:
        # replace lz_demand_mw with FlexibleDemand in the energy balance constraint
        # note: it is easiest to do this after retrieving the bids because this
        # destroys the dual values which are needed for calculating the bids
        # note: the first two lines are simpler than the method I use, but my approach
        # preserves the ordering of the list, which is nice for reporting.
        # m.LZ_Energy_Components_Consume.remove('lz_demand_mw')
        # m.LZ_Energy_Components_Consume.append('FlexibleDemand')
        ecc = m.LZ_Energy_Components_Consume
        ecc[ecc.index('lz_demand_mw')] = 'FlexibleDemand'
        reconstruct_energy_balance(m)

def sum_product(vector1, vector2):
    return sum(v1*v2 for (v1, v2) in zip(vector1, vector2))

def total_direct_costs_per_year(m, period):
    """Return undiscounted total cost per year, during each period, as calculated by SWITCH,
    including everything except DR_Welfare_Cost.

    note: during the first iteration, this doesn't include "other_costs", but in later 
    iterations it does.

    This code comes from financials.calc_sys_costs_per_period(), excluding discounting
    and upscaling to the period.
    
    NOTE: ideally this would give costs by zone and period, to allow calibration for different
    utilities within a large study. But the cost components don't distinguish that way.
    (They probably should, since that would allow us to discuss average electricity costs
    in each zone.)
    """
    return value(
        sum(getattr(m, annual_cost)[period] for annual_cost in m.cost_components_annual)
        + sum(
            getattr(m, tp_cost)[t] * m.tp_weight_in_year[t]
            for t in m.PERIOD_TPS[period]
                for tp_cost in m.cost_components_tp
                    if tp_cost != "DR_Welfare_Cost"
        )
    )    

def electricity_marginal_cost(m, lz, tp):
    """Return marginal cost of production per MWh in load_zone lz during timepoint tp."""
    return m.dual[m.Energy_Balance[lz, tp]]/m.bring_timepoint_costs_to_base_year[tp]

def electricity_demand(m, lz, tp):
    """Return total electricity consumption by customers in load_zone lz during timepoint tp."""
    return value(sum(
        getattr(m, component)[lz, tp]
            for component in ('lz_demand_mw', 'FlexibleDemand')
                if component in m.LZ_Energy_Components_Consume
    ))
    
def make_prices(m):
    """Calculate hourly prices for customers, based on the current model configuration.
    These may be any combination of marginal vs. total-cost and flat vs. dynamic.
    """

    if m.options.dr_total_cost_pricing:
        # rescale (long-run) marginal costs to recover all costs 
        # (sunk and other, in addition to marginal)
        # calculate the ratio between potential revenue 
        # at marginal-cost pricing and total costs for each period
        mc_annual_revenue = {
            (lz, p): 
            sum(
                electricity_demand(m, lz, tp) 
                * electricity_marginal_cost(m, lz, tp) 
                * m.tp_weight_in_year[tp]
                for tp in m.PERIOD_TPS[p]
            )
            for lz in m.LOAD_ZONES for p in m.PERIODS
        }
        # note: it would be nice to do this on a zonal basis, but production costs
        # are only available model-wide.
        price_scalar = {
            p: total_direct_costs_per_year(m, p) 
                / sum(mc_annual_revenue[lz, p] for lz in m.LOAD_ZONES) 
            for p in m.PERIODS
        }
    else:
        # use marginal costs directly as prices
        price_scalar = {p: 1.0 for p in m.PERIODS}
        
    # calculate hourly prices
    hourly_prices = {
        (lz, tp): price_scalar[m.tp_period[tp]] * electricity_marginal_cost(m, lz, tp)
            for lz in m.LOAD_ZONES for tp in m.TIMEPOINTS
    }
    
    if m.options.dr_flat_pricing:
        # use flat prices each year
        # calculate annual average prices (total revenue / total kWh)
        average_prices = {
            (lz, p): 
            sum(
                hourly_prices[lz, tp] 
                * electricity_demand(m, lz, tp) 
                * m.tp_weight_in_year[tp] 
                for tp in m.PERIOD_TPS[p]
            ) 
            / 
            sum(
                electricity_demand(m, lz, tp) 
                * m.tp_weight_in_year[tp] 
                for tp in m.PERIOD_TPS[p]
            )
            for lz in m.LOAD_ZONES for p in m.PERIODS
        }
        prices = {
            (lz, tp): average_prices[lz, m.tp_period[tp]]
            for lz in m.LOAD_ZONES for tp in m.TIMEPOINTS
        }
    else:
        prices = hourly_prices
    
    return prices

annual_revenue = None

def calibrate_model(m):
    global annual_revenue   # save a copy for debugging later
    """
    Calibrate the demand system and add it to the model. 
    Also calculate other_costs (utility costs not modeled by SWITCH).
    """
    
    # base_data consists of a list of tuples showing (load_zone, timeseries, base_load (list) and base_price)
    # note: the constructor below assumes list comprehensions will preserve the order of the underlying list
    # (which is guaranteed according to http://stackoverflow.com/questions/1286167/is-the-order-of-results-coming-from-a-list-comprehension-guaranteed)
    
    # calculate the average-cost price for the current study period
    # TODO: store monthly retail prices in system_load, and find annual average prices
    # that correspond to the load forecasts for each period, then store scale factors
    # in system_load_scale to convert 2007-08 monthly prices into monthly prices for other
    # years (same technique as rescaling the loads, but only adjusting the mean), then
    # report base prices for each timepoint along with the loads in loads.tab.
    # For now, we just assume the base price was $180/MWh, which is HECO's average price in
    # 2007 according to EIA form 826. 
    # TODO: add in something for the fixed costs, to make marginal cost commensurate with the base_price
    #baseCosts = [m.dual[m.EnergyBalance[lz, tp]] for lz in m.LOAD_ZONES for tp in m.TIMEPOINTS]
    base_price = 180  # average retail price for 2007 ($/MWh)
    m.base_data = [(
        lz, 
        ts, 
        [m.lz_demand_mw[lz, tp] for tp in m.TS_TPS[ts]],
        [base_price] * len(m.TS_TPS[ts])
    ) for lz in m.LOAD_ZONES for ts in m.TIMESERIES]
    
    # make a dict of base_data, indexed by load_zone and timepoint, for later reporting
    m.base_data_dict = {
        (lz, tp): (m.lz_demand_mw[lz, tp], base_price) 
            for lz in m.LOAD_ZONES for tp in m.TIMEPOINTS
    }
    
    # calculate costs that are included in the base prices but not reflected in SWITCH.
    # note: during the first iteration, other_costs = 0, so this calculates a value for
    # other_costs that will bring total_direct_costs_per_year() up to the baseline 
    # annual_revenue level.
    # note: this will break if we use varying durations for individual timepoints in a timeseries (unlikely)
    annual_revenue = dict(zip(list(m.PERIODS), [0.0]*len(m.PERIODS)))
    for lz, ts, loads, prices in m.base_data:
        annual_revenue[m.ts_period[ts]] += sum_product(loads, prices) * m.tp_weight_in_year[m.TS_TPS[ts].first()]
    for p in m.PERIODS:
        m.other_costs[p] = annual_revenue[p] - total_direct_costs_per_year(m, p)
    
    # calibrate the demand module
    demand_module.calibrate(m.base_data, m.options.dr_elasticity_scenario)

    # note: SystemCostPerPeriod and SystemCost will get reconstructed
    # in add_bids later in the first iteration, so there's no need to reconstruct them here.


def get_bids(m):
    """Get bids for loads and willingness-to-pay from the demand system at the current prices.
    
    Each bid is a tuple of (load_zone, timeseries, [hourly prices], [hourly demand], wtp)
    """

    bids = []
    all_prices = make_prices(m)


    for i, (lz, ts, base_load, base_price) in enumerate(m.base_data):
        
        # if i < 2:
        #     print "prices (day {i}): {p}".format(i=i, p=prices)
        #     print "weights: {w}".format(w=[m.bring_timepoint_costs_to_base_year[tp] for tp in m.TS_TPS[ts]])

        prices = [all_prices[(lz, tp)] for tp in m.TS_TPS[ts]]
        
        demand, wtp = demand_module.bid(lz, ts, prices)

        bids.append((lz, ts, prices, demand, wtp))

        # if i < 2:
        #     import pdb; pdb.set_trace()

    return bids
    

def add_bids(m, bids):
    """ 
    accept a list of bids written as tuples like
    (lz, ts, prices, demand, wtp)
    where lz is the load zone, ts is the timeseries, 
    demand is a list of demand levels for the timepoints during that series, 
    and wtp is the private benefit from consuming the amount of power in that bid.
    Then add that set of bids to the model
    """
    # create a bid ID and add it to the list of bids
    if len(m.DR_BID_LIST) == 0:
        b = 1
    else:
        b = max(m.DR_BID_LIST) + 1

    tag = m.options.scenario_name
    outputs_dir = m.options.outputs_dir
    
    m.DR_BID_LIST.add(b)
    # m.DR_BIDS_LZ_TP.reconstruct()
    # m.DR_BIDS_LZ_TS.reconstruct()
    # add the bids for each load zone and timepoint to the dr_bid list
    for (lz, ts, prices, demand, wtp) in bids:
        # record the private benefit
        m.dr_bid_benefit[b, lz, ts] = wtp
        # record the level of demand for each timepoint
        timepoints = m.TS_TPS[ts]
        # print "ts: "+str(ts)
        # print "demand: " + str(demand)
        # print "timepoints: " + str([t for t in timepoints])
        for i, d in enumerate(demand):
            # print "i+1: "+str(i+1)
            # print "d: "+str(d)
            # print "timepoints[i+1]: "+str(timepoints[i+1])
            # note: demand is a python list or array, which uses 0-based indexing, but
            # timepoints is a pyomo set, which uses 1-based indexing, so we have to shift the index by 1.
            m.dr_bid[b, lz, timepoints[i+1]] = d
            m.dr_price[b, lz, timepoints[i+1]] = prices[i]

    print "len(m.DR_BID_LIST): {l}".format(l=len(m.DR_BID_LIST))
    print "m.DR_BID_LIST: {b}".format(b=[x for x in m.DR_BID_LIST])

    # store bid information for later reference
    # this has to be done after the model is updated and
    # before DRBidWeight is reconstructed (which destroys the duals)
    if b == 1:
        util.create_table(
            output_file=os.path.join(outputs_dir, "bid_{t}.tsv".format(t=tag)), 
            headings=(
                "bid_num", "load_zone", "timeseries", "timepoint", "marginal_cost", "price", 
                "bid_load", "wtp", "base_price", "base_load"
            )
        )   
    util.append_table(m, m.LOAD_ZONES, m.TIMEPOINTS,
        output_file=os.path.join(outputs_dir, "bid_{t}.tsv".format(t=tag)), 
        values=lambda m, lz, tp: (
            b,
            lz,
            m.tp_ts[tp],
            m.tp_timestamp[tp],
            electricity_marginal_cost(m, lz, tp),
            m.dr_price[max(m.DR_BID_LIST), lz, tp],
            m.dr_bid[max(m.DR_BID_LIST), lz, tp],
            m.dr_bid_benefit[b, lz, m.tp_ts[tp]],
            m.base_data_dict[lz, tp][1],
            m.base_data_dict[lz, tp][0],
        )
    )

    write_results(m)
    write_batch_results(m)

    # reconstruct the components that depend on m.DR_BID_LIST, m.dr_bid_benefit and m.dr_bid
    m.DRBidWeight.reconstruct()
    m.DR_Convex_Bid_Weight.reconstruct()
    m.FlexibleDemand.reconstruct()
    m.DR_Welfare_Cost.reconstruct()
    # it seems like we have to reconstruct the higher-level components that depend on these 
    # ones (even though these are Expressions), because otherwise they refer to objects that
    # used to be returned by the Expression but aren't any more (e.g., versions of DRBidWeight 
    # that no longer exist in the model).
    # (i.e., Energy_Balance refers to the items returned by FlexibleDemand instead of referring 
    # to FlexibleDemand itself)
    reconstruct_energy_balance(m)
    m.SystemCostPerPeriod.reconstruct()
    m.SystemCost.reconstruct()

def reconstruct_energy_balance(m):
    """Reconstruct Energy_Balance constraint, preserving dual values (if present)."""
    # copy the existing Energy_Balance object
    old_Energy_Balance = dict(m.Energy_Balance)
    m.Energy_Balance.reconstruct()
    for k in old_Energy_Balance:
        # change dual entries to match new Energy_Balance objects
        m.dual[m.Energy_Balance[k]] = m.dual.pop(old_Energy_Balance[k])
    

def write_batch_results(m):
    # append results to the batch results file, creating it if needed
    output_file = os.path.join(m.options.outputs_dir, "demand_response_summary.tsv")

    # create a file to hold batch results if it doesn't already exist
    # note: we retain this file across scenarios so it can summarize all results,
    # but this means it needs to be manually cleared before launching a new 
    # batch of scenarios (e.g., when running get_scenario_data or clearing the
    # scenario_queue directory)
    if not os.path.isfile(output_file):
        util.create_table(output_file=output_file, headings=summary_headers(m))
    
    util.append_table(m, output_file=output_file, values=lambda m: summary_values(m))

def summary_headers(m):
    return (
        ("tag", "iteration", "total_cost")
        +tuple('total_direct_costs_per_year_'+str(p) for p in m.PERIODS)
        +tuple('other_costs_'+str(p) for p in m.PERIODS)
        +tuple('DR_Welfare_Cost_'+str(p) for p in m.PERIODS)
        +tuple('customer_payments_'+str(p) for p in m.PERIODS)
        +tuple('MWh_sold_'+str(p) for p in m.PERIODS)
    )
    
def summary_values(m):
    demand_components = [
        c for c in ('lz_demand_mw', 'DemandResponse', 'ChargeEVs', 'FlexibleDemand') if hasattr(m, c)
    ]
    values = []
    
    # tag (configuration)
    values.extend([
        m.options.scenario_name,
        m.iteration_number,
        m.SystemCost  # total cost (all periods)
    ])
    
    # direct costs (including "other")
    values.extend([total_direct_costs_per_year(m, p) for p in m.PERIODS])
    
    # other_costs
    values.extend([m.other_costs[p] for p in m.PERIODS])
    
    # DR_Welfare_Cost
    values.extend([
        sum(m.DR_Welfare_Cost[t] * m.tp_weight_in_year[t] for t in m.PERIOD_TPS[p])
        for p in m.PERIODS
    ])
    
    # payments by customers ([expected load] * [price offered for that load])
    last_bid = m.DR_BID_LIST.last()
    values.extend([
        sum(
            electricity_demand(m, lz, tp) * m.dr_price[last_bid, lz, tp] * m.tp_weight_in_year[tp]
            for lz in m.LOAD_ZONES for tp in m.PERIOD_TPS[p]
        )
        for p in m.PERIODS
    ])
    
    # total MWh delivered each year
    values.extend([
        sum(
            electricity_demand(m, lz, tp) * m.tp_weight_in_year[tp]
            for lz in m.LOAD_ZONES for tp in m.PERIOD_TPS[p]
        )
        for p in m.PERIODS
    ])

    return values

def write_results(m):
    outputs_dir = m.options.outputs_dir
    tag = filename_tag(m)
            
    avg_ts_scale = float(sum(m.ts_scale_to_year[ts] for ts in m.TIMESERIES))/len(m.TIMESERIES)
    last_bid = m.DR_BID_LIST.last()
    
    util.write_table(
        m, m.LOAD_ZONES, m.TIMEPOINTS,
        output_file=os.path.join(outputs_dir, "energy_sources{t}.tsv".format(t=tag)), 
        headings=
            ("load_zone", "period", "timepoint_label")
            +tuple(m.FUELS)
            +tuple(m.NON_FUEL_ENERGY_SOURCES)
            +tuple("curtail_"+s for s in m.NON_FUEL_ENERGY_SOURCES)
            +tuple(m.LZ_Energy_Components_Produce)
            +tuple(m.LZ_Energy_Components_Consume)
            +("marginal_cost","price","peak_day","base_load","base_price"),
        values=lambda m, z, t: 
            (z, m.tp_period[t], m.tp_timestamp[t]) 
            +tuple(
                sum(get(m.DispatchProjByFuel, (p, t, f), 0.0) for p in m.PROJECTS_BY_FUEL[f])
                for f in m.FUELS
            )
            +tuple(
                sum(get(m.DispatchProj, (p, t), 0.0) for p in m.PROJECTS_BY_NON_FUEL_ENERGY_SOURCE[s])
                for s in m.NON_FUEL_ENERGY_SOURCES
            )
            +tuple(
                sum(
                    get(m.DispatchUpperLimit, (p, t), 0.0) - get(m.DispatchProj, (p, t), 0.0) 
                    for p in m.PROJECTS_BY_NON_FUEL_ENERGY_SOURCE[s]
                )
                for s in m.NON_FUEL_ENERGY_SOURCES
            )
            +tuple(getattr(m, component)[z, t] for component in m.LZ_Energy_Components_Produce)
            +tuple(getattr(m, component)[z, t] for component in m.LZ_Energy_Components_Consume)
            +(
                electricity_marginal_cost(m, z, t),
                m.dr_price[last_bid, z, t],
                'peak' if m.ts_scale_to_year[m.tp_ts[t]] < 0.5*avg_ts_scale else 'typical',
                m.base_data_dict[z, t][0],
                m.base_data_dict[z, t][1],
            )
    )
    
    # import pprint
    # b=[(pr, pe, value(m.BuildProj[pr, pe]), m.proj_gen_tech[pr], m.proj_overnight_cost[pr, pe]) for (pr, pe) in m.BuildProj if value(m.BuildProj[pr, pe]) > 0]
    # bt=set(x[3] for x in b) # technologies
    # pprint([(t, sum(x[2] for x in b if x[3]==t), sum(x[4] for x in b if x[3]==t)/sum(1.0 for x in b if x[3]==t)) for t in bt])


def filename_tag(m):
    if m.options.scenario_name:
        t = m.options.scenario_name + "_"
    else:
        t = ""
    t = t + "_".join(map(str, m.iteration_node))
    if t:
        t = "_" + t
    return t

