import os
from pprint import pprint
from pyomo.environ import *
import switch_model.utilities as utilities
from util import get

def define_arguments(argparser):
    argparser.add_argument('--biofuel-limit', type=float, default=1.0, 
        help="Maximum fraction of power that can be obtained from biofuel in any period (default=1.0)")
    argparser.add_argument('--rps-activate', default='activate',
        dest='rps_level', action='store_const', const='activate', 
        help="Activate RPS (on by default).")
    argparser.add_argument('--rps-deactivate', 
        dest='rps_level', action='store_const', const='deactivate', 
        help="Dectivate RPS.")
    argparser.add_argument('--rps-no-renewables', 
        dest='rps_level', action='store_const', const='no_renewables', 
        help="Deactivate RPS and don't allow any new renewables.")
    argparser.add_argument(
        '--rps-allocation', default=None, 
        choices=[
            'quadratic', 
            'fuel_switch_by_period', 'fuel_switch_by_timeseries', 
            'full_load_heat_rate', 
            'split_commit',
            'relaxed_split_commit',
        ],
        help="Method to use to allocate power output among fuels. Default is fuel_switch_by_period for models "
            + "with unit commitment, full_load_heat_rate for models without."
    )
    
def define_components(m):
    """

    """
    ###################
    # RPS calculation
    ##################
    
    m.f_rps_eligible = Param(m.FUELS, within=Binary)

    m.RPS_ENERGY_SOURCES = Set(initialize=lambda m: 
        list(m.NON_FUEL_ENERGY_SOURCES) + [f for f in m.FUELS if m.f_rps_eligible[f]])

    m.RPS_YEARS = Set(ordered=True)
    m.rps_target = Param(m.RPS_YEARS)

    def rps_target_for_period_rule(m, p):
        """find the last target that is in effect before the _end_ of the period"""
        latest_target = max(y for y in m.RPS_YEARS if y < m.period_start[p] + m.period_length_years[p])
        return m.rps_target[latest_target]
    m.rps_target_for_period = Param(m.PERIODS, initialize=rps_target_for_period_rule)

    # maximum share of (bio)fuels in rps
    # note: using Infinity as the upper limit causes the solution to take forever
    # m.rps_fuel_limit = Param(default=float("inf"), mutable=True)
    m.rps_fuel_limit = Param(initialize=m.options.biofuel_limit, mutable=True)

    # Define DispatchGenRenewableMW, which shows the amount of power produced 
    # by each project from each fuel during each time step.
    define_DispatchGenRenewableMW(m)

    # calculate amount of power produced from renewable fuels during each period
    m.RPSFuelPower = Expression(m.PERIODS, rule=lambda m, per:
        sum(
            m.DispatchGenRenewableMW[p, tp] * m.tp_weight[tp]
                for p in m.FUEL_BASED_GENS 
                    if (p, m.TPS_IN_PERIOD[per].first()) in m.GEN_TPS
                        for tp in m.TPS_IN_PERIOD[per]
        )
    )

    # Note: this rule ignores pumped hydro and batteries, so it could be gamed by producing extra 
    # RPS-eligible power and burning it off in storage losses; on the other hand, 
    # it also neglects the (small) contribution from net flow of pumped hydro projects.
    # TODO: incorporate pumped hydro into this rule, maybe change the target to refer to 
    # sum(getattr(m, component)[z, t] for z in m.LOAD_ZONES) for component in m.Zone_Power_Injections)

    # power production that can be counted toward the RPS each period
    m.RPSEligiblePower = Expression(m.PERIODS, rule=lambda m, per:
        m.RPSFuelPower[per]
        +
        sum(
            m.DispatchGen[p, tp] * m.tp_weight[tp]
                for f in m.NON_FUEL_ENERGY_SOURCES if f in m.RPS_ENERGY_SOURCES
                    for p in m.GENERATION_PROJECTS_BY_NON_FUEL_ENERGY_SOURCE[f]
                        if (p, m.TPS_IN_PERIOD[per].first()) in m.GEN_TPS
                            for tp in m.TPS_IN_PERIOD[per]
        )
    )

    # total power production each period (against which RPS is measured)
    m.RPSTotalPower = Expression(m.PERIODS, rule=lambda m, per:
        sum(
            m.DispatchGen[p, tp] * m.tp_weight[tp]
                for p in m.GENERATION_PROJECTS if (p, m.TPS_IN_PERIOD[per].first()) in m.GEN_TPS
                    for tp in m.TPS_IN_PERIOD[per] 
        )
    )
    
    if m.options.rps_level == 'activate':
        # we completely skip creating the constraint if the RPS is not activated.
        # this makes it easy for other modules to check whether there's an RPS in effect
        # (if we deactivated the RPS after it is constructed, then other modules would
        # have to postpone checking until then)
        m.RPS_Enforce = Constraint(m.PERIODS, rule=lambda m, per:
            m.RPSEligiblePower[per] >= m.rps_target_for_period[per] * m.RPSTotalPower[per]
        )
    elif m.options.rps_level == 'no_renewables':
        # prevent construction of any new exclusively-renewable projects
        # (doesn't actually ban use of biofuels in existing or multi-fuel projects,
        # but that could be done with --biofuel-limit 0)
        m.No_Renewables = Constraint(m.NEW_GEN_BLD_YRS, rule=lambda m, g, bld_yr:
            (m.BuildGen[g, bld_yr] == 0)
            if m.gen_energy_source[g] in m.RPS_ENERGY_SOURCES else
            Constraint.Skip
        )

    # Don't allow (bio)fuels to provide more than a certain percentage of the system's energy
    # Note: when the system really wants to use more biofuel, it is possible to "game" this limit by
    # cycling power through batteries, pumped storage, transmission lines or the hydrogen system to
    # burn off some 
    # extra non-fuel energy, allowing more biofuel into the system. (This doesn't typically happen 
    # with batteries due to high variable costs -- e.g., it has to cycle 4 kWh through a battery to
    # consume 1 kWh of non-biofuel power, to allow 0.05 kWh of additional biofuel into the system. 
    # Even if this can save $0.5/kWh, if battery cycling costs $0.15/kWh, that means $0.60 extra to
    # save $0.025. It also doesn't happen in the hydrogen scenario, since storing intermittent power
    # directly as hydrogen can directly displace biofuel consumption. But it could happen if batteries
    # have low efficiency or low cycling cost, or if transmission losses are significant.)
    # One solution would be to only apply the RPS to the predefined load (not generation), but then
    # transmission and battery losses could be served by fossil fuels.
    # Alternatively: limit fossil fuels to (1-rps) * standard loads 
    # and limit biofuels to (1-bio)*standard loads. This would force renewables to be used for
    # all losses, which is slightly inaccurate.
    # TODO: fix the problem noted above; for now we don't worry too much because there are no
    # transmission losses, the cycling costs for batteries are too high and pumped storage is only
    # adopted on a small scale.
    
    m.RPS_Fuel_Cap = Constraint(m.PERIODS, rule = lambda m, per:
        m.RPSFuelPower[per] <= m.rps_fuel_limit * m.RPSTotalPower[per]
    )

def define_DispatchGenRenewableMW(m):
    # Define DispatchGenRenewableMW, which shows the amount of power produced 
    # by each project from each fuel during each time step.
    # This must be linear, because it may be used in RPS calculations.
    # This can get complex when a project uses multiple fuels and incremental
    # heat rate curves. 
    if m.options.rps_allocation is None:
        if hasattr(m, 'FUEL_USE_SEGMENTS_FOR_GEN'):
            # using heat rate curves and possibly startup fuel; 
            # have to do more advanced allocation of power to fuels
            m.options.rps_allocation = 'fuel_switch_by_period'
        else:
            # only using full load heat rate; use simpler allocation strategy
            m.options.rps_allocation = 'full_load_heat_rate'
        if m.options.verbose:
            print "Using {} method to allocate DispatchGenRenewableMW".format(m.options.rps_allocation)
    
    if m.options.rps_allocation == 'full_load_heat_rate':
        simple_DispatchGenRenewableMW(m)
    elif m.options.rps_allocation == 'quadratic':
        quadratic_DispatchGenRenewableMW(m)
    elif m.options.rps_allocation == 'fuel_switch_by_period':
        binary_by_period_DispatchGenRenewableMW(m)
    elif m.options.rps_allocation == 'fuel_switch_by_timeseries':
        binary_by_timeseries_DispatchGenRenewableMW(m)
    elif m.options.rps_allocation == 'split_commit':
        split_commit_DispatchGenRenewableMW(m)
    elif m.options.rps_allocation == 'relaxed_split_commit':
        relaxed_split_commit_DispatchGenRenewableMW(m)


def simple_DispatchGenRenewableMW(m):
    # Allocate the power produced during each timepoint among the fuels.
    # When not using heat rate curves, this can be calculated directly from
    # fuel usage and the full load heat rate. This also allows use of 
    # multiple fuels in the same project at the same time.
    m.DispatchGenRenewableMW = Expression(
        m._FUEL_BASED_GEN_TPS,
        rule=lambda m, g, t:
            sum(
                m.GenFuelUseRate[g, t, f] 
                    for f in m.FUELS_FOR_GEN[g]
                        if m.f_rps_eligible[f]
            )
            / m.gen_full_load_heat_rate[g]
    )


def split_commit_DispatchGenRenewableMW(m):
    # This approach requires the utility to designate part of their capacity for
    # renewable production and part for non-renewable, and show how they commit
    # and dispatch each part. The current version allows fractional commitment to
    # each mode, but we could use integer commitment variables to force full units 
    # into each mode (more physically meaningful, but unnecessarily restrictive and
    # harder to calculate; the current version may serve as a reasonable accounting
    # method for multi-fuel projects in a partial-RPS environment).
    
    # TODO: limit this to projects that can use both renewable and non-renewable fuel
    # TODO: force CommitGenRenewable == CommitGen when there's 100% RPS  
    # TODO: force DispatchGenRenewableMW == DispatchGen when there's 100% RPS  
    # TODO: force CommitGenRenewable == 0 when there's 0% RPS
    # (these may not be needed: single-category projects will get dispatch forced to zero
    # in one category and forced up to total dispatch in another; non-renewable capacity
    # can't get committed in the 100% RPS due to non-zero min loads)
    
    # count amount of renewable power produced from project
    m.DispatchGenRenewableMW = Var(m._FUEL_BASED_GEN_TPS, within=NonNegativeReals)
    m.DispatchGenRenewableMW_Cap = Constraint(m._FUEL_BASED_GEN_TPS, 
        rule = lambda m, g, tp:
            m.DispatchGenRenewableMW[g, tp] <= m.DispatchGen[g, tp]
    )
    # a portion of every startup and shutdown must be designated as renewable
    m.CommitGenRenewable = Var(m._FUEL_BASED_GEN_TPS, within=NonNegativeReals)
    m.CommitGenRenewable_Cap = Constraint(m._FUEL_BASED_GEN_TPS, 
        rule = lambda m, g, tp:
            m.CommitGenRenewable[g, tp] <= m.CommitGen[g, tp]
    )
    m.StartupGenCapacityRenewable = Var(m._FUEL_BASED_GEN_TPS, within=NonNegativeReals)
    m.StartupGenCapacityRenewable_Cap = Constraint(m._FUEL_BASED_GEN_TPS, 
        rule = lambda m, g, tp:
            m.StartupGenCapacityRenewable[g, tp] <= m.StartupGenCapacity[g, tp]
    )
    m.ShutdownGenCapacityRenewable = Var(m._FUEL_BASED_GEN_TPS, within=NonNegativeReals)
    m.ShutdownGenCapacityRenewable_Cap = Constraint(m._FUEL_BASED_GEN_TPS, 
        rule = lambda m, g, tp:
            m.ShutdownGenCapacityRenewable[g, tp] <= m.ShutdownGenCapacity[g, tp]
    )
    # chain commitments, startup and shutdown for renewables
    m.Commit_StartupGenCapacity_ShutdownGenCapacity_Consistency_Renewable = Constraint(
        m._FUEL_BASED_GEN_TPS,
        rule=lambda m, g, tp: 
            m.CommitGenRenewable[g, m.tp_previous[tp]]
            + m.StartupGenCapacityRenewable[g, tp] 
            - m.ShutdownGenCapacityRenewable[g, tp] 
            == m.CommitGenRenewable[g, tp]
    )
    # must use committed capacity for renewable production
    m.Enforce_Dispatch_Upper_Limit_Renewable = Constraint(
        m._FUEL_BASED_GEN_TPS,
        rule=lambda m, g, tp: 
            m.DispatchGenRenewableMW[g, tp] <= m.CommitGenRenewable[g, tp]
    )
    # can't dispatch non-renewable capacity below its lower limit
    m.Enforce_Dispatch_Lower_Limit_Non_Renewable = Constraint(
        m._FUEL_BASED_GEN_TPS,
        rule=lambda m, g, tp: 
            (m.DispatchGen[g, tp] - m.DispatchGenRenewableMW[g, tp])
            >= 
            (m.CommitGen[g, tp] - m.CommitGenRenewable[g, tp]) 
            * m.gen_min_load_fraction_TP[g, tp]
    )
    # use standard heat rate calculations for renewable and non-renewable parts
    m.ProjRenewableFuelUseRate_Calculate = Constraint(
        m.GEN_TPS_FUEL_PIECEWISE_CONS_SET,
        rule=lambda m, g, tp, intercept, incremental_heat_rate: 
            sum(
                m.GenFuelUseRate[g, tp, f] 
                    for f in m.FUELS_FOR_GEN[g]
                        if f in m.RPS_ENERGY_SOURCES
            ) 
            >=
            m.StartupGenCapacityRenewable[g, tp] * m.gen_startup_fuel[g] / m.tp_duration_hrs[tp]
            + intercept * m.CommitGenRenewable[g, tp]
            + incremental_heat_rate * m.DispatchGenRenewableMW[g, tp]
    )
    m.ProjNonRenewableFuelUseRate_Calculate = Constraint(
        m.GEN_TPS_FUEL_PIECEWISE_CONS_SET,
        rule=lambda m, g, tp, intercept, incremental_heat_rate: 
            sum(
                m.GenFuelUseRate[g, tp, f] 
                    for f in m.FUELS_FOR_GEN[g]
                        if f not in m.RPS_ENERGY_SOURCES
            ) 
            >=
            (m.StartupGenCapacity[g, tp] - m.StartupGenCapacityRenewable[g, tp]) * m.gen_startup_fuel[g] / m.tp_duration_hrs[tp]
            + intercept * (m.CommitGen[g, tp] - m.CommitGenRenewable[g, tp])
            + incremental_heat_rate * (m.DispatchGen[g, tp] - m.DispatchGenRenewableMW[g, tp])
    )

def relaxed_split_commit_DispatchGenRenewableMW(m):
    # This is similar to the split_commit approach, but allows startup fuel
    # to be freely allocated between renewable and non-renewable fuels.
    # This eliminates the need for m.CommitGenRenewable variables, which are
    # then replaced by m.DispatchGenRenewableMW.
    # This means all startup fuel can be non-renewable, except when the RPS
    # is 100%.
        
    # count amount of renewable power produced from project
    m.DispatchGenRenewableMW = Var(m._FUEL_BASED_GEN_TPS, within=NonNegativeReals)
    m.DispatchGenRenewableMW_Cap = Constraint(m._FUEL_BASED_GEN_TPS, 
        rule = lambda m, g, tp:
            m.DispatchGenRenewableMW[g, tp] <= m.DispatchGen[g, tp]
    )
    m.StartupGenCapacityRenewable = Var(m._FUEL_BASED_GEN_TPS, within=NonNegativeReals)
    m.StartupGenCapacityRenewable_Cap = Constraint(m._FUEL_BASED_GEN_TPS, 
        rule = lambda m, g, tp:
            m.StartupGenCapacityRenewable[g, tp] <= m.StartupGenCapacity[g, tp]
    )

    # can't dispatch non-renewable capacity below its lower limit
    m.Enforce_Dispatch_Lower_Limit_Non_Renewable = Constraint(
        m._FUEL_BASED_GEN_TPS,
        rule=lambda m, g, tp: 
            (m.DispatchGen[g, tp] - m.DispatchGenRenewableMW[g, tp])
            >= 
            (m.CommitGen[g, tp] - m.DispatchGenRenewableMW[g, tp]) 
            * m.gen_min_load_fraction_TP[g, tp]
    )
    
    # use standard heat rate calculations for renewable and non-renewable parts
    m.ProjRenewableFuelUseRate_Calculate = Constraint(
        m.GEN_TPS_FUEL_PIECEWISE_CONS_SET,
        rule=lambda m, g, tp, intercept, incremental_heat_rate: 
            sum(
                m.GenFuelUseRate[g, tp, f] 
                    for f in m.FUELS_FOR_GEN[g]
                        if f in m.RPS_ENERGY_SOURCES
            ) 
            >=
            m.StartupGenCapacityRenewable[g, tp] * m.gen_startup_fuel[g] / m.tp_duration_hrs[tp]
            + intercept * m.DispatchGenRenewableMW[g, tp]
            + incremental_heat_rate * m.DispatchGenRenewableMW[g, tp]
    )
    m.ProjNonRenewableFuelUseRate_Calculate = Constraint(
        m.GEN_TPS_FUEL_PIECEWISE_CONS_SET,
        rule=lambda m, g, tp, intercept, incremental_heat_rate: 
            sum(
                m.GenFuelUseRate[g, tp, f] 
                    for f in m.FUELS_FOR_GEN[g]
                        if f not in m.RPS_ENERGY_SOURCES
            ) 
            >=
            (m.StartupGenCapacity[g, tp] - m.StartupGenCapacityRenewable[g, tp]) * m.gen_startup_fuel[g] / m.tp_duration_hrs[tp]
            + intercept * (m.CommitGen[g, tp] - m.DispatchGenRenewableMW[g, tp])
            + incremental_heat_rate * (m.DispatchGen[g, tp] - m.DispatchGenRenewableMW[g, tp])
    )

    # don't allow any non-renewable fuel if RPS is 100%
    if m.options.rps_level == 'activate':
        # find all dispatch points for non-renewable fuels during periods with 100% RPS
        m.FULL_RPS_GEN_FOSSIL_FUEL_DISPATCH_POINTS = Set(
            dimen=3,
            initialize=lambda m: [
                (g, tp, f) 
                    for per in m.PERIODS if m.rps_target_for_period[per] == 1.0
                        for g in m.FUEL_BASED_GENS 
                            if (g, m.TPS_IN_PERIOD[per].first()) in m.GEN_TPS
                                for f in m.FUELS_FOR_GEN[g] if not m.f_rps_eligible[f]
                                    for tp in m.TPS_IN_PERIOD[per]
            ]
        )
        m.No_Fossil_Fuel_With_Full_RPS = Constraint(
            m.FULL_RPS_GEN_FOSSIL_FUEL_DISPATCH_POINTS,
            rule=lambda m, g, tp, f: m.GenFuelUseRate[g, tp, f] == 0.0
        )


def binary_by_period_DispatchGenRenewableMW(m):
    # NOTE: this could be extended to handle fuel blends (e.g., 50% biomass/50% coal)
    # by assigning an RPS eligibility level to each fuel (e.g., 50%), then
    # setting binary variables for whether to use each fuel during each period
    # (possibly treated as an SOS; or might be able to have an SOS for total
    # amount to produce from each fuel during the period, and require that total
    # consumption of each fuel <= production from that fuel * max((consumption+startup)/output across operating points)
    # This could be further simplified by creating a set of eligibility levels,
    # and choosing the amount to produce from each eligibility level (similar to the
    # renewable/non-renewable distinction here, but with a 50% renewable category)
    
    m.GEN_WITH_FUEL_ACTIVE_PERIODS = Set(dimen=2, initialize=lambda m: {
        (g, pe) 
            for g in m.FUEL_BASED_GENS for pe in m.PERIODS
                if (g, m.TPS_IN_PERIOD[pe].first()) in m._FUEL_BASED_GEN_TPS
    })
    
    # choose whether to run (only) on renewable fuels during each period
    m.DispatchRenewableFlag = Var(m.GEN_WITH_FUEL_ACTIVE_PERIODS, within=Binary)
    
    # force flag on or off when the RPS is simple (to speed computation)
    m.Force_DispatchRenewableFlag = Constraint(
        m.GEN_WITH_FUEL_ACTIVE_PERIODS, 
        rule=lambda m, g, pe:
            (m.DispatchRenewableFlag[g, pe] == 0) 
            if (m.rps_target_for_period[pe]==0.0 or m.options.rps_level != 'activate')
            else (
                (m.DispatchRenewableFlag[g, pe] == 1) 
                if m.rps_target_for_period[pe]==1.0
                else Constraint.Skip
            )
    )
    
    # count amount of renewable power produced from project
    m.DispatchGenRenewableMW = Var(m._FUEL_BASED_GEN_TPS, within=NonNegativeReals)
    
    # don't overcount renewable power production
    m.Limit_DispatchGenRenewableMW = Constraint(
        m._FUEL_BASED_GEN_TPS, 
            rule=lambda m, g, tp: 
                m.DispatchGenRenewableMW[g, tp] <= m.DispatchGen[g, tp]
    )
    # force the flag to be set during renewable timepoints
    m.Set_DispatchRenewableFlag = Constraint(
            m._FUEL_BASED_GEN_TPS, 
            rule=lambda m, g, tp:
                 m.DispatchGenRenewableMW[g, tp] 
                 <= 
                 m.DispatchRenewableFlag[g, m.tp_period[tp]] * m.gen_capacity_limit_mw[g]
    )
    
    # prevent use of non-renewable fuels during renewable timepoints
    def Enforce_DispatchRenewableFlag_rule(m, g, tp, f):
        if m.f_rps_eligible[f]:
            return Constraint.Skip
        else:
            # harder to read like this, but having all numerical values on the right hand side
            # facilitates analysis of duals and reduced costs
            # note: we also add a little slack to avoid having this be the main constraint
            # on total output from any power plant (that also clarifies dual analysis)
            big_fuel = 1.01 * m.gen_capacity_limit_mw[g] * m.gen_full_load_heat_rate[g]
            return (
                m.GenFuelUseRate[g, tp, f] 
                + m.DispatchRenewableFlag[g, m.tp_period[tp]] * big_fuel
                <= 
                big_fuel
            )
    m.Enforce_DispatchRenewableFlag = Constraint(
        m.GEN_TP_FUELS, rule=Enforce_DispatchRenewableFlag_rule
    )

def binary_by_timeseries_DispatchGenRenewableMW(m):
    m.GEN_WITH_FUEL_ACTIVE_TIMESERIES = Set(dimen=2, initialize=lambda m: {
        (g, ts) 
            for g in m.FUEL_BASED_GENS for ts in m.TIMESERIES
                if (g, m.TPS_IN_TS[ts].first()) in m._FUEL_BASED_GEN_TPS
    })
    
    # choose whether to run (only) on renewable fuels during each period
    m.DispatchRenewableFlag = Var(m.GEN_WITH_FUEL_ACTIVE_TIMESERIES, within=Binary)
    
    # force flag on or off depending on RPS status (to speed computation)
    m.Force_DispatchRenewableFlag = Constraint(
        m.GEN_WITH_FUEL_ACTIVE_TIMESERIES, 
        rule=lambda m, g, ts:
            (m.DispatchRenewableFlag[g, ts] == 0) if m.rps_target_for_period[m.ts_period[ts]]==0.0
            else (
                (m.DispatchRenewableFlag[g, ts] == 1) if m.rps_target_for_period[m.ts_period[ts]]==1.0
                else Constraint.Skip
            )
    )
    
    # count amount of renewable power produced from project
    m.DispatchGenRenewableMW = Var(m._FUEL_BASED_GEN_TPS, within=NonNegativeReals)
    
    # don't overcount renewable power production
    m.Limit_DispatchGenRenewableMW = Constraint(
        m._FUEL_BASED_GEN_TPS, 
            rule=lambda m, g, tp: 
                m.DispatchGenRenewableMW[g, tp] <= m.DispatchGen[g, tp]
    )
    # force the flag to be set during renewable timepoints
    m.Set_DispatchRenewableFlag = Constraint(
            m._FUEL_BASED_GEN_TPS, 
            rule=lambda m, g, tp:
                 m.DispatchGenRenewableMW[g, tp] 
                 <= 
                 m.DispatchRenewableFlag[g, m.tp_ts[tp]] * m.gen_capacity_limit_mw[g]
    )
    
    # prevent use of non-renewable fuels during renewable timepoints
    m.Enforce_DispatchRenewableFlag = Constraint(
        m.GEN_TP_FUELS, 
        rule=lambda m, g, tp, f: 
            Constraint.Skip if m.f_rps_eligible[f]
            else (
                # original code, rewritten to get numerical parts on rhs
                # m.GenFuelUseRate[g, tp, f]
                # <=
                # (1-m.DispatchRenewableFlag[g, m.tp_ts[tp]]) * m.gen_capacity_limit_mw[g] * m.gen_full_load_heat_rate[g]
                m.GenFuelUseRate[g, tp, f] 
                + m.DispatchRenewableFlag[g, m.tp_ts[tp]] * m.gen_capacity_limit_mw[g] * m.gen_full_load_heat_rate[g]
                <= 
                m.gen_capacity_limit_mw[g] * m.gen_full_load_heat_rate[g]
            )
    )



def advanced2_DispatchGenRenewableMW(m):
    # choose whether to run (only) on renewable fuels during each timepoint
    m.DispatchRenewableFlag = Var(m._FUEL_BASED_GEN_TPS, within=Binary)
    
    # count amount of renewable power produced from project
    m.DispatchGenRenewableMW = Var(m._FUEL_BASED_GEN_TPS, within=NonNegativeReals)
    
    # don't overcount renewable power production
    m.Limit_DispatchGenRenewableMW = Constraint(
        m._FUEL_BASED_GEN_TPS, 
            rule=lambda m, g, tp: m.DispatchGenRenewableMW[g, tp] <= m.DispatchGen[g, tp]
    )
    # force the flag to be set during renewable timepoints
    m.Set_DispatchRenewableFlag = Constraint(
            m._FUEL_BASED_GEN_TPS, 
            rule=lambda m, g, tp:
                 m.DispatchGenRenewableMW[g, tp] 
                 <= 
                 m.DispatchRenewableFlag[g, tp] * m.gen_capacity_limit_mw[g]
    )
    
    # prevent use of non-renewable fuels during renewable timepoints
    m.Enforce_DispatchRenewableFlag = Constraint(
        m.GEN_TP_FUELS, 
        rule=lambda m, g, tp, f: 
            Constraint.Skip if m.f_rps_eligible[f]
            else (
                m.GenFuelUseRate[g, tp, f] 
                <= 
                (1-m.DispatchRenewableFlag[g, tp]) * m.gen_capacity_limit_mw[g] * m.gen_full_load_heat_rate[g]
            )
    )


def advanced1_DispatchGenRenewableMW(m):
    # Allocate the power produced during each timepoint among the fuels.

    m.DispatchGenRenewableMW = Var(m.GEN_TP_FUELS, within=NonNegativeReals)
    # make sure this matches total production
    m.DispatchGenRenewableMW_Total = Constraint(
        m._FUEL_BASED_GEN_TPS, 
        rule=lambda m, g, tp: 
            sum(m.DispatchGenRenewableMW[g, tp, f] for f in m.FUELS_FOR_GEN[g])
            ==
            m.DispatchGen[g, tp]
    )
    
    # choose a single fuel to use during each timestep
    m.DispatchFuelFlag = Var(m.GEN_TP_FUELS, within=Binary)
    m.DispatchFuelFlag_Total = Constraint(
        m._FUEL_BASED_GEN_TPS, 
        rule=lambda m, g, tp: 
            sum(m.DispatchFuelFlag[g, tp, f] for f in m.FUELS_FOR_GEN[g])
            ==
            1
    )

    # consume only the selected fuel and allocate all production to that fuel (big-M constraints)
    m.Allocate_Dispatch_Output = Constraint(
        m.GEN_TP_FUELS, 
        rule=lambda m, g, tp, f: 
            m.DispatchGenRenewableMW[g, tp, f] 
            <= 
            m.DispatchFuelFlag[g, tp, f] * m.gen_capacity_limit_mw[g]
    )
    m.Allocate_Dispatch_Fuel = Constraint(
        m.GEN_TP_FUELS, 
        rule=lambda m, g, tp, f: 
            m.GenFuelUseRate[g, tp, f] 
            <= 
            m.DispatchFuelFlag[g, tp, f] * m.gen_capacity_limit_mw[g] * m.gen_full_load_heat_rate[g]
    )
    
    # note: in cases where a project has a single fuel, the presolver should force  
    # DispatchGenRenewableMW for that fuel to match DispatchGen, and possibly
    # eliminate the allocation constraints
    
    # possible simplifications:
    # omit binary variables and big-m constraints if len(m.FUELS_FOR_GEN[p]) == 1 
    #   (assign all production to the single fuel)
    # use m.GenFuelUseRate[g, t, f] / m.gen_full_load_heat_rate[g]
    #    for gects with no heat rate curve and no startup fuel

    # note: a continuous, quadratic version of this function can be created as follows:
    # - make DispatchFuelFlag a PercentFraction instead of Binary
    # - replace gen_capacity_limit_mw with GenCapacity in Allocate_Dispatch_Output
    # - replace m.gen_capacity_limit_mw * m.gen_full_load_heat_rate with 
    #   sum(m.GenFuelUseRate[g, t, f] for f in m.FUELS_FOR_GEN[g])
    #   in Allocate_Dispatch_Fuel (define this as an Expression in dispatch.py)
    # - replace <= with == in the allocation constraints
    # - drop the DispatchGenRenewableMW_Total constraint
    
    # or this would also work:
    # m.DispatchGenRenewableMW = Var(m.GEN_TP_FUELS)
    # m.DispatchGenRenewableMW_Allocate = Constraint(
    #     m.GEN_TP_FUELS,
    #     rule = lambda m, g, t, f:
    #         m.DispatchGenRenewableMW[g, t, f]
    #         * sum(m.GenFuelUseRate[g, t, _f] for _f in m.FUELS_FOR_GEN[g])
    #         ==
    #         DispatchGen[g, t]
    #         * m.GenFuelUseRate[g, t, f]
    # )

def quadratic_DispatchGenRenewableMW(m):
    # choose how much power to obtain from renewables during each timepoint
    m.DispatchRenewableFraction = Var(m._FUEL_BASED_GEN_TPS, within=PercentFraction)
    
    # count amount of renewable power produced from project
    m.DispatchGenRenewableMW = Var(m._FUEL_BASED_GEN_TPS, within=NonNegativeReals)
    
    # don't overcount renewable power production
    m.Set_DispatchRenewableFraction = Constraint(
            m._FUEL_BASED_GEN_TPS, 
            rule=lambda m, g, tp:
                 m.DispatchGenRenewableMW[g, tp] 
                 <= 
                 m.DispatchRenewableFraction[g, tp] * m.DispatchGen[g, tp]
    )
    m.Enforce_DispatchRenewableFraction = Constraint(
        m._FUEL_BASED_GEN_TPS, 
        rule=lambda m, g, tp: 
            sum(
                m.GenFuelUseRate[g, tp, f] 
                    for f in m.FUELS_FOR_GEN[g] 
                        if m.f_rps_eligible[f]
            )
            >=
            m.DispatchRenewableFraction[g, tp] *
            sum(
                m.GenFuelUseRate[g, tp, f] 
                    for f in m.FUELS_FOR_GEN[g]
            )
    )

def quadratic1_DispatchGenRenewableMW(m):
    # Allocate the power produced during each timepoint among the fuels.
    m.DispatchGenRenewableMW = Var(m.GEN_TP_FUELS, within=NonNegativeReals)

    # make sure this matches total production
    m.DispatchGenRenewableMW_Total = Constraint(
        m._FUEL_BASED_GEN_TPS, 
        rule=lambda m, g, tp: 
            sum(m.DispatchGenRenewableMW[g, tp, f] for f in m.FUELS_FOR_GEN[g])
            ==
            m.DispatchGen[g, tp]
    )
    
    m.DispatchGenRenewableMW_Allocate = Constraint(
        m.GEN_TP_FUELS,
        rule = lambda m, g, t, f:
            m.DispatchGenRenewableMW[g, t, f]
            * sum(m.GenFuelUseRate[g, t, _f] for _f in m.FUELS_FOR_GEN[g])
            <=
            m.DispatchGen[g, t]
            * m.GenFuelUseRate[g, t, f]
    )

def load_inputs(m, switch_data, inputs_dir):
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'fuels.tab'),
        select=('fuel', 'rps_eligible'),
        param=(m.f_rps_eligible,))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'rps_targets.tab'),
        autoselect=True,
        index=m.RPS_YEARS,
        param=(m.rps_target,))

