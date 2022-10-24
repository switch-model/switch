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
from __future__ import print_function
from __future__ import division

# TODO: create a new module to handle total-cost pricing.
# That should apply a simple tax to every retail kWh sold (zone_demand_mw or FlexibleDemand)
# (this is a fixed adder to the cost in $/kWh, not a multiplier times the marginal cost)
# that module can be used as-is to find the effect of any particular adder
# or it can iterate at a level above the demand_response module
# and use something like scipy.optimize.newton() to find the right tax to come out
# revenue-neutral (i.e., recover any stranded costs, rebate any supply-side rents)

import os, sys, time
from pprint import pprint
from pyomo.environ import *

try:
    from pyomo.repn import generate_standard_repn
except ImportError:
    # this was called generate_canonical_repn before Pyomo 5.6
    from pyomo.repn import generate_canonical_repn as generate_standard_repn

import switch_model.utilities as utilities

# TODO: move part of the reporting back into Hawaii module and eliminate these dependencies
from switch_model.hawaii.save_results import DispatchGenByFuel
import switch_model.hawaii.util as util

demand_module = None  # will be set via command-line options


def define_arguments(argparser):
    argparser.add_argument(
        "--dr-flat-pricing",
        action="store_true",
        default=False,
        help="Charge a constant (average) price for electricity, rather than varying hour by hour",
    )
    argparser.add_argument(
        "--dr-demand-module",
        default=None,
        help="Name of module to use for demand-response bids. This should also be "
        "specified in the modules list, and should provide calibrate() and bid() functions. "
        "Pre-written options include constant_elasticity_demand_system or r_demand_system. "
        "Specify one of these in the modules list and use --help again to see module-specific options.",
    )
    argparser.add_argument(
        "--demand-response-reserve-types",
        nargs="+",
        default=[],
        help="Type(s) of reserves to provide from demand response (e.g., 'contingency' or 'regulation'). "
        "Specify 'none' to disable. Default is 'spinning' if an operating reserve module is used, "
        "otherwise it is 'none'.",
    )


def define_components(m):

    # load scipy.optimize; this is done here to avoid loading it during unit tests
    try:
        global scipy
        import scipy.optimize
    except ImportError:
        print("=" * 80)
        print(
            "Unable to load scipy package, which is used by the demand response system."
        )
        print("Please install this via 'conda install scipy' or 'pip install scipy'.")
        print("=" * 80)
        raise

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
            "Please add this module to the modules list (usually modules.txt) "
            "or specify --include-module {mod} in options.txt, scenarios.txt or "
            "on the command line.".format(mod=m.options.dr_demand_module)
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
    m.dr_unserved_load_penalty_per_mwh = Param(
        initialize=10000, within=NonNegativeReals
    )
    # amount of unserved load during each timepoint
    m.DRUnservedLoad = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    # total cost for unserved load
    m.DR_Unserved_Load_Penalty = Expression(
        m.TIMEPOINTS,
        rule=lambda m, tp: sum(
            m.DRUnservedLoad[z, tp] * m.dr_unserved_load_penalty_per_mwh
            for z in m.LOAD_ZONES
        ),
    )
    # add unserved load to the zonal energy balance
    m.Zone_Power_Injections.append("DRUnservedLoad")
    # add the unserved load penalty to the model's objective function
    m.Cost_Components_Per_TP.append("DR_Unserved_Load_Penalty")

    # list of products (commodities and reserves) that can be bought or sold
    m.DR_PRODUCTS = Set(dimen=1, initialize=["energy", "energy up", "energy down"])

    ###################
    # Price Responsive Demand bids
    ##################

    # list of all bids that have been received from the demand system
    m.DR_BID_LIST = Set(dimen=1, initialize=[], ordered=True)
    # we need an explicit indexing set for everything that depends on DR_BID_LIST
    # so we can reconstruct it (and them) each time we add an element to DR_BID_LIST
    # (not needed, and actually doesn't work -- reconstruct() fails for sets)
    # m.DR_BIDS_LZ_TP = Set(initialize = lambda m: m.DR_BID_LIST * m.LOAD_ZONES * m.TIMEPOINTS)
    # m.DR_BIDS_LZ_TS = Set(initialize = lambda m: m.DR_BID_LIST * m.LOAD_ZONES * m.TIMESERIES)

    # data for the individual bids; each load_zone gets one bid for each timeseries,
    # and each bid covers all the timepoints in that timeseries. So we just record
    # the bid for each timepoint for each load_zone.
    m.dr_bid = Param(
        m.DR_BID_LIST,
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        m.DR_PRODUCTS,
        mutable=True,
        within=NonNegativeReals,
    )

    # price used to get this bid (only kept for reference)
    m.dr_price = Param(
        m.DR_BID_LIST,
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        m.DR_PRODUCTS,
        mutable=True,
        within=NonNegativeReals,
    )

    # the private benefit of serving each bid
    m.dr_bid_benefit = Param(
        m.DR_BID_LIST, m.LOAD_ZONES, m.TIMESERIES, mutable=True, within=NonNegativeReals
    )

    # weights to assign to the bids for each timeseries when constructing an optimal demand profile
    m.DRBidWeight = Var(
        m.DR_BID_LIST, m.LOAD_ZONES, m.TIMESERIES, within=NonNegativeReals
    )

    # def DR_Convex_Bid_Weight_rule(m, z, ts):
    #     if len(m.DR_BID_LIST) == 0:
    #         print "no items in m.DR_BID_LIST, skipping DR_Convex_Bid_Weight constraint"
    #         return Constraint.Skip
    #     else:
    #         print "constructing DR_Convex_Bid_Weight constraint"
    #         return (sum(m.DRBidWeight[b, z, ts] for b in m.DR_BID_LIST) == 1)
    #
    # choose a convex combination of bids for each zone and timeseries
    m.DR_Convex_Bid_Weight = Constraint(
        m.LOAD_ZONES,
        m.TIMESERIES,
        rule=lambda m, z, ts: Constraint.Skip
        if len(m.DR_BID_LIST) == 0
        else (sum(m.DRBidWeight[b, z, ts] for b in m.DR_BID_LIST) == 1),
    )

    # Since we don't have differentiated prices for each zone, we have to use the same
    # weights for all zones. (Otherwise the model will try to micromanage load in each
    # zone, but that won't be reflected in the prices we report.)
    # Note: LOAD_ZONES is not an ordered set, so we have to use a trick to get a single
    # arbitrary one to refer to (list(m.LOAD_ZONES)[0] would also work).
    m.DR_Load_Zone_Shared_Bid_Weight = Constraint(
        m.DR_BID_LIST,
        m.LOAD_ZONES,
        m.TIMESERIES,
        rule=lambda m, b, z, ts: m.DRBidWeight[b, z, ts]
        == m.DRBidWeight[b, next(iter(m.LOAD_ZONES)), ts],
    )

    # For flat-price models, we have to use the same weight for all timeseries within the
    # same year (period), because there is only one price for the whole period, so it can't
    # induce different adjustments in individual timeseries.
    if m.options.dr_flat_pricing:
        m.DR_Flat_Bid_Weight = Constraint(
            m.DR_BID_LIST,
            m.LOAD_ZONES,
            m.TIMESERIES,
            rule=lambda m, b, z, ts: m.DRBidWeight[b, z, ts]
            == m.DRBidWeight[b, z, m.tp_ts[m.TPS_IN_PERIOD[m.ts_period[ts]].first()]],
        )

    # Optimal level of demand, calculated from available bids (negative, indicating consumption)
    m.FlexibleDemand = Expression(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, tp: sum(
            m.DRBidWeight[b, z, m.tp_ts[tp]] * m.dr_bid[b, z, tp, "energy"]
            for b in m.DR_BID_LIST
        ),
    )

    # calculate available slack from demand response for use as reserves (from
    # supply perspective, so "up" means less load), then register spinning
    # reserves
    m.DemandUpReserveSales = Expression(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, tp: -sum(
            m.DRBidWeight[b, z, m.tp_ts[tp]] * m.dr_bid[b, z, tp, "energy up"]
            for b in m.DR_BID_LIST
        ),
    )
    m.DemandDownReserveSales = Expression(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, tp: -sum(
            m.DRBidWeight[b, z, m.tp_ts[tp]] * m.dr_bid[b, z, tp, "energy down"]
            for b in m.DR_BID_LIST
        ),
    )
    if hasattr(m, "ZONES_IN_BALANCING_AREA"):
        m.DemandResponseSlackUp = Expression(
            m.BALANCING_AREA_TIMEPOINTS,
            rule=lambda m, ba, tp: sum(
                m.DemandUpReserveSales[z, tp] for z in m.ZONES_IN_BALANCING_AREA[ba]
            ),
        )
        m.DemandResponseSlackDown = Expression(
            m.BALANCING_AREA_TIMEPOINTS,
            rule=lambda m, ba, tp: sum(
                m.DemandDownReserveSales[z, tp] for z in m.ZONES_IN_BALANCING_AREA[ba]
            ),
        )
    register_demand_response_reserves(m)

    # replace zone_demand_mw with FlexibleDemand in the energy balance constraint
    # note: the first two lines are simpler than the method I use, but my approach
    # preserves the ordering of the list, which is nice for older spreadsheets that expect
    # a certain ordering.
    # m.Zone_Power_Withdrawals.remove('zone_demand_mw')
    # m.Zone_Power_Withdrawals.append('FlexibleDemand')
    idx = m.Zone_Power_Withdrawals.index("zone_demand_mw")
    m.Zone_Power_Withdrawals[idx] = "FlexibleDemand"

    # private benefit of the electricity consumption
    # (i.e., willingness to pay for the current electricity supply)
    # reported as negative cost, i.e., positive benefit
    # also divide by number of timepoints in the timeseries
    # to convert from a cost per timeseries to a cost per timepoint.
    m.DR_Welfare_Cost = Expression(
        m.TIMEPOINTS,
        rule=lambda m, tp: (-1.0)
        * sum(
            m.DRBidWeight[b, z, m.tp_ts[tp]] * m.dr_bid_benefit[b, z, m.tp_ts[tp]]
            for b in m.DR_BID_LIST
            for z in m.LOAD_ZONES
        )
        * m.tp_duration_hrs[tp]
        / m.ts_num_tps[m.tp_ts[tp]],
    )

    # add the private benefit to the model's objective function
    m.Cost_Components_Per_TP.append("DR_Welfare_Cost")

    # variable to store the baseline data
    m.base_data = None

    # # TODO: create a data file that lists which timepoints are grouped into each flat
    # # pricing block; also enforce a requirement that no block can span periods.
    # # Then use that to choose flat prices for each block in each period when flat pricing
    # # is turned on (or maybe only when TOU block pricing is turned on).
    # # Price must be flat within each block, and total revenue across all blocks in each
    # # period must equal total marginal cost for those loads.
    #
    # # Hours during each day that fall into each flat-pricing block (zero-based).
    # # Note: this does not allow for blocks shorter than one hour, and if timepoints
    # # are longer than one hour, they will be placed in the first matching hour.
    # m.FLAT_PRICING_BLOCKS = Set()
    # raise NotImplementedError("The line above just contained `Set(` until 6/27/18; something is missing here.")
    #
    # # Times during each day to switch from one flat-pricing block to another; should be a float
    # # between 0 (midnight) and 24 (following midnight). Timepoints will be assigned to
    # # the immediately preceding block. Default is 0 (single block all day).
    # # This assumes that timepoints begin at midnight each day and are sequenced
    # # from there.
    # m.FLAT_PRICING_BREAK_TIMES = Set(default=[0])
    # m.FLAT_PRICING_GROUPS = Set(initialize=m.PERIODS * m.FLAT_PRICING_START_TIMES)
    # def rule(m, p, st):
    #     try:
    #         d = m.TPS_FOR_FLAT_PRICING_GROUP_dict
    #     except AttributeError:
    #         d = m.TPS_FOR_FLAT_PRICING_GROUP_dict = dict()
    #         # construct a dictionary of which timepoints fall in each block
    #         # tuples show starting time and
    #         sorted(range(len(seq)), key=seq.__getitem__)
    #         start_times = sorted(m.FLAT_PRICING_START_TIMES)
    #         cur_start = xxx
    #         raise NotImplementedError("The line above just contained `cur_start =` until 6/27/18; something is missing here.")
    #
    #         start_time_tuples = [(s, 0) for s in m.FLAT_PRICING_START_TIMES]
    #         for ts in m.TIMESERIES:
    #             timepoint_tuples = [(i * m.ts_duration_of_tp[ts], tp) for i, tp in enumerate(m.TPS_IN_TS[ts])]
    #
    #     return d.pop(p, st)
    #
    # m.TPS_FOR_FLAT_PRICING_GROUP = Set(m.FLAT_PRICING_GROUPS, initialize=rule)
    #
    # m.tp_flat_pricing_block = Param(m.TIMEPOINTS, within=m.FLAT_PRICING_START_TIMES, initialize=rule)

    # provide up and down reserves (from supply perspective, so "up" means less load)
    # note: the bids are negative quantities, indicating _production_ of reserves;
    # they contribute to the reserve requirement with opposite sign


def pre_iterate(m):
    # could all prev values be stored in post_iterate?
    # then this func would just alter the model based on values calculated in post_iterate
    # (e.g., get a bid based on current prices, add bid to model, rebuild components)

    # NOTE:
    # bids must be added to the model here, and the model must be reconstructed here,
    # so the model can then be solved and remain in a "solved" state through the end
    # of post-iterate, to avoid problems in final reporting.

    # store various properties from previous model solution for later reference
    if m.iteration_number == 0:
        # model hasn't been solved yet
        m.prev_marginal_cost = {
            (z, tp, prod): None
            for z in m.LOAD_ZONES
            for tp in m.TIMEPOINTS
            for prod in m.DR_PRODUCTS
        }
        m.prev_demand = {
            (z, tp, prod): None
            for z in m.LOAD_ZONES
            for tp in m.TIMEPOINTS
            for prod in m.DR_PRODUCTS
        }
        m.prev_SystemCost = None
    else:
        # get values from previous solution
        m.prev_marginal_cost = {
            (z, tp, prod): electricity_marginal_cost(m, z, tp, prod)
            for z in m.LOAD_ZONES
            for tp in m.TIMEPOINTS
            for prod in m.DR_PRODUCTS
        }
        m.prev_demand = {
            (z, tp, prod): electricity_demand(m, z, tp, prod)
            for z in m.LOAD_ZONES
            for tp in m.TIMEPOINTS
            for prod in m.DR_PRODUCTS
        }
        m.prev_SystemCost = value(m.SystemCost)

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
        prev_direct_cost = value(
            sum(
                (
                    sum(
                        m.prev_marginal_cost[z, tp, prod] * m.prev_demand[z, tp, prod]
                        for z in m.LOAD_ZONES
                        for prod in m.DR_PRODUCTS
                    )
                )
                * m.bring_timepoint_costs_to_base_year[tp]
                for ts in m.TIMESERIES
                for tp in m.TPS_IN_TS[ts]
            )
        )
        prev_welfare_cost = value(
            sum(
                (m.DR_Welfare_Cost[tp]) * m.bring_timepoint_costs_to_base_year[tp]
                for ts in m.TIMESERIES
                for tp in m.TPS_IN_TS[ts]
            )
        )
        prev_cost = prev_direct_cost + prev_welfare_cost

        # prev_cost = value(sum(
        #     (
        #         sum(
        #             m.prev_marginal_cost[lz, tp, prod] * m.prev_demand[lz, tp, prod]
        #             for lz in m.LOAD_ZONES for prod in m.DR_PRODUCTS
        #         ) + m.DR_Welfare_Cost[tp]
        #     ) * m.bring_timepoint_costs_to_base_year[tp]
        #     for ts in m.TIMESERIES
        #     for tp in m.TPS_IN_TS[ts]
        # ))

        print("")
        print("previous direct cost: ${:,.0f}".format(prev_direct_cost))
        print("previous welfare cost: ${:,.0f}".format(prev_welfare_cost))
        print("")

    # get the next bid and attach it to the model
    update_demand(m)

    if m.iteration_number > 0:
        # get an estimate of best possible net cost of serving load
        # (if we could completely serve the last bid at the prices we quoted,
        # that would be an optimum; the actual cost may be higher but never lower)
        b = m.DR_BID_LIST.last()  # current bid number
        best_direct_cost = value(
            sum(
                sum(
                    m.prev_marginal_cost[z, tp, prod] * m.dr_bid[b, z, tp, prod]
                    for z in m.LOAD_ZONES
                    for prod in m.DR_PRODUCTS
                )
                * m.bring_timepoint_costs_to_base_year[tp]
                for ts in m.TIMESERIES
                for tp in m.TPS_IN_TS[ts]
            )
        )
        best_bid_benefit = value(
            sum(
                (
                    -sum(m.dr_bid_benefit[b, z, ts] for z in m.LOAD_ZONES)
                    * m.tp_duration_hrs[tp]
                    / m.ts_num_tps[ts]
                )
                * m.bring_timepoint_costs_to_base_year[tp]
                for ts in m.TIMESERIES
                for tp in m.TPS_IN_TS[ts]
            )
        )
        best_cost = best_direct_cost + best_bid_benefit

        # best_cost = value(sum(
        #     (
        #         sum(
        #             m.prev_marginal_cost[z, tp, prod] * m.dr_bid[b, z, tp, prod]
        #             for z in m.LOAD_ZONES for prod in m.DR_PRODUCTS
        #         )
        #         - sum(m.dr_bid_benefit[b, z, ts] for z in m.LOAD_ZONES)
        #         * m.tp_duration_hrs[tp] / m.ts_num_tps[ts]
        #     ) * m.bring_timepoint_costs_to_base_year[tp]
        #     for ts in m.TIMESERIES
        #     for tp in m.TPS_IN_TS[ts]
        # ))

        print("")
        print("best direct cost: ${:,.0f}".format(best_direct_cost))
        print("best bid benefit: ${:,.0f}".format(best_bid_benefit))
        print("")

        print(
            "lower bound=${:,.0f}, previous cost=${:,.0f}, optimality gap (vs direct cost)={}".format(
                best_cost, prev_cost, (prev_cost - best_cost) / abs(prev_direct_cost)
            )
        )
        if prev_cost < best_cost:
            print(
                "WARNING: final cost is below reported lower bound; "
                "there is probably a problem with the demand system."
            )

        # import pdb; pdb.set_trace()

    # basis for optimality test:
    # 1. The total cost of supply, as a function of quantity produced each hour, forms
    # a surface which is convex downward, since it is linear (assuming all variables are
    # continuous or all integer variables are kept at their current level, i.e., the curve
    # is locally convex). (Think of the convex hull of the extreme points of the production
    # cost function.)
    # 2. The total benefit of consumption, as a function of quantity consumed each hour,
    # forms a surface which is concave downward (by the assumption/requirement of convexity
    # of the demand function).
    # 3. marginal costs (prev_marginal_cost) and production levels (pref_demand) from the
    # most recent solution to the master problem define a production cost plane which is
    # tangent to the production cost function at that production level. From 1, the production
    # cost function must lie on or above this surface everywhere. This plane is given by
    # (something + prev_marginal_cost * (demand - dr_bid))
    # 4. The last bid quantities (dr_bid) must be at a point where marginal benefit of consumption
    # equals marginal cost of consumption (prev_marginal_cost) in all directions; otherwise
    # they would not be a private optimum.
    # 5. The benefit reported in the last bid (dr_bid_benefit) shows the level of the total
    # benefit curve at that point.
    # 6. From 2, 4 and 5, the prev_marginal_cost and the last reported benefit must form
    # a plane which is at or above the total benefit curve everywhere. This plane is given by
    # (-DR_Welfare_Cost - (prev_marginal_cost * (demand - prev_demand) + something))
    # 7. Since the total cost curve must lie above the plane defined in 3. and the total
    # benefit curve must lie below the plane defined in 6., the (constant) distance between
    # these planes is an upper bound on the net benefit that can be obtained. This is given by
    # (-DR_Welfare_Cost - prev_marginal_cost * (demand - prev_demand))
    # - (prev_marginal_cost * (demand - dr_bid))
    # = ...

    # (prev_marginal_cost * (demand - dr_bid))
    # - (prev_marginal_cost * (demand - prev_demand) )
    # -
    # = prev_marginal_cost * prev_demand + DR_Welfare_Cost
    #   - (prev_marginal_cost * dr_bid - dr_bid_benefit)

    # Check for convergence -- optimality gap is less than 0.1% of best possible cost
    # (which may be negative)
    # TODO: index this to the direct costs, rather than the direct costs minus benefits
    # as it stands, it converges with about $50,000,000 optimality gap, which is about
    # 3% of direct costs.
    converged = (
        m.iteration_number > 0
        and (prev_cost - best_cost) / abs(prev_direct_cost) <= 0.0001
    )

    return converged


def post_iterate(m):
    print("\n\n=======================================================")
    print("Solved model")
    print("=======================================================")
    print("Total cost: ${v:,.0f}".format(v=value(m.SystemCost)))

    # TODO:
    # maybe calculate prices for the next round here and attach them to the
    # model, so they can be reported as final prices (currently we don't
    # report the final prices, only the prices prior to the final model run)

    SystemCost = value(m.SystemCost)  # calculate once to save time
    if m.prev_SystemCost is None:
        print(
            "prev_SystemCost=<n/a>, SystemCost={:,.0f}, ratio=<n/a>".format(SystemCost)
        )
    else:
        print(
            "prev_SystemCost={:,.0f}, SystemCost={:,.0f}, ratio={}".format(
                m.prev_SystemCost, SystemCost, SystemCost / m.prev_SystemCost
            )
        )

    tag = m.options.scenario_name
    outputs_dir = m.options.outputs_dir

    # report information on most recent bid
    if m.iteration_number == 0:
        util.create_table(
            output_file=os.path.join(outputs_dir, "bid_{t}.csv".format(t=tag)),
            headings=("bid_num", "load_zone", "timeseries", "timepoint")
            + tuple("marginal_cost " + prod for prod in m.DR_PRODUCTS)
            + tuple("price " + prod for prod in m.DR_PRODUCTS)
            + tuple("bid " + prod for prod in m.DR_PRODUCTS)
            + ("wtp", "base_price", "base_load"),
        )
    b = m.DR_BID_LIST.last()  # current bid
    util.append_table(
        m,
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        output_file=os.path.join(outputs_dir, "bid_{t}.csv".format(t=tag)),
        values=lambda m, z, tp: (b, z, m.tp_ts[tp], m.tp_timestamp[tp])
        + tuple(m.prev_marginal_cost[z, tp, prod] for prod in m.DR_PRODUCTS)
        + tuple(m.dr_price[b, z, tp, prod] for prod in m.DR_PRODUCTS)
        + tuple(m.dr_bid[b, z, tp, prod] for prod in m.DR_PRODUCTS)
        + (
            m.dr_bid_benefit[b, z, m.tp_ts[tp]],
            m.base_data_dict[z, tp][1],
            m.base_data_dict[z, tp][0],
        ),
    )

    # store the current bid weights for future reference
    if m.iteration_number == 0:
        util.create_table(
            output_file=os.path.join(outputs_dir, "bid_weights_{t}.csv".format(t=tag)),
            headings=("iteration", "load_zone", "timeseries", "bid_num", "weight"),
        )
    util.append_table(
        m,
        m.LOAD_ZONES,
        m.TIMESERIES,
        m.DR_BID_LIST,
        output_file=os.path.join(outputs_dir, "bid_weights_{t}.csv".format(t=tag)),
        values=lambda m, z, ts, b: (
            len(m.DR_BID_LIST),
            z,
            ts,
            b,
            m.DRBidWeight[b, z, ts],
        ),
    )

    # if m.iteration_number % 5 == 0:
    #     # save time by only writing results every 5 iterations
    # write_results(m)

    # Stop if there are no duals. This is an efficient point to check, and
    # otherwise the errors later are pretty cryptic.
    if not m.dual:
        raise RuntimeError(
            "No dual values have been calculated. Check that your solver is "
            "able to provide duals for integer programs. If using cplex, you "
            "may need to specify --retrieve-cplex-mip-duals."
        )

    write_dual_costs(m)
    write_results(m)
    write_batch_results(m)

    # if m.iteration_number >= 3:
    #     import pdb; pdb.set_trace()


def update_demand(m):
    """
    This should be called after solving the model, in order to calculate new bids
    to include in future runs. The first time through, it also uses the fixed demand
    and marginal costs to calibrate the demand system, and then replaces the fixed
    demand with the flexible demand system.
    """
    first_run = m.base_data is None

    print("attaching new demand bid to model")
    if first_run:
        calibrate_model(m)
    else:  # not first run
        if m.options.verbose:
            print("m.DRBidWeight:")
            pprint(
                [
                    (
                        z,
                        ts,
                        [(b, value(m.DRBidWeight[b, z, ts])) for b in m.DR_BID_LIST],
                    )
                    for z in m.LOAD_ZONES
                    for ts in m.TIMESERIES
                ]
            )

    # get new bids from the demand system at the current prices
    bids = get_bids(m)

    # add the new bids to the model
    if m.options.verbose:
        print("adding bids to model")
        # print "first day (z, ts, prices, demand, wtp) ="
        # pprint(bids[0])
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
    """Return undiscounted total cost per year, during each period, as calculated by Switch,
    including everything except DR_Welfare_Cost.

    This code comes from financials.calc_sys_costs_per_period(), excluding discounting
    and upscaling to the period.

    NOTE: ideally this would give costs by zone and period, to allow calibration for different
    utilities within a large study. But the cost components don't distinguish that way.
    (They probably should, since that would allow us to discuss average electricity costs
    in each zone.)
    """
    return value(
        sum(
            getattr(m, annual_cost)[period]
            for annual_cost in m.Cost_Components_Per_Period
        )
        + sum(
            getattr(m, tp_cost)[t] * m.tp_weight_in_year[t]
            for t in m.TPS_IN_PERIOD[period]
            for tp_cost in m.Cost_Components_Per_TP
            if tp_cost != "DR_Welfare_Cost"
        )
    )


def electricity_marginal_cost(m, z, tp, prod):
    """Return marginal cost of providing product prod in load_zone z during timepoint tp."""
    if hasattr(m, "zone_balancing_area"):
        ba = m.zone_balancing_area[z]
    if prod == "energy":
        component = m.Zone_Energy_Balance[z, tp]
    elif prod == "energy up":
        if hasattr(m, "Limit_DemandResponseSpinningReserveUp"):
            component = m.Limit_DemandResponseSpinningReserveUp[ba, tp]
        else:
            component = m.Satisfy_Spinning_Reserve_Up_Requirement[ba, tp]
    elif prod == "energy down":
        if hasattr(m, "Limit_DemandResponseSpinningReserveUp"):
            component = m.Limit_DemandResponseSpinningReserveDown[ba, tp]
        else:
            component = m.Satisfy_Spinning_Reserve_Down_Requirement[ba, tp]
    else:
        raise ValueError("Unrecognized electricity product: {}.".format(prod))
    return m.dual[component] / m.bring_timepoint_costs_to_base_year[tp]


def electricity_demand(m, z, tp, prod):
    """Return total consumption of product prod in load_zone z during timepoint tp (negative if customers supply product)."""
    if prod == "energy":
        if len(m.DR_BID_LIST) == 0:
            # use zone_demand_mw (base demand) if no bids have been received yet
            # (needed to find flat prices before solving the model the first time)
            demand = m.zone_demand_mw[z, tp]
        else:
            demand = m.FlexibleDemand[z, tp]
    elif prod == "energy up":
        # note: reserves have positive sign when provided by demand side,
        # but that should be shown as negative demand
        demand = -value(m.DemandUpReserveSales[z, tp])
    elif prod == "energy down":
        demand = -value(m.DemandDownReserveSales[z, tp])
    else:
        raise ValueError("Unrecognized electricity product: {}.".format(prod))
    return demand


def calibrate_model(m):
    """
    Calibrate the demand system and add it to the model.
    """

    # base_data consists of a list of tuples showing (load_zone, timeseries, base_load (list) and base_price)
    # note: the constructor below assumes list comprehensions will preserve the order of the underlying list
    # (which is guaranteed according to http://stackoverflow.com/questions/1286167/is-the-order-of-results-coming-from-a-list-comprehension-guaranteed)

    # calculate the average-cost price for the current study period
    # TODO: store monthly retail prices in system_load, and find annual average prices
    # that correspond to the load forecasts for each period, then store scale factors
    # in system_load_scale to convert 2007-08 monthly prices into monthly prices for other
    # years (same technique as rescaling the loads, but only adjusting the mean), then
    # report base prices for each timepoint along with the loads in loads.csv.
    # For now, we just assume the base price was $180/MWh, which is HECO's average price in
    # 2007 according to EIA form 826.
    # TODO: add in something for the fixed costs, to make marginal cost commensurate with the base_price
    # baseCosts = [m.dual[m.EnergyBalance[z, tp]] for z in m.LOAD_ZONES for tp in m.TIMEPOINTS]
    base_price = 180  # average retail price for 2007 ($/MWh)
    m.base_data = [
        (
            z,
            ts,
            [m.zone_demand_mw[z, tp] for tp in m.TPS_IN_TS[ts]],
            [base_price] * len(m.TPS_IN_TS[ts]),
        )
        for z in m.LOAD_ZONES
        for ts in m.TIMESERIES
    ]

    # make a dict of base_data, indexed by load_zone and timepoint, for later reference
    m.base_data_dict = {
        (z, tp): (m.zone_demand_mw[z, tp], base_price)
        for z in m.LOAD_ZONES
        for tp in m.TIMEPOINTS
    }

    # calibrate the demand module
    demand_module.calibrate(m, m.base_data)


def get_prices(m, flat_revenue_neutral=True):
    """Calculate appropriate prices for each day, based on the current state
    of the model."""

    # construct dictionaries of marginal cost vectors for each product for each load zone and time series
    if m.iteration_number == 0:
        # use base prices on the first pass ($0 for everything other than energy)
        marginal_costs = {
            (z, ts): {
                prod: (
                    [m.base_data_dict[z, tp][1] for tp in m.TPS_IN_TS[ts]]
                    if prod == "energy"
                    else [0.0] * len(m.TPS_IN_TS[ts])
                )
                for prod in m.DR_PRODUCTS
            }
            for z in m.LOAD_ZONES
            for ts in m.TIMESERIES
        }
    else:
        # use marginal costs from last solution
        marginal_costs = {
            (z, ts): {
                prod: [
                    electricity_marginal_cost(m, z, tp, prod) for tp in m.TPS_IN_TS[ts]
                ]
                for prod in m.DR_PRODUCTS
            }
            for z in m.LOAD_ZONES
            for ts in m.TIMESERIES
        }

    if m.options.dr_flat_pricing:
        # find flat price for the whole period that is revenue neutral with the marginal costs
        # (e.g., an aggregator could buy at dynamic marginal cost and sell to the customer at
        # a flat price; the aggregator must find the correct flat price so they break even)
        prices = find_flat_prices(m, marginal_costs, flat_revenue_neutral)
    else:
        prices = marginal_costs

    return prices


def get_bids(m):
    """Get bids from the demand system showing quantities at the current prices and willingness-to-pay for those quantities
    call bid() with dictionary of prices for different products

    Each bid is a tuple of (load_zone, timeseries, {prod: [hourly prices]}, {prod: [hourly quantities]}, wtp)
    quantity will be positive for consumption, negative if customer will supply product
    """

    prices = get_prices(m)

    # get bids for all load zones and timeseries
    bids = []
    for z in m.LOAD_ZONES:
        for ts in m.TIMESERIES:
            demand, wtp = demand_module.bid(m, z, ts, prices[z, ts])
            # import pdb; pdb.set_trace()
            if m.options.dr_flat_pricing:
                # assume demand side will not provide reserves, even if they offered some
                # (at zero price)
                for (k, v) in demand.items():
                    if k != "energy":
                        for i in range(len(v)):
                            v[i] = 0.0
            bids.append((z, ts, prices[z, ts], demand, wtp))

    return bids


# def zone_period_average_marginal_cost(m, load_zone, period):
#     avg_cost = value(
#         sum(
#             electricity_marginal_cost(m, load_zone, tp, 'energy')
#             * electricity_demand(m, load_zone, tp, 'energy')
#             * m.tp_weight_in_year[tp]
#             for tp in m.PERIOD_TPS[period]
#         )
#         /
#         sum(
#             electricity_demand(m, load_zone, tp, 'energy')
#             * m.tp_weight_in_year[tp]
#             for tp in m.PERIOD_TPS[period]
#         )
#     )
#     return avg_cost


def find_flat_prices(m, marginal_costs, revenue_neutral):
    # calculate flat prices for an imaginary load-serving entity (LSE) who
    # must break even in each load zone and period.
    # LSE buys at marginal cost, sells at flat prices
    # this is like a transformation on the demand function, where we are
    # now  selling to the LSE rather than directly to the customers
    #
    # LSE iterates in sub-loop (scipy.optimize.newton) to find flat price:
    # set price (e.g., simple average of MC or avg weighted by expected demand)
    # offer price to demand side
    # receive bids
    # calc revenue balance for LSE (q*price - q.MC)
    # if > 0: decrease price (q will go up across the board)
    # if < 0: increase price (q will go down across the board) but

    flat_prices = dict()
    for z in m.LOAD_ZONES:
        for p in m.PERIODS:
            price_guess = value(
                sum(
                    marginal_costs[z, ts]["energy"][i]
                    * electricity_demand(m, z, tp, "energy")
                    * m.tp_weight_in_year[tp]
                    for ts in m.TS_IN_PERIOD[p]
                    for i, tp in enumerate(m.TPS_IN_TS[ts])
                )
                / sum(
                    electricity_demand(m, z, tp, "energy") * m.tp_weight_in_year[tp]
                    for tp in m.TPS_IN_PERIOD[p]
                )
            )

            if revenue_neutral:
                # find a flat price that produces revenue equal to marginal costs
                flat_prices[z, p] = scipy.optimize.newton(
                    revenue_imbalance, price_guess, args=(m, z, p, marginal_costs)
                )
            else:
                # used in final round, when LSE is considered to have
                # bought the final constructed quantity at the final
                # marginal cost
                flat_prices[z, p] = price_guess

    # construct a collection of flat prices with the right structure
    final_prices = {
        (z, ts): {
            prod: [flat_prices[z, p] if prod == "energy" else 0.0]
            * len(m.TPS_IN_TS[ts])
            for prod in m.DR_PRODUCTS
        }
        for z in m.LOAD_ZONES
        for p in m.PERIODS
        for ts in m.TS_IN_PERIOD[p]
    }
    return final_prices


def revenue_imbalance(flat_price, m, load_zone, period, dynamic_prices):
    """find demand and revenue that would occur in this load_zone and period with flat prices, and
    compare to the cost of meeting that demand by purchasing power at the current dynamic prices"""
    flat_price_revenue = 0.0
    dynamic_price_revenue = 0.0
    for ts in m.TS_IN_PERIOD[period]:
        prices = {
            prod: [flat_price if prod == "energy" else 0.0] * len(m.TPS_IN_TS[ts])
            for prod in m.DR_PRODUCTS
        }
        demand, wtp = demand_module.bid(m, load_zone, ts, prices)
        # flat_price_revenue += sum(
        #     p * d * m.ts_duration_of_tp[ts] * m.ts_scale_to_year[ts]
        #     for p, d in zip(prices['energy'], demand['energy']
        # )
        flat_price_revenue += flat_price * sum(
            d * m.ts_duration_of_tp[ts] * m.ts_scale_to_year[ts]
            for d in demand["energy"]
        )
        dynamic_price_revenue += sum(
            p * d * m.ts_duration_of_tp[ts] * m.ts_scale_to_year[ts]
            for p, d in zip(dynamic_prices[load_zone, ts]["energy"], demand["energy"])
        )
    imbalance = dynamic_price_revenue - flat_price_revenue

    print(
        "{}, {}: price ${} produces revenue imbalance of ${}/year".format(
            load_zone, period, flat_price, imbalance
        )
    )

    return imbalance


def add_bids(m, bids):
    """
    accept a list of bids written as tuples like
    (z, ts, prod, prices, demand, wtp)
    where z is the load zone, ts is the timeseries, prod is the product,
    demand is a list of demand levels for the timepoints during that series (possibly negative, to sell),
    and wtp is the net private benefit from consuming/selling the amount of power in that bid.
    Then add that set of bids to the model
    """
    # create a bid ID and add it to the list of bids
    if len(m.DR_BID_LIST) == 0:
        b = 1
    else:
        b = max(m.DR_BID_LIST) + 1

    m.DR_BID_LIST.add(b)

    # add the bids for each load zone and timepoint to the dr_bid list
    for (z, ts, prices, demand, wtp) in bids:
        # record the private benefit
        m.dr_bid_benefit[b, z, ts] = wtp
        # record the level of demand for each timepoint
        for prod in m.DR_PRODUCTS:
            for i, tp in enumerate(m.TPS_IN_TS[ts]):
                m.dr_bid[b, z, tp, prod] = demand[prod][i]
                m.dr_price[b, z, tp, prod] = prices[prod][i]

    print("len(m.DR_BID_LIST): {l}".format(l=len(m.DR_BID_LIST)))
    print("m.DR_BID_LIST: {b}".format(b=[x for x in m.DR_BID_LIST]))

    # reconstruct the components that depend on m.DR_BID_LIST, m.dr_bid_benefit and m.dr_bid
    m.DRBidWeight.reconstruct()
    m.DR_Convex_Bid_Weight.reconstruct()
    m.DR_Load_Zone_Shared_Bid_Weight.reconstruct()
    if hasattr(m, "DR_Flat_Bid_Weight"):
        m.DR_Flat_Bid_Weight.reconstruct()
    m.FlexibleDemand.reconstruct()
    m.DemandUpReserveSales.reconstruct()
    m.DemandDownReserveSales.reconstruct()
    if hasattr(m, "DemandResponseSlackUp"):
        m.DemandResponseSlackUp.reconstruct()
        m.DemandResponseSlackDown.reconstruct()
    if hasattr(m, "Limit_DemandResponseSpinningReserveUp"):
        m.Limit_DemandResponseSpinningReserveUp.reconstruct()
        m.Limit_DemandResponseSpinningReserveDown.reconstruct()

    m.DR_Welfare_Cost.reconstruct()
    # it seems like we have to reconstruct the higher-level components that depend on these
    # ones (even though these are Expressions), because otherwise they refer to objects that
    # used to be returned by the Expression but aren't any more (e.g., versions of DRBidWeight
    # that no longer exist in the model).
    # (i.e., Energy_Balance refers to the items returned by FlexibleDemand instead of referring
    # to FlexibleDemand itself)
    m.Zone_Energy_Balance.reconstruct()
    if hasattr(m, "Aggregate_Spinning_Reserve_Details"):
        m.Aggregate_Spinning_Reserve_Details.reconstruct()
    if hasattr(m, "Satisfy_Spinning_Reserve_Up_Requirement"):
        m.Satisfy_Spinning_Reserve_Up_Requirement.reconstruct()
        m.Satisfy_Spinning_Reserve_Down_Requirement.reconstruct()
    # reconstruct_energy_balance(m)
    m.SystemCostPerPeriod.reconstruct()
    m.SystemCost.reconstruct()


def reconstruct_energy_balance(m):
    """Reconstruct Energy_Balance constraint, preserving dual values (if present)."""
    # copy the existing Energy_Balance object
    old_Energy_Balance = dict(m.Zone_Energy_Balance)
    m.Zone_Energy_Balance.reconstruct()
    # TODO: now that this happens just before a solve, there may be no need to
    # preserve duals across the reconstruct().
    if m.iteration_number > 0:
        for k in old_Energy_Balance:
            # change dual entries to match new Energy_Balance objects
            m.dual[m.Zone_Energy_Balance[k]] = m.dual.pop(old_Energy_Balance[k])


def register_demand_response_reserves(m):
    if m.options.demand_response_reserve_types == []:
        if hasattr(m, "Spinning_Reserve_Up_Provisions"):
            m.options.demand_response_reserve_types == ["spinning"]
        else:
            m.options.demand_response_reserve_types == ["none"]

    if [rt.lower() for rt in m.options.demand_response_reserve_types] != ["none"]:
        # Register with spinning reserves
        if not hasattr(m, "Spinning_Reserve_Up_Provisions"):
            raise ValueError(
                "--demand-response-reserve-types is set to a value other than "
                "'none' ({}). This requires that a spinning reserve module be "
                "specified in modules.txt.".format(
                    m.options.demand_response_reserve_types
                )
            )

        if hasattr(m, "GEN_SPINNING_RESERVE_TYPES"):
            # using advanced formulation, index by reserve type, balancing area, timepoint
            # define variables for each type of reserves to be provided
            # choose how to allocate the slack between the different reserve products
            m.DR_SPINNING_RESERVE_TYPES = Set(
                dimen=1, initialize=m.options.demand_response_reserve_types
            )
            m.DemandResponseSpinningReserveUp = Var(
                m.DR_SPINNING_RESERVE_TYPES,
                m.BALANCING_AREA_TIMEPOINTS,
                within=NonNegativeReals,
            )
            m.DemandResponseSpinningReserveDown = Var(
                m.DR_SPINNING_RESERVE_TYPES,
                m.BALANCING_AREA_TIMEPOINTS,
                within=NonNegativeReals,
            )
            # constrain reserve provision within available slack
            m.Limit_DemandResponseSpinningReserveUp = Constraint(
                m.BALANCING_AREA_TIMEPOINTS,
                rule=lambda m, ba, tp: sum(
                    m.DemandResponseSpinningReserveUp[rt, ba, tp]
                    for rt in m.DR_SPINNING_RESERVE_TYPES
                )
                <= m.DemandResponseSlackUp[ba, tp],
            )
            m.Limit_DemandResponseSpinningReserveDown = Constraint(
                m.BALANCING_AREA_TIMEPOINTS,
                rule=lambda m, ba, tp: sum(
                    m.DemandResponseSpinningReserveDown[rt, ba, tp]
                    for rt in m.DR_SPINNING_RESERVE_TYPES
                )
                <= m.DemandResponseSlackDown[ba, tp],
            )
            m.Spinning_Reserve_Up_Provisions.append("DemandResponseSpinningReserveUp")
            m.Spinning_Reserve_Down_Provisions.append(
                "DemandResponseSpinningReserveDown"
            )
        else:
            # using older formulation, only one type of spinning reserves, indexed by balancing area, timepoint
            if m.options.demand_response_reserve_types != ["spinning"]:
                raise ValueError(
                    'Unable to use reserve types other than "spinning" with simple spinning reserves module.'
                )
            m.Spinning_Reserve_Up_Provisions.append("DemandResponseSlackUp")
            m.Spinning_Reserve_Down_Provisions.append("DemandResponseSlackDown")


def write_batch_results(m):
    # append results to the batch results file, creating it if needed
    output_file = os.path.join(m.options.outputs_dir, "demand_response_summary.csv")

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
        + tuple("total_direct_costs_per_year_" + str(p) for p in m.PERIODS)
        + tuple("DR_Welfare_Cost_" + str(p) for p in m.PERIODS)
        + tuple(
            prod + " payment " + str(p) for prod in m.DR_PRODUCTS for p in m.PERIODS
        )
        + tuple(prod + " sold " + str(p) for prod in m.DR_PRODUCTS for p in m.PERIODS)
    )


def summary_values(m):
    demand_components = [
        c
        for c in ("zone_demand_mw", "ShiftDemand", "ChargeEVs", "FlexibleDemand")
        if hasattr(m, c)
    ]
    values = []

    # tag (configuration)
    values.extend(
        [
            m.options.scenario_name,
            m.iteration_number,
            m.SystemCost,  # total cost (all periods)
        ]
    )

    # direct costs (including "other")
    values.extend([total_direct_costs_per_year(m, p) for p in m.PERIODS])

    # DR_Welfare_Cost
    values.extend(
        [
            sum(
                m.DR_Welfare_Cost[t] * m.tp_weight_in_year[t]
                for t in m.TPS_IN_PERIOD[p]
            )
            for p in m.PERIODS
        ]
    )

    # payments by customers ([expected demand] * [price offered for that demand])
    # note: this uses the final MC to set the final price, rather than using the
    # final price offered to customers. This creates consistency between the final
    # quantities and prices. Otherwise, we would use prices that differ from the
    # final cost by some random amount, and the split between PS and CS would
    # jump around randomly.
    # note: if switching to using the offered prices, then you may have to use None
    # as the customer payment during iteration 0, since m.dr_price[last_bid, z, tp, prod]
    # may not be defined yet.
    last_bid = m.DR_BID_LIST.last()
    values.extend(
        [
            sum(
                # we assume customers pay final marginal cost, so we don't artificially
                # electricity_demand(m, z, tp, prod) * m.dr_price[last_bid, z, tp, prod] * m.tp_weight_in_year[tp]
                electricity_demand(m, z, tp, prod)
                * electricity_marginal_cost(m, z, tp, prod)
                * m.tp_weight_in_year[tp]
                for z in m.LOAD_ZONES
                for tp in m.TPS_IN_PERIOD[p]
            )
            for prod in m.DR_PRODUCTS
            for p in m.PERIODS
        ]
    )
    # import pdb; pdb.set_trace()

    # total quantities bought (or sold) by customers each year
    values.extend(
        [
            sum(
                electricity_demand(m, z, tp, prod) * m.tp_weight_in_year[tp]
                for z in m.LOAD_ZONES
                for tp in m.TPS_IN_PERIOD[p]
            )
            for prod in m.DR_PRODUCTS
            for p in m.PERIODS
        ]
    )

    return values


def get(component, idx, default):
    try:
        return component[idx]
    except KeyError:
        return default


def write_results(m, include_iter_num=True):
    outputs_dir = m.options.outputs_dir
    tag = filename_tag(m, include_iter_num)

    avg_ts_scale = float(sum(m.ts_scale_to_year[ts] for ts in m.TIMESERIES)) / len(
        m.TIMESERIES
    )
    last_bid = m.DR_BID_LIST.last()

    # get final prices that will be charged to customers (not necessarily
    # the same as the final prices they were offered, if iteration was
    # stopped before complete convergence)
    final_prices_by_timeseries = get_prices(m, flat_revenue_neutral=False)
    final_prices = {
        (lz, tp, prod): final_prices_by_timeseries[lz, ts][prod][i]
        for lz in m.LOAD_ZONES
        for ts in m.TIMESERIES
        for i, tp in enumerate(m.TPS_IN_TS[ts])
        for prod in m.DR_PRODUCTS
    }
    final_quantities = {
        (lz, tp, prod): value(
            sum(
                m.DRBidWeight[b, lz, ts] * m.dr_bid[b, lz, tp, prod]
                for b in m.DR_BID_LIST
            )
        )
        for lz in m.LOAD_ZONES
        for ts in m.TIMESERIES
        for tp in m.TPS_IN_TS[ts]
        for prod in m.DR_PRODUCTS
    }

    # final_prices_by_timepoint = dict()
    # for lz in m.LOAD_ZONES:
    #     for ts in m.TIMESERIES:
    #         for prod in m.DR_PRODUCTS:
    #             for i, tp in enumerate(m.TPS_IN_TS[ts]):
    #                 final_prices_by_timepoint[lz, ts, prod] = \
    #                     final_prices[lz, ts][prod][i]

    # if m.options.dr_flat_pricing:
    #     final_prices = dict()
    #     for lz in m.LOAD_ZONES:
    #         for p in m.PERIODS:
    #             # calculate average marginal cost of power for each period,
    #             # assuming customers will consume the currently-specified amount of power (not react to pricing)
    #             flat_price = zone_period_average_marginal_cost(m, lz, p)
    #             for tp in m.PERIOD_TPS[p]:
    #                 for prod in m.DR_PRODUCTS:
    #                     final_prices[lz, tp, prod] = \
    #                         flat_price if prod=='energy' else 0.0
    # else:
    #     final_prices = {
    #         (lz, tp, prod): electricity_marginal_cost(m, lz, tp, prod)
    #         for lz in m.LOAD_ZONES
    #         for tp in m.TIMEPOINTS
    #         for prod in m.DR_PRODUCTS
    #     }

    util.write_table(
        m,
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        output_file=os.path.join(outputs_dir, "energy_sources{t}.csv".format(t=tag)),
        headings=("load_zone", "period", "timepoint_label")
        + tuple(m.FUELS)
        + tuple(m.NON_FUEL_ENERGY_SOURCES)
        + tuple("curtail_" + s for s in m.NON_FUEL_ENERGY_SOURCES)
        + tuple(m.Zone_Power_Injections)
        + tuple(m.Zone_Power_Withdrawals)
        + tuple("offered price " + prod for prod in m.DR_PRODUCTS)
        + tuple("bid q " + prod for prod in m.DR_PRODUCTS)
        + tuple("final mc " + prod for prod in m.DR_PRODUCTS)
        + tuple("final price " + prod for prod in m.DR_PRODUCTS)
        + tuple("final q " + prod for prod in m.DR_PRODUCTS)
        + ("peak_day", "base_load", "base_price"),
        values=lambda m, z, t: (z, m.tp_period[t], m.tp_timestamp[t])
        + tuple(
            sum(DispatchGenByFuel(m, p, t, f) for p in m.GENS_BY_FUEL[f])
            for f in m.FUELS
        )
        + tuple(
            sum(
                get(m.DispatchGen, (p, t), 0.0)
                for p in m.GENS_BY_NON_FUEL_ENERGY_SOURCE[s]
            )
            for s in m.NON_FUEL_ENERGY_SOURCES
        )
        + tuple(
            sum(
                get(m.DispatchUpperLimit, (p, t), 0.0) - get(m.DispatchGen, (p, t), 0.0)
                for p in m.GENS_BY_NON_FUEL_ENERGY_SOURCE[s]
            )
            for s in m.NON_FUEL_ENERGY_SOURCES
        )
        + tuple(getattr(m, component)[z, t] for component in m.Zone_Power_Injections)
        + tuple(getattr(m, component)[z, t] for component in m.Zone_Power_Withdrawals)
        + tuple(m.dr_price[last_bid, z, t, prod] for prod in m.DR_PRODUCTS)
        + tuple(m.dr_bid[last_bid, z, t, prod] for prod in m.DR_PRODUCTS)
        + tuple(electricity_marginal_cost(m, z, t, prod) for prod in m.DR_PRODUCTS)
        + tuple(final_prices[z, t, prod] for prod in m.DR_PRODUCTS)
        + tuple(final_quantities[z, t, prod] for prod in m.DR_PRODUCTS)
        + (
            "peak"
            if m.ts_scale_to_year[m.tp_ts[t]] < 0.5 * avg_ts_scale
            else "typical",
            m.base_data_dict[z, t][0],
            m.base_data_dict[z, t][1],
        ),
    )

    # import pprint
    # b=[(g, pe, value(m.BuildGen[g, pe]), m.gen_tech[g], m.gen_overnight_cost[g, pe]) for (g, pe) in m.BuildGen if value(m.BuildGen[g, pe]) > 0]
    # bt=set(x[3] for x in b) # technologies
    # pprint([(t, sum(x[2] for x in b if x[3]==t), sum(x[4] for x in b if x[3]==t)/sum(1.0 for x in b if x[3]==t)) for t in bt])


def write_dual_costs(m, include_iter_num=True):
    outputs_dir = m.options.outputs_dir
    tag = filename_tag(m, include_iter_num)

    # with open(os.path.join(outputs_dir, "producer_surplus{t}.csv".format(t=tag)), 'w') as f:
    #     for g, per in m.Max_Build_Potential:
    #         const = m.Max_Build_Potential[g, per]
    #         surplus = const.upper() * m.dual[const]
    #         if surplus != 0.0:
    #             f.write(','.join([const.name, str(surplus)]) + '\n')
    #     # import pdb; pdb.set_trace()
    #     for g, year in m.BuildGen:
    #         var = m.BuildGen[g, year]
    #         if var.ub is not None and var.ub > 0.0 and value(var) > 0.0 and var in m.rc and m.rc[var] != 0.0:
    #             surplus = var.ub * m.rc[var]
    #             f.write(','.join([var.name, str(surplus)]) + '\n')

    outfile = os.path.join(outputs_dir, "dual_costs{t}.csv".format(t=tag))
    dual_data = []
    start_time = time.time()
    print("Writing {} ... ".format(outfile), end=" ")

    def add_dual(const, lbound, ubound, duals, prefix="", offset=0.0):
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
                    raise ValueError(
                        "{} has no {} bound but has a non-zero dual value {}.".format(
                            const.name, "lower" if dual > 0 else "upper", dual
                        )
                    )
            else:
                total_cost = dual * (bound + offset)
                if total_cost != 0.0:
                    dual_data.append(
                        (
                            prefix + const.name,
                            direction,
                            (bound + offset),
                            dual,
                            total_cost,
                        )
                    )

    for comp in m.component_objects(ctype=Var):
        for idx in comp:
            var = comp[idx]
            if var.value is not None:  # ignore vars that weren't used in the model
                if var.is_integer() or var.is_binary():
                    # integrality constraint sets upper and lower bounds
                    add_dual(var, value(var), value(var), m.rc, prefix="integer: ")
                else:
                    add_dual(var, var.lb, var.ub, m.rc)
    for comp in m.component_objects(ctype=Constraint):
        for idx in comp:
            constr = comp[idx]
            if constr.active:
                offset = 0.0
                # cancel out any constants that were stored in the body instead of the bounds
                # (see https://groups.google.com/d/msg/pyomo-forum/-loinAh0Wx4/IIkxdfqxAQAJ)
                # (might be faster to do this once during model setup instead of every time)
                standard_constraint = generate_standard_repn(constr.body)
                if standard_constraint.constant is not None:
                    offset = -standard_constraint.constant
                add_dual(
                    constr,
                    value(constr.lower),
                    value(constr.upper),
                    m.dual,
                    offset=offset,
                )

    dual_data.sort(key=lambda r: (not r[0].startswith("DR_Convex_"), r[3] >= 0) + r)

    with open(outfile, "w") as f:
        f.write(
            ",".join(["constraint", "direction", "bound", "dual", "total_cost"]) + "\n"
        )
        f.writelines(",".join(map(str, r)) + "\n" for r in dual_data)
    print("time taken: {dur:.2f}s".format(dur=time.time() - start_time))


def filename_tag(m, include_iter_num=True):
    tag = ""
    if m.options.scenario_name:
        tag += "_" + m.options.scenario_name
    if include_iter_num:
        if m.options.max_iter is None:
            n_digits = 4
        else:
            n_digits = len(str(m.options.max_iter - 1))
        tag += "".join(f"_{t:0{n_digits}d}" for t in m.iteration_node)
    return tag


def post_solve(m, outputs_dir):
    # report final results, possibly after smoothing,
    # and without the iteration number
    write_dual_costs(m, include_iter_num=False)
    write_results(m, include_iter_num=False)
