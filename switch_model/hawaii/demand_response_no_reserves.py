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

import os, sys, time
from pprint import pprint
from pyomo.environ import *
import switch_model.utilities as utilities
demand_module = None    # will be set via command-line options

import util
from util import get

def define_arguments(argparser):
    argparser.add_argument("--dr-flat-pricing", action='store_true', default=False,
        help="Charge a constant (average) price for electricity, rather than varying hour by hour")
    argparser.add_argument("--dr-total-cost-pricing", action='store_true', default=False,
        help="Include both marginal and non-marginal(fixed) costs when setting prices")
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
    
    # Make sure the model has dual and rc suffixes
    if not hasattr(m, "dual"):
        m.dual = Suffix(direction=Suffix.IMPORT)
    if not hasattr(m, "rc"):
        m.rc = Suffix(direction=Suffix.IMPORT)
    
    ###################
    # Unserved load, with a penalty.
    # to ensure the model is always feasible, no matter what demand bids we get
    ##################

    # cost per MWh for unserved load (high)
    m.dr_unserved_load_penalty_per_mwh = Param(initialize=10000)
    # amount of unserved load during each timepoint
    m.DRUnservedLoad = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    # total cost for unserved load
    m.DR_Unserved_Load_Penalty = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        sum(m.DRUnservedLoad[z, tp] * m.dr_unserved_load_penalty_per_mwh for z in m.LOAD_ZONES)
    )
    # add unserved load to the zonal energy balance
    m.Zone_Power_Injections.append('DRUnservedLoad')
    # add the unserved load penalty to the model's objective function
    m.Cost_Components_Per_TP.append('DR_Unserved_Load_Penalty')

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
    
    # def DR_Convex_Bid_Weight_rule(m, z, ts):
    #     if len(m.DR_BID_LIST) == 0:
    #         print "no items in m.DR_BID_LIST, skipping DR_Convex_Bid_Weight constraint"
    #         return Constraint.Skip
    #     else:
    #         print "constructing DR_Convex_Bid_Weight constraint"
    #         return (sum(m.DRBidWeight[b, z, ts] for b in m.DR_BID_LIST) == 1)
    # 
    # choose a convex combination of bids for each zone and timeseries
    m.DR_Convex_Bid_Weight = Constraint(m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, z, ts: 
        Constraint.Skip if len(m.DR_BID_LIST) == 0 
            else (sum(m.DRBidWeight[b, z, ts] for b in m.DR_BID_LIST) == 1)
    )
    
    # Since we don't have differentiated prices for each zone, we have to use the same
    # weights for all zones. (Otherwise the model will try to micromanage load in each
    # zone, but that won't be reflected in the prices we report.)
    # Note: LOAD_ZONES is not an ordered set, so we have to use a trick to get a single
    # arbitrary one to refer to (next(iter(m.LOAD_ZONES)) would also work).
    m.DR_Load_Zone_Shared_Bid_Weight = Constraint(
        m.DR_BID_LIST, m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, b, z, ts: 
            m.DRBidWeight[b, z, ts] == m.DRBidWeight[b, list(m.LOAD_ZONES)[0], ts]
    )

    # For flat-price models, we have to use the same weight for all timeseries within the
    # same year (period), because there is only one price for the whole period, so it can't
    # induce different adjustments in individual timeseries.
    if m.options.dr_flat_pricing:
        m.DR_Flat_Bid_Weight = Constraint(
            m.DR_BID_LIST, m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, b, z, ts: 
                m.DRBidWeight[b, z, ts] 
                == m.DRBidWeight[b, z, m.tp_ts[m.TPS_IN_PERIOD[m.ts_period[ts]].first()]]
        )
                
    
    # Optimal level of demand, calculated from available bids (negative, indicating consumption)
    m.FlexibleDemand = Expression(m.LOAD_ZONES, m.TIMEPOINTS, 
        rule=lambda m, z, tp:
            sum(m.DRBidWeight[b, z, m.tp_ts[tp]] * m.dr_bid[b, z, tp] for b in m.DR_BID_LIST)
    )

    # replace zone_demand_mw with FlexibleDemand in the energy balance constraint
    # note: the first two lines are simpler than the method I use, but my approach
    # preserves the ordering of the list, which is nice for older spreadsheets that expect
    # a certain ordering.
    # m.Zone_Power_Withdrawals.remove('zone_demand_mw')
    # m.Zone_Power_Withdrawals.append('FlexibleDemand')
    idx = m.Zone_Power_Withdrawals.index('zone_demand_mw')
    m.Zone_Power_Withdrawals[idx] = 'FlexibleDemand'

    # private benefit of the electricity consumption 
    # (i.e., willingness to pay for the current electricity supply)
    # reported as negative cost, i.e., positive benefit
    # also divide by number of timepoints in the timeseries
    # to convert from a cost per timeseries to a cost per timepoint.
    m.DR_Welfare_Cost = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        (-1.0) 
        * sum(m.DRBidWeight[b, z, m.tp_ts[tp]] * m.dr_bid_benefit[b, z, m.tp_ts[tp]] 
            for b in m.DR_BID_LIST for z in m.LOAD_ZONES) 
        * m.tp_duration_hrs[tp] / m.ts_num_tps[m.tp_ts[tp]]
    )

    # add the private benefit to the model's objective function
    m.Cost_Components_Per_TP.append('DR_Welfare_Cost')

    # annual costs, recovered via baseline prices
    # but not included in switch's calculation of costs
    m.other_costs = Param(m.PERIODS, mutable=True, default=0.0)
    m.Cost_Components_Per_Period.append('other_costs')
    
    # variable to store the baseline data
    m.base_data = None

def pre_iterate(m):
    # could all prev values be stored in post_iterate?
    # then this func would just alter the model based on values calculated in post_iterate
    # (e.g., get a bid based on current prices, add bid to model, rebuild components)
    
    # NOTE:
    # bids must be added to the model here, and the model must be reconstructed here, 
    # so the model can then be solved and remain in a "solved" state through the end
    # of post-iterate, to avoid problems in final reporting.
    
    # store various properties from previous model solution for later reference
    m.prev_marginal_cost = (
        {(z, tp): None for z in m.LOAD_ZONES for tp in m.TIMEPOINTS} # model hasn't been solved yet
        if m.iteration_number == 0 else 
        {(z, tp): electricity_marginal_cost(m, z, tp) for z in m.LOAD_ZONES for tp in m.TIMEPOINTS}
    )
    m.prev_demand = (
        {(z, tp): None for z in m.LOAD_ZONES for tp in m.TIMEPOINTS} # model hasn't been solved yet
        if m.iteration_number == 0 else 
        {(z, tp): electricity_demand(m, z, tp) for z in m.LOAD_ZONES for tp in m.TIMEPOINTS}
    )
    m.prev_SystemCost = (
        None
        if m.iteration_number == 0 else 
        value(m.SystemCost)
    )

    if m.iteration_number > 0:
        # store cost of previous solution before it gets altered by update_demand()
        # TODO: this and best_cost could probably be moved to post_iterate
        # Then we'd be comparing the final (current) solution to the best possible
        # solution based on the prior round of bids, rather than comparing the new
        # bid to the prior solution to the master problem. This is probably fine.
        # TODO: does this correctly account for producer surplus? It seems like that's
        # being treated as a cost (embedded in MC * demand); maybe this should use 
        # total direct cost instead,
        # or focus specifically on consumer surplus (use prices instead of MC as the
        # convergence measure). But maybe this is OK, since the question is, "if we
        # could serve the last bid at the MC we had then (which also means the PS
        # we had then? no change for altered volume?), would everyone be much
        # better off than they are with the allocation we have now chosen?"
        # Maybe using MC lets us focus on whether there can be another incrementally
        # different solution that would be much better than the one we have now. 
        # This ignores other solutions far away, where an integer variable is flipped,
        # but that's OK. (?)
        prev_cost = value(sum(
            (
                sum(
                    m.prev_marginal_cost[z, tp] * m.prev_demand[z, tp]
                        for z in m.LOAD_ZONES 
                ) + m.DR_Welfare_Cost[tp]
            ) * m.bring_timepoint_costs_to_base_year[tp]
                for ts in m.TIMESERIES
                    for tp in m.TPS_IN_TS[ts]
        ))
    
    # get the next bid and attach it to the model
    update_demand(m)

    b = m.DR_BID_LIST.last()    # current bid number

    if m.iteration_number > 0:
        # get an estimate of best possible net cost of serving load
        # (if we could completely serve the last bid at the prices we quoted,
        # that would be an optimum; the actual cost may be higher but never lower)
        best_cost = value(sum(
            sum(
                m.prev_marginal_cost[z, tp] * m.dr_bid[b, z, tp] 
                - m.dr_bid_benefit[b, z, ts] * m.tp_duration_hrs[tp] / m.ts_num_tps[ts]
                for z in m.LOAD_ZONES 
            ) 
            * m.bring_timepoint_costs_to_base_year[tp]
            for ts in m.TIMESERIES
            for tp in m.TPS_IN_TS[ts]
        ))
        print "lower bound={}, previous cost={}, ratio={}".format(
            best_cost, prev_cost, prev_cost/best_cost)

    # Check for convergence -- optimality gap is less than 0.1% of best possible cost 
    # (which may be negative)
    # TODO: index this to the direct costs, rather than the direct costs minus benefits
    # as it stands, it converges with about $50,000,000 optimality gap, which is about 
    # 3% of direct costs.
    converged = (m.iteration_number > 0 and (prev_cost - best_cost)/abs(best_cost) <= 0.0001)
        
    return converged

def post_iterate(m):
    print "\n\n======================================================="
    print "Solved model"
    print "======================================================="
    print "Total cost: ${v:,.0f}".format(v=value(m.SystemCost))


    # TODO: 
    # maybe calculate prices for the next round here and attach them to the
    # model, so they can be reported as final prices (currently we don't
    # report the final prices, only the prices prior to the final model run)

    SystemCost = value(m.SystemCost)    # calculate once to save time
    print "prev_SystemCost={}, SystemCost={}, ratio={}".format(
        m.prev_SystemCost, SystemCost, 
        None if m.prev_SystemCost is None else SystemCost/m.prev_SystemCost
    )

    tag = m.options.scenario_name
    outputs_dir = m.options.outputs_dir

    # report information on most recent bid
    if m.iteration_number == 0:
        util.create_table(
            output_file=os.path.join(outputs_dir, "bid_{t}.tsv".format(t=tag)), 
            headings=(
                "bid_num", "load_zone", "timeseries", "timepoint", "marginal_cost", "price", 
                "bid_load", "wtp", "base_price", "base_load"
            )
        )
    b = m.DR_BID_LIST.last()    # current bid
    util.append_table(m, m.LOAD_ZONES, m.TIMEPOINTS,
        output_file=os.path.join(outputs_dir, "bid_{t}.tsv".format(t=tag)), 
        values=lambda m, z, tp: (
            b,
            z,
            m.tp_ts[tp],
            m.tp_timestamp[tp],
            m.prev_marginal_cost[z, tp],
            m.dr_price[b, z, tp],
            m.dr_bid[b, z, tp],
            m.dr_bid_benefit[b, z, m.tp_ts[tp]],
            m.base_data_dict[z, tp][1],
            m.base_data_dict[z, tp][0],
        )
    )

    # store the current bid weights for future reference
    if m.iteration_number == 0:
        util.create_table(
            output_file=os.path.join(outputs_dir, "bid_weights_{t}.tsv".format(t=tag)), 
            headings=("iteration", "load_zone", "timeseries", "bid_num", "weight")
        )
    util.append_table(m, m.LOAD_ZONES, m.TIMESERIES, m.DR_BID_LIST, 
        output_file=os.path.join(outputs_dir, "bid_weights_{t}.tsv".format(t=tag)), 
        values=lambda m, z, ts, b: (len(m.DR_BID_LIST), z, ts, b, m.DRBidWeight[b, z, ts])
    )
    
    # report the dual costs
    write_dual_costs(m)

    # if m.iteration_number % 5 == 0:
    #     # save time by only writing results every 5 iterations
    # write_results(m)
    
    write_results(m)
    write_batch_results(m)


def update_demand(m):
    """
    This should be called after solving the model, in order to calculate new bids
    to include in future runs. The first time through, it also uses the fixed demand
    and marginal costs to calibrate the demand system, and then replaces the fixed
    demand with the flexible demand system.
    """
    first_run = (m.base_data is None)

    print "attaching new demand bid to model"
    if first_run:
        calibrate_model(m)
        
    else:   # not first run
        # print "m.DRBidWeight (first day):"
        # print [(b, z, ts, value(m.DRBidWeight[b, z, ts])) 
        #     for b in m.DR_BID_LIST
        #     for z in m.LOAD_ZONES
        #     for ts in m.TIMESERIES]
        print "m.DRBidWeight:"
        pprint([(z, ts, [(b, value(m.DRBidWeight[b, z, ts])) for b in m.DR_BID_LIST])
            for z in m.LOAD_ZONES
            for ts in m.TIMESERIES])
        #print "DR_Convex_Bid_Weight:"
        #m.DR_Convex_Bid_Weight.pprint()

    # get new bids from the demand system at the current prices
    bids = get_bids(m)
    
    print "adding bids to model"
    # print "first day (z, ts, prices, demand, wtp) ="
    # pprint(bids[0])
    # add the new bids to the model
    add_bids(m, bids)
    # print "m.dr_bid_benefit (first day):"
    # pprint([(b, z, ts, value(m.dr_bid_benefit[b, z, ts]))
    #     for b in m.DR_BID_LIST
    #     for z in m.LOAD_ZONES
    #     for ts in [m.TIMESERIES.first()]])
    
    # print "m.dr_bid (first day):"
    # print [(b, z, ts, value(m.dr_bid[b, z, ts]))
    #     for b in m.DR_BID_LIST
    #     for z in m.LOAD_ZONES 
    #     for ts in m.TPS_IN_TS[m.TIMESERIES.first()]]
    

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
        sum(getattr(m, annual_cost)[period] for annual_cost in m.Cost_Components_Per_Period)
        + sum(
            getattr(m, tp_cost)[t] * m.tp_weight_in_year[t]
            for t in m.TPS_IN_PERIOD[period]
                for tp_cost in m.Cost_Components_Per_TP
                    if tp_cost != "DR_Welfare_Cost"
        )
    )    

def electricity_marginal_cost(m, z, tp):
    """Return marginal cost of production per MWh in load_zone z during timepoint tp."""
    return m.dual[m.Energy_Balance[z, tp]]/m.bring_timepoint_costs_to_base_year[tp]

def electricity_demand(m, z, tp):
    """Return total electricity consumption by customers in load_zone z during timepoint tp."""
    return value(sum(
        getattr(m, component)[z, tp]
            for component in ('zone_demand_mw', 'FlexibleDemand')
                if component in m.Zone_Power_Withdrawals
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
            (z, p): 
            sum(
                electricity_demand(m, z, tp) 
                * electricity_marginal_cost(m, z, tp) 
                * m.tp_weight_in_year[tp]
                for tp in m.TPS_IN_PERIOD[p]
            )
            for z in m.LOAD_ZONES for p in m.PERIODS
        }
        # note: it would be nice to do this on a zonal basis, but production costs
        # are only available model-wide.
        price_scalar = {
            p: total_direct_costs_per_year(m, p) 
                / sum(mc_annual_revenue[z, p] for z in m.LOAD_ZONES) 
            for p in m.PERIODS
        }
    else:
        # use marginal costs directly as prices
        price_scalar = {p: 1.0 for p in m.PERIODS}
        
    # calculate hourly prices
    hourly_prices = {
        (z, tp): price_scalar[m.tp_period[tp]] * electricity_marginal_cost(m, z, tp)
            for z in m.LOAD_ZONES for tp in m.TIMEPOINTS
    }
    
    if m.options.dr_flat_pricing:
        # use flat prices each year
        # calculate annual average prices (total revenue / total kWh)
        average_prices = {
            (z, p): 
            sum(
                hourly_prices[z, tp] 
                * electricity_demand(m, z, tp) 
                * m.tp_weight_in_year[tp] 
                for tp in m.TPS_IN_PERIOD[p]
            ) 
            / 
            sum(
                electricity_demand(m, z, tp) 
                * m.tp_weight_in_year[tp] 
                for tp in m.TPS_IN_PERIOD[p]
            )
            for z in m.LOAD_ZONES for p in m.PERIODS
        }
        prices = {
            (z, tp): average_prices[z, m.tp_period[tp]]
            for z in m.LOAD_ZONES for tp in m.TIMEPOINTS
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
    #baseCosts = [m.dual[m.EnergyBalance[z, tp]] for z in m.LOAD_ZONES for tp in m.TIMEPOINTS]
    base_price = 180  # average retail price for 2007 ($/MWh)
    m.base_data = [(
        z, 
        ts, 
        [m.zone_demand_mw[z, tp] for tp in m.TPS_IN_TS[ts]],
        [base_price] * len(m.TPS_IN_TS[ts])
    ) for z in m.LOAD_ZONES for ts in m.TIMESERIES]
    
    # make a dict of base_data, indexed by load_zone and timepoint, for later reference
    m.base_data_dict = {
        (z, tp): (m.zone_demand_mw[z, tp], base_price) 
            for z in m.LOAD_ZONES for tp in m.TIMEPOINTS
    }
    
    # calculate costs that are included in the base prices but not reflected in SWITCH.
    # note: during the first iteration, other_costs = 0, so this calculates a value for
    # other_costs that will bring total_direct_costs_per_year() up to the baseline 
    # annual_revenue level.
    annual_revenue = dict(zip(list(m.PERIODS), [0.0]*len(m.PERIODS)))
    for (z, tp), (load, price) in m.base_data_dict.iteritems():
        annual_revenue[m.tp_period[tp]] += load * prices * m.tp_weight_in_year[tp]
    for p in m.PERIODS:
        # m.other_costs[p] = annual_revenue[p] - total_direct_costs_per_year(m, p)
        # disable other_costs calculation; these should be specified externally if at all
        m.other_costs[p] = 0.0
    
    # calibrate the demand module
    #demand_module.calibrate(m.base_data, m.options.dr_elasticity_scenario)
    demand_module.calibrate(m, m.base_data)


def get_bids(m):
    """Get bids for loads and willingness-to-pay from the demand system at the current prices.
    
    Each bid is a tuple of (load_zone, timeseries, [hourly prices], [hourly demand], wtp)
    """

    bids = []

    if m.iteration_number > 0:
        # calculate prices from last model solution
        all_prices = make_prices(m)
        # TODO: change make_prices to use base_price in iteration 0,
        # instead of doing it below


    for i, (z, ts, base_load, base_price) in enumerate(m.base_data):
        
        # if i < 2:
        #     print "prices (day {i}): {p}".format(i=i, p=prices)
        #     print "weights: {w}".format(w=[m.bring_timepoint_costs_to_base_year[tp] for tp in m.TPS_IN_TS[ts]])

        if m.iteration_number == 0:
            # use base prices on the first pass
            prices = base_price
        else:
            # use prices from last solution
            prices = [all_prices[(z, tp)] for tp in m.TPS_IN_TS[ts]]
        
        demand, wtp = demand_module.bid(m, z, ts, prices)

        bids.append((z, ts, prices, demand, wtp))

        # if i < 2:
        #     import pdb; pdb.set_trace()

    return bids
    

def add_bids(m, bids):
    """ 
    accept a list of bids written as tuples like
    (z, ts, prices, demand, wtp)
    where z is the load zone, ts is the timeseries, 
    demand is a list of demand levels for the timepoints during that series, 
    and wtp is the private benefit from consuming the amount of power in that bid.
    Then add that set of bids to the model
    """
    # create a bid ID and add it to the list of bids
    if len(m.DR_BID_LIST) == 0:
        b = 1
    else:
        b = max(m.DR_BID_LIST) + 1
    
    m.DR_BID_LIST.add(b)
    # m.DR_BIDS_LZ_TP.reconstruct()
    # m.DR_BIDS_LZ_TS.reconstruct()
    # add the bids for each load zone and timepoint to the dr_bid list
    for (z, ts, prices, demand, wtp) in bids:
        # record the private benefit
        m.dr_bid_benefit[b, z, ts] = wtp
        # record the level of demand for each timepoint
        timepoints = m.TPS_IN_TS[ts]
        # print "ts: "+str(ts)
        # print "demand: " + str(demand)
        # print "timepoints: " + str([t for t in timepoints])
        for i, d in enumerate(demand):
            # print "i+1: "+str(i+1)
            # print "d: "+str(d)
            # print "timepoints[i+1]: "+str(timepoints[i+1])
            # note: demand is a python list or array, which uses 0-based indexing, but
            # timepoints is a pyomo set, which uses 1-based indexing, so we have to shift the index by 1.
            m.dr_bid[b, z, timepoints[i+1]] = d
            m.dr_price[b, z, timepoints[i+1]] = prices[i]

    print "len(m.DR_BID_LIST): {l}".format(l=len(m.DR_BID_LIST))
    print "m.DR_BID_LIST: {b}".format(b=[x for x in m.DR_BID_LIST])

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
    # TODO: now that this happens just before a solve, there may be no need to 
    # preserve duals across the reconstruct().
    if m.iteration_number > 0:
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
        c for c in ('zone_demand_mw', 'ShiftDemand', 'ChargeEVs', 'FlexibleDemand') if hasattr(m, c)
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
        sum(m.DR_Welfare_Cost[t] * m.tp_weight_in_year[t] for t in m.TPS_IN_PERIOD[p])
        for p in m.PERIODS
    ])
    
    # payments by customers ([expected load] * [gice offered for that load])
    # TODO: this uses the price from just _before_ the final solution.
    # eventually this should be changed to reflect our expected pricing strategy 
    # (final constructed load * last offered price or final ex post price?)
    last_bid = m.DR_BID_LIST.last()
    if m.iteration_number == 0:
        values.extend([None for p in m.PERIODS])
    else:
        values.extend([
            sum(
                electricity_demand(m, z, tp) * m.dr_price[last_bid, z, tp] * m.tp_weight_in_year[tp]
                for z in m.LOAD_ZONES for tp in m.TPS_IN_PERIOD[p]
            )
            for p in m.PERIODS
        ])
    
    # total MWh delivered each year
    values.extend([
        sum(
            electricity_demand(m, z, tp) * m.tp_weight_in_year[tp]
            for z in m.LOAD_ZONES for tp in m.TPS_IN_PERIOD[p]
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
            +tuple(m.Zone_Power_Injections)
            +tuple(m.Zone_Power_Withdrawals)
            +("marginal_cost","final_marginal_cost","price","bid_load","peak_day","base_load","base_price"),
        values=lambda m, z, t: 
            (z, m.tp_period[t], m.tp_timestamp[t]) 
            +tuple(
                sum(get(m.DispatchGenByFuel, (p, t, f), 0.0) for p in m.GENERATION_PROJECTS_BY_FUEL[f])
                for f in m.FUELS
            )
            +tuple(
                sum(get(m.DispatchGen, (p, t), 0.0) for p in m.GENERATION_PROJECTS_BY_NON_FUEL_ENERGY_SOURCE[s])
                for s in m.NON_FUEL_ENERGY_SOURCES
            )
            +tuple(
                sum(
                    get(m.DispatchUpperLimit, (p, t), 0.0) - get(m.DispatchGen, (p, t), 0.0) 
                    for p in m.GENERATION_PROJECTS_BY_NON_FUEL_ENERGY_SOURCE[s]
                )
                for s in m.NON_FUEL_ENERGY_SOURCES
            )
            +tuple(getattr(m, component)[z, t] for component in m.Zone_Power_Injections)
            +tuple(getattr(m, component)[z, t] for component in m.Zone_Power_Withdrawals)
            +(
                m.prev_marginal_cost[z, t],
                electricity_marginal_cost(m, z, t),
                m.dr_price[last_bid, z, t],
                m.dr_bid[last_bid, z, t],
                'peak' if m.ts_scale_to_year[m.tp_ts[t]] < 0.5*avg_ts_scale else 'typical',
                m.base_data_dict[z, t][0],
                m.base_data_dict[z, t][1],
            )
    )
    
    # import pprint
    # b=[(g, pe, value(m.BuildGen[g, pe]), m.gen_tech[g], m.gen_overnight_cost[g, pe]) for (g, pe) in m.BuildGen if value(m.BuildGen[g, pe]) > 0]
    # bt=set(x[3] for x in b) # technologies
    # pprint([(t, sum(x[2] for x in b if x[3]==t), sum(x[4] for x in b if x[3]==t)/sum(1.0 for x in b if x[3]==t)) for t in bt])

def write_dual_costs(m):
    outputs_dir = m.options.outputs_dir
    tag = filename_tag(m)

    # with open(os.path.join(outputs_dir, "producer_surplus{t}.tsv".format(t=tag)), 'w') as f:
    #     for g, per in m.Max_Build_Potential:
    #         const = m.Max_Build_Potential[g, per]
    #         surplus = const.upper() * m.dual[const]
    #         if surplus != 0.0:
    #             f.write('\t'.join([const.cname(), str(surplus)]) + '\n')
    #     # import pdb; pdb.set_trace()
    #     for g, year in m.BuildGen:
    #         var = m.BuildGen[g, year]
    #         if var.ub is not None and var.ub > 0.0 and value(var) > 0.0 and var in m.rc and m.rc[var] != 0.0:
    #             surplus = var.ub * m.rc[var]
    #             f.write('\t'.join([var.cname(), str(surplus)]) + '\n')

    outfile = os.path.join(outputs_dir, "dual_costs{t}.tsv".format(t=tag))
    dual_data = []
    start_time = time.time()
    print "Writing {} ... ".format(outfile),
    
    def add_dual(const, lbound, ubound, duals):
        if const in duals:
            dual = duals[const]
            if dual >= 0.0:
                direction = ">="
                bound = lbound
            else:
                direction = "<="
                bound = ubound
            if bound is None:
                # Variable is unbounded; dual should be 0.0 or possibly a tiny non-zero value.
                if not (-1e-5 < dual < 1e-5):
                    raise ValueError("{} has no {} bound but has a non-zero dual value {}.".format(
                        const.cname(), "lower" if dual > 0 else "upper", dual))
            else:
                total_cost = dual * bound
                if total_cost != 0.0:
                    dual_data.append((const.cname(), direction, bound, dual, total_cost))

    for comp in m.component_objects(ctype=Var):
        for idx in comp:
            var = comp[idx]
            add_dual(var, var.lb, var.ub, m.rc)
    for comp in m.component_objects(ctype=Constraint):
        for idx in comp:
            constr = comp[idx]
            add_dual(constr, value(constr.lower), value(constr.upper), m.dual)

    dual_data.sort(key=lambda r: (not r[0].startswith('DR_Convex_'), r[3] >= 0)+r)

    with open(outfile, 'w') as f:
        f.write('\t'.join(['constraint', 'direction', 'bound', 'dual', 'total_cost']) + '\n')
        f.writelines('\t'.join(map(str, r)) + '\n' for r in dual_data)
    print "time taken: {dur:.2f}s".format(dur=time.time()-start_time)

def filename_tag(m):
    if m.options.scenario_name:
        t = m.options.scenario_name + "_"
    else:
        t = ""
    t = t + "_".join(map(str, m.iteration_node))
    if t:
        t = "_" + t
    return t

