import os
from pprint import pprint
from pyomo.environ import *
import switch_mod.utilities as utilities
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

    # Define DispatchProjRenewableMW, which shows the amount of power produced 
    # by each project from each fuel during each time step.
    define_DispatchProjRenewableMW(m)

    # calculate amount of power produced from renewable fuels during each period
    m.RPSFuelPower = Expression(m.PERIODS, rule=lambda m, per:
        sum(
            m.DispatchProjRenewableMW[p, tp] * m.tp_weight[tp]
                for p in m.FUEL_BASED_PROJECTS 
                    if (p, m.PERIOD_TPS[per].first()) in m.PROJ_DISPATCH_POINTS
                        for tp in m.PERIOD_TPS[per]
        )
    )

    # Note: this rule ignores pumped hydro and batteries, so it could be gamed by producing extra 
    # RPS-eligible power and burning it off in storage losses; on the other hand, 
    # it also neglects the (small) contribution from net flow of pumped hydro projects.
    # TODO: incorporate pumped hydro into this rule, maybe change the target to refer to 
    # sum(getattr(m, component)[lz, t] for lz in m.LOAD_ZONES) for component in m.LZ_Energy_Components_Produce)

    # power production that can be counted toward the RPS each period
    m.RPSEligiblePower = Expression(m.PERIODS, rule=lambda m, per:
        m.RPSFuelPower[per]
        +
        sum(
            m.DispatchProj[p, tp] * m.tp_weight[tp]
                for f in m.NON_FUEL_ENERGY_SOURCES if f in m.RPS_ENERGY_SOURCES
                    for p in m.PROJECTS_BY_NON_FUEL_ENERGY_SOURCE[f]
                        if (p, m.PERIOD_TPS[per].first()) in m.PROJ_DISPATCH_POINTS
                            for tp in m.PERIOD_TPS[per]
        )
        -
        # assume DumpPower is curtailed renewable energy
        sum(m.DumpPower[lz, tp] * m.tp_weight[tp] for lz in m.LOAD_ZONES for tp in m.PERIOD_TPS[per])
    )

    # total power production each period (against which RPS is measured)
    # (we subtract DumpPower, because that shouldn't have been produced in the first place)
    m.RPSTotalPower = Expression(m.PERIODS, rule=lambda m, per:
        sum(
            m.DispatchProj[p, tp] * m.tp_weight[tp]
                for p in m.PROJECTS if (p, m.PERIOD_TPS[per].first()) in m.PROJ_DISPATCH_POINTS
                    for tp in m.PERIOD_TPS[per] 
        )
        - sum(m.DumpPower[lz, tp] * m.tp_weight[tp] for lz in m.LOAD_ZONES for tp in m.PERIOD_TPS[per])
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
        m.No_Renewables = Constraint(m.NEW_PROJ_BUILDYEARS, rule=lambda m, proj, bld_yr:
            (m.BuildProj[proj, bld_yr] == 0)
            if m.proj_energy_source[proj] in m.RPS_ENERGY_SOURCES else
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

def define_DispatchProjRenewableMW(m):
    # Define DispatchProjRenewableMW, which shows the amount of power produced 
    # by each project from each fuel during each time step.
    # This must be linear, because it may be used in RPS calculations.
    # This can get complex when a project uses multiple fuels and incremental
    # heat rate curves. 
    if m.options.rps_allocation is None:
        if hasattr(m, 'PROJ_FUEL_USE_SEGMENTS'):
            # using heat rate curves and possibly startup fuel; 
            # have to do more advanced allocation of power to fuels
            m.options.rps_allocation = 'fuel_switch_by_period'
        else:
            # only using full load heat rate; use simpler allocation strategy
            m.options.rps_allocation = 'full_load_heat_rate'
        if m.options.verbose:
            print "Using {} method to allocate DispatchProjRenewableMW".format(m.options.rps_allocation)
    
    if m.options.rps_allocation == 'full_load_heat_rate':
        simple_DispatchProjRenewableMW(m)
    elif m.options.rps_allocation == 'quadratic':
        quadratic_DispatchProjRenewableMW(m)
    elif m.options.rps_allocation == 'fuel_switch_by_period':
        binary_by_period_DispatchProjRenewableMW(m)
    elif m.options.rps_allocation == 'fuel_switch_by_timeseries':
        binary_by_timeseries_DispatchProjRenewableMW(m)
    elif m.options.rps_allocation == 'split_commit':
        split_commit_DispatchProjRenewableMW(m)
    elif m.options.rps_allocation == 'relaxed_split_commit':
        relaxed_split_commit_DispatchProjRenewableMW(m)


def simple_DispatchProjRenewableMW(m):
    # Allocate the power produced during each timepoint among the fuels.
    # When not using heat rate curves, this can be calculated directly from
    # fuel usage and the full load heat rate. This also allows use of 
    # multiple fuels in the same project at the same time.
    m.DispatchProjRenewableMW = Expression(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS,
        rule=lambda m, proj, t:
            sum(
                m.ProjFuelUseRate[proj, t, f] 
                    for f in m.PROJ_FUELS[proj]
                        if m.f_rps_eligible[f]
            )
            / m.proj_full_load_heat_rate[proj]
    )


def split_commit_DispatchProjRenewableMW(m):
    # This approach requires the utility to designate part of their capacity for
    # renewable production and part for non-renewable, and show how they commit
    # and dispatch each part. The current version allows fractional commitment to
    # each mode, but we could use integer commitment variables to force full units 
    # into each mode (more physically meaningful, but unnecessarily restrictive and
    # harder to calculate; the current version may serve as a reasonable accounting
    # method for multi-fuel projects in a partial-RPS environment).
    
    # TODO: limit this to projects that can use both renewable and non-renewable fuel
    # TODO: force CommitProjectRenewable == CommitProject when there's 100% RPS  
    # TODO: force DispatchProjRenewableMW == DispatchProj when there's 100% RPS  
    # TODO: force CommitProjectRenewable == 0 when there's 0% RPS
    # (these may not be needed: single-category projects will get dispatch forced to zero
    # in one category and forced up to total dispatch in another; non-renewable capacity
    # can't get committed in the 100% RPS due to non-zero min loads)
    
    # count amount of renewable power produced from project
    m.DispatchProjRenewableMW = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    m.DispatchProjRenewableMW_Cap = Constraint(m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule = lambda m, pr, tp:
            m.DispatchProjRenewableMW[pr, tp] <= m.DispatchProj[pr, tp]
    )
    # a portion of every startup and shutdown must be designated as renewable
    m.CommitProjectRenewable = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    m.CommitProjectRenewable_Cap = Constraint(m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule = lambda m, pr, tp:
            m.CommitProjectRenewable[pr, tp] <= m.CommitProject[pr, tp]
    )
    m.StartupRenewable = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    m.StartupRenewable_Cap = Constraint(m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule = lambda m, pr, tp:
            m.StartupRenewable[pr, tp] <= m.Startup[pr, tp]
    )
    m.ShutdownRenewable = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    m.ShutdownRenewable_Cap = Constraint(m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule = lambda m, pr, tp:
            m.ShutdownRenewable[pr, tp] <= m.Shutdown[pr, tp]
    )
    # chain commitments, startup and shutdown for renewables
    m.Commit_Startup_Shutdown_Consistency_Renewable = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS,
        rule=lambda m, pr, tp: 
            m.CommitProjectRenewable[pr, m.tp_previous[tp]]
            + m.StartupRenewable[pr, tp] 
            - m.ShutdownRenewable[pr, tp] 
            == m.CommitProjectRenewable[pr, tp]
    )
    # must use committed capacity for renewable production
    m.Enforce_Dispatch_Upper_Limit_Renewable = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS,
        rule=lambda m, pr, tp: 
            m.DispatchProjRenewableMW[pr, tp] <= m.CommitProjectRenewable[pr, tp]
    )
    # can't dispatch non-renewable capacity below its lower limit
    m.Enforce_Dispatch_Lower_Limit_Non_Renewable = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS,
        rule=lambda m, pr, tp: 
            (m.DispatchProj[pr, tp] - m.DispatchProjRenewableMW[pr, tp])
            >= 
            (m.CommitProject[pr, tp] - m.CommitProjectRenewable[pr, tp]) 
            * m.proj_min_load_fraction_TP[pr, tp]
    )
    # use standard heat rate calculations for renewable and non-renewable parts
    m.ProjRenewableFuelUseRate_Calculate = Constraint(
        m.PROJ_DISP_FUEL_PIECEWISE_CONS_SET,
        rule=lambda m, pr, tp, intercept, incremental_heat_rate: 
            sum(
                m.ProjFuelUseRate[pr, tp, f] 
                    for f in m.PROJ_FUELS[pr]
                        if f in m.RPS_ENERGY_SOURCES
            ) 
            >=
            m.StartupRenewable[pr, tp] * m.proj_startup_fuel[pr] / m.tp_duration_hrs[tp]
            + intercept * m.CommitProjectRenewable[pr, tp]
            + incremental_heat_rate * m.DispatchProjRenewableMW[pr, tp]
    )
    m.ProjNonRenewableFuelUseRate_Calculate = Constraint(
        m.PROJ_DISP_FUEL_PIECEWISE_CONS_SET,
        rule=lambda m, pr, tp, intercept, incremental_heat_rate: 
            sum(
                m.ProjFuelUseRate[pr, tp, f] 
                    for f in m.PROJ_FUELS[pr]
                        if f not in m.RPS_ENERGY_SOURCES
            ) 
            >=
            (m.Startup[pr, tp] - m.StartupRenewable[pr, tp]) * m.proj_startup_fuel[pr] / m.tp_duration_hrs[tp]
            + intercept * (m.CommitProject[pr, tp] - m.CommitProjectRenewable[pr, tp])
            + incremental_heat_rate * (m.DispatchProj[pr, tp] - m.DispatchProjRenewableMW[pr, tp])
    )

def relaxed_split_commit_DispatchProjRenewableMW(m):
    # This is similar to the split_commit approach, but allows startup fuel
    # to be freely allocated between renewable and non-renewable fuels.
    # This eliminates the need for m.CommitProjectRenewable variables, which are
    # then replaced by m.DispatchProjRenewableMW.
    # This means all startup fuel can be non-renewable, except when the RPS
    # is 100%.
        
    # count amount of renewable power produced from project
    m.DispatchProjRenewableMW = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    m.DispatchProjRenewableMW_Cap = Constraint(m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule = lambda m, pr, tp:
            m.DispatchProjRenewableMW[pr, tp] <= m.DispatchProj[pr, tp]
    )
    m.StartupRenewable = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    m.StartupRenewable_Cap = Constraint(m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule = lambda m, pr, tp:
            m.StartupRenewable[pr, tp] <= m.Startup[pr, tp]
    )

    # can't dispatch non-renewable capacity below its lower limit
    m.Enforce_Dispatch_Lower_Limit_Non_Renewable = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS,
        rule=lambda m, pr, tp: 
            (m.DispatchProj[pr, tp] - m.DispatchProjRenewableMW[pr, tp])
            >= 
            (m.CommitProject[pr, tp] - m.DispatchProjRenewableMW[pr, tp]) 
            * m.proj_min_load_fraction_TP[pr, tp]
    )
    
    # use standard heat rate calculations for renewable and non-renewable parts
    m.ProjRenewableFuelUseRate_Calculate = Constraint(
        m.PROJ_DISP_FUEL_PIECEWISE_CONS_SET,
        rule=lambda m, pr, tp, intercept, incremental_heat_rate: 
            sum(
                m.ProjFuelUseRate[pr, tp, f] 
                    for f in m.PROJ_FUELS[pr]
                        if f in m.RPS_ENERGY_SOURCES
            ) 
            >=
            m.StartupRenewable[pr, tp] * m.proj_startup_fuel[pr] / m.tp_duration_hrs[tp]
            + intercept * m.DispatchProjRenewableMW[pr, tp]
            + incremental_heat_rate * m.DispatchProjRenewableMW[pr, tp]
    )
    m.ProjNonRenewableFuelUseRate_Calculate = Constraint(
        m.PROJ_DISP_FUEL_PIECEWISE_CONS_SET,
        rule=lambda m, pr, tp, intercept, incremental_heat_rate: 
            sum(
                m.ProjFuelUseRate[pr, tp, f] 
                    for f in m.PROJ_FUELS[pr]
                        if f not in m.RPS_ENERGY_SOURCES
            ) 
            >=
            (m.Startup[pr, tp] - m.StartupRenewable[pr, tp]) * m.proj_startup_fuel[pr] / m.tp_duration_hrs[tp]
            + intercept * (m.CommitProject[pr, tp] - m.DispatchProjRenewableMW[pr, tp])
            + incremental_heat_rate * (m.DispatchProj[pr, tp] - m.DispatchProjRenewableMW[pr, tp])
    )

    # don't allow any non-renewable fuel if RPS is 100%
    if m.options.rps_level == 'activate':
        # find all dispatch points for non-renewable fuels during periods with 100% RPS
        m.FULL_RPS_PROJ_FOSSIL_FUEL_DISPATCH_POINTS = Set(
            dimen=3,
            initialize=lambda m: [
                (pr, tp, f) 
                    for per in m.PERIODS if m.rps_target_for_period[per] == 1.0
                        for pr in m.FUEL_BASED_PROJECTS 
                            if (pr, m.PERIOD_TPS[per].first()) in m.PROJ_DISPATCH_POINTS
                                for f in m.PROJ_FUELS[pr] if not m.f_rps_eligible[f]
                                    for tp in m.PERIOD_TPS[per]
            ]
        )
        m.No_Fossil_Fuel_With_Full_RPS = Constraint(
            m.FULL_RPS_PROJ_FOSSIL_FUEL_DISPATCH_POINTS,
            rule=lambda m, pr, tp, f: m.ProjFuelUseRate[pr, tp, f] == 0.0
        )


def binary_by_period_DispatchProjRenewableMW(m):
    # NOTE: this could be extended to handle fuel blends (e.g., 50% biomass/50% coal)
    # by assigning an RPS eligibility level to each fuel (e.g., 50%), then
    # setting binary variables for whether to use each fuel during each period
    # (possibly treated as an SOS; or might be able to have an SOS for total
    # amount to produce from each fuel during the period, and require that total
    # consumption of each fuel <= production from that fuel * max((consumption+startup)/output across operating points)
    # This could be further simplified by creating a set of eligibility levels,
    # and choosing the amount to produce from each eligibility level (similar to the
    # renewable/non-renewable distinction here, but with a 50% renewable category)
    
    m.PROJ_WITH_FUEL_ACTIVE_PERIODS = Set(dimen=2, initialize=lambda m: {
        (pr, pe) 
            for pr in m.FUEL_BASED_PROJECTS for pe in m.PERIODS
                if (pr, m.PERIOD_TPS[pe].first()) in m.PROJ_WITH_FUEL_DISPATCH_POINTS
    })
    
    # choose whether to run (only) on renewable fuels during each period
    m.DispatchRenewableFlag = Var(m.PROJ_WITH_FUEL_ACTIVE_PERIODS, within=Binary)
    
    # force flag on or off when the RPS is simple (to speed computation)
    m.Force_DispatchRenewableFlag = Constraint(
        m.PROJ_WITH_FUEL_ACTIVE_PERIODS, 
        rule=lambda m, pr, pe:
            (m.DispatchRenewableFlag[pr, pe] == 0) 
            if (m.rps_target_for_period[pe]==0.0 or m.options.rps_level != 'activate')
            else (
                (m.DispatchRenewableFlag[pr, pe] == 1) 
                if m.rps_target_for_period[pe]==1.0
                else Constraint.Skip
            )
    )
    
    # count amount of renewable power produced from project
    m.DispatchProjRenewableMW = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    
    # don't overcount renewable power production
    m.Limit_DispatchProjRenewableMW = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
            rule=lambda m, pr, tp: 
                m.DispatchProjRenewableMW[pr, tp] <= m.DispatchProj[pr, tp]
    )
    # force the flag to be set during renewable timepoints
    m.Set_DispatchRenewableFlag = Constraint(
            m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
            rule=lambda m, pr, tp:
                 m.DispatchProjRenewableMW[pr, tp] 
                 <= 
                 m.DispatchRenewableFlag[pr, m.tp_period[tp]] * m.proj_capacity_limit_mw[pr]
    )
    
    # prevent use of non-renewable fuels during renewable timepoints
    def Enforce_DispatchRenewableFlag_rule(m, pr, tp, f):
        if m.f_rps_eligible[f]:
            return Constraint.Skip
        else:
            # harder to read like this, but having all numerical values on the right hand side
            # facilitates analysis of duals and reduced costs
            # note: we also add a little slack to avoid having this be the main constraint
            # on total output from any power plant (that also clarifies dual analysis)
            big_fuel = 1.01 * m.proj_capacity_limit_mw[pr] * m.proj_full_load_heat_rate[pr]
            return (
                m.ProjFuelUseRate[pr, tp, f] 
                + m.DispatchRenewableFlag[pr, m.tp_period[tp]] * big_fuel
                <= 
                big_fuel
            )
    m.Enforce_DispatchRenewableFlag = Constraint(
        m.PROJ_FUEL_DISPATCH_POINTS, rule=Enforce_DispatchRenewableFlag_rule
    )

def binary_by_timeseries_DispatchProjRenewableMW(m):
    m.PROJ_WITH_FUEL_ACTIVE_TIMESERIES = Set(dimen=2, initialize=lambda m: {
        (pr, ts) 
            for pr in m.FUEL_BASED_PROJECTS for ts in m.TIMESERIES
                if (pr, m.TS_TPS[ts].first()) in m.PROJ_WITH_FUEL_DISPATCH_POINTS
    })
    
    # choose whether to run (only) on renewable fuels during each period
    m.DispatchRenewableFlag = Var(m.PROJ_WITH_FUEL_ACTIVE_TIMESERIES, within=Binary)
    
    # force flag on or off depending on RPS status (to speed computation)
    m.Force_DispatchRenewableFlag = Constraint(
        m.PROJ_WITH_FUEL_ACTIVE_TIMESERIES, 
        rule=lambda m, pr, ts:
            (m.DispatchRenewableFlag[pr, ts] == 0) if m.rps_target_for_period[m.ts_period[ts]]==0.0
            else (
                (m.DispatchRenewableFlag[pr, ts] == 1) if m.rps_target_for_period[m.ts_period[ts]]==1.0
                else Constraint.Skip
            )
    )
    
    # count amount of renewable power produced from project
    m.DispatchProjRenewableMW = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    
    # don't overcount renewable power production
    m.Limit_DispatchProjRenewableMW = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
            rule=lambda m, pr, tp: 
                m.DispatchProjRenewableMW[pr, tp] <= m.DispatchProj[pr, tp]
    )
    # force the flag to be set during renewable timepoints
    m.Set_DispatchRenewableFlag = Constraint(
            m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
            rule=lambda m, pr, tp:
                 m.DispatchProjRenewableMW[pr, tp] 
                 <= 
                 m.DispatchRenewableFlag[pr, m.tp_ts[tp]] * m.proj_capacity_limit_mw[pr]
    )
    
    # prevent use of non-renewable fuels during renewable timepoints
    m.Enforce_DispatchRenewableFlag = Constraint(
        m.PROJ_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp, f: 
            Constraint.Skip if m.f_rps_eligible[f]
            else (
                # original code, rewritten to get numerical parts on rhs
                # m.ProjFuelUseRate[pr, tp, f]
                # <=
                # (1-m.DispatchRenewableFlag[pr, m.tp_ts[tp]]) * m.proj_capacity_limit_mw[pr] * m.proj_full_load_heat_rate[pr]
                m.ProjFuelUseRate[pr, tp, f] 
                + m.DispatchRenewableFlag[pr, m.tp_ts[tp]] * m.proj_capacity_limit_mw[pr] * m.proj_full_load_heat_rate[pr]
                <= 
                m.proj_capacity_limit_mw[pr] * m.proj_full_load_heat_rate[pr]
            )
    )



def advanced2_DispatchProjRenewableMW(m):
    # choose whether to run (only) on renewable fuels during each timepoint
    m.DispatchRenewableFlag = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=Binary)
    
    # count amount of renewable power produced from project
    m.DispatchProjRenewableMW = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    
    # don't overcount renewable power production
    m.Limit_DispatchProjRenewableMW = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
            rule=lambda m, pr, tp: m.DispatchProjRenewableMW[pr, tp] <= m.DispatchProj[pr, tp]
    )
    # force the flag to be set during renewable timepoints
    m.Set_DispatchRenewableFlag = Constraint(
            m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
            rule=lambda m, pr, tp:
                 m.DispatchProjRenewableMW[pr, tp] 
                 <= 
                 m.DispatchRenewableFlag[pr, tp] * m.proj_capacity_limit_mw[pr]
    )
    
    # prevent use of non-renewable fuels during renewable timepoints
    m.Enforce_DispatchRenewableFlag = Constraint(
        m.PROJ_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp, f: 
            Constraint.Skip if m.f_rps_eligible[f]
            else (
                m.ProjFuelUseRate[pr, tp, f] 
                <= 
                (1-m.DispatchRenewableFlag[pr, tp]) * m.proj_capacity_limit_mw[pr] * m.proj_full_load_heat_rate[pr]
            )
    )


def advanced1_DispatchProjRenewableMW(m):
    # Allocate the power produced during each timepoint among the fuels.

    m.DispatchProjRenewableMW = Var(m.PROJ_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    # make sure this matches total production
    m.DispatchProjRenewableMW_Total = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp: 
            sum(m.DispatchProjRenewableMW[pr, tp, f] for f in m.PROJ_FUELS[pr])
            ==
            m.DispatchProj[pr, tp]
    )
    
    # choose a single fuel to use during each timestep
    m.DispatchFuelFlag = Var(m.PROJ_FUEL_DISPATCH_POINTS, within=Binary)
    m.DispatchFuelFlag_Total = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp: 
            sum(m.DispatchFuelFlag[pr, tp, f] for f in m.PROJ_FUELS[pr])
            ==
            1
    )

    # consume only the selected fuel and allocate all production to that fuel (big-M constraints)
    m.Allocate_Dispatch_Output = Constraint(
        m.PROJ_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp, f: 
            m.DispatchProjRenewableMW[pr, tp, f] 
            <= 
            m.DispatchFuelFlag[pr, tp, f] * m.proj_capacity_limit_mw[pr]
    )
    m.Allocate_Dispatch_Fuel = Constraint(
        m.PROJ_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp, f: 
            m.ProjFuelUseRate[pr, tp, f] 
            <= 
            m.DispatchFuelFlag[pr, tp, f] * m.proj_capacity_limit_mw[pr] * m.proj_full_load_heat_rate[pr]
    )
    
    # note: in cases where a project has a single fuel, the presolver should force  
    # DispatchProjRenewableMW for that fuel to match DispatchProj, and possibly
    # eliminate the allocation constraints
    
    # possible simplifications:
    # omit binary variables and big-m constraints if len(m.PROJ_FUELS[p]) == 1 
    #   (assign all production to the single fuel)
    # use m.ProjFuelUseRate[proj, t, f] / m.proj_full_load_heat_rate[proj]
    #    for projects with no heat rate curve and no startup fuel

    # note: a continuous, quadratic version of this function can be created as follows:
    # - make DispatchFuelFlag a PercentFraction instead of Binary
    # - replace proj_capacity_limit_mw with ProjCapacity in Allocate_Dispatch_Output
    # - replace m.proj_capacity_limit_mw * m.proj_full_load_heat_rate with 
    #   sum(m.ProjFuelUseRate[pr, t, f] for f in m.PROJ_FUELS[pr])
    #   in Allocate_Dispatch_Fuel (define this as an Expression in dispatch.py)
    # - replace <= with == in the allocation constraints
    # - drop the DispatchProjRenewableMW_Total constraint
    
    # or this would also work:
    # m.DispatchProjRenewableMW = Var(m.PROJ_FUEL_DISPATCH_POINTS)
    # m.DispatchProjRenewableMW_Allocate = Constraint(
    #     m.PROJ_FUEL_DISPATCH_POINTS,
    #     rule = lambda m, proj, t, f:
    #         m.DispatchProjRenewableMW[proj, t, f]
    #         * sum(m.ProjFuelUseRate[proj, t, _f] for _f in m.PROJ_FUELS[proj])
    #         ==
    #         DispatchProj[proj, t]
    #         * m.ProjFuelUseRate[proj, t, f]
    # )

def quadratic_DispatchProjRenewableMW(m):
    # choose how much power to obtain from renewables during each timepoint
    m.DispatchRenewableFraction = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=PercentFraction)
    
    # count amount of renewable power produced from project
    m.DispatchProjRenewableMW = Var(m.PROJ_WITH_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    
    # don't overcount renewable power production
    m.Set_DispatchRenewableFraction = Constraint(
            m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
            rule=lambda m, pr, tp:
                 m.DispatchProjRenewableMW[pr, tp] 
                 <= 
                 m.DispatchRenewableFraction[pr, tp] * m.DispatchProj[pr, tp]
    )
    m.Enforce_DispatchRenewableFraction = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp: 
            sum(
                m.ProjFuelUseRate[pr, tp, f] 
                    for f in m.PROJ_FUELS[pr] 
                        if m.f_rps_eligible[f]
            )
            >=
            m.DispatchRenewableFraction[pr, tp] *
            sum(
                m.ProjFuelUseRate[pr, tp, f] 
                    for f in m.PROJ_FUELS[pr]
            )
    )

def quadratic1_DispatchProjRenewableMW(m):
    # Allocate the power produced during each timepoint among the fuels.
    m.DispatchProjRenewableMW = Var(m.PROJ_FUEL_DISPATCH_POINTS, within=NonNegativeReals)

    # make sure this matches total production
    m.DispatchProjRenewableMW_Total = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp: 
            sum(m.DispatchProjRenewableMW[pr, tp, f] for f in m.PROJ_FUELS[pr])
            ==
            m.DispatchProj[pr, tp]
    )
    
    m.DispatchProjRenewableMW_Allocate = Constraint(
        m.PROJ_FUEL_DISPATCH_POINTS,
        rule = lambda m, proj, t, f:
            m.DispatchProjRenewableMW[proj, t, f]
            * sum(m.ProjFuelUseRate[proj, t, _f] for _f in m.PROJ_FUELS[proj])
            <=
            m.DispatchProj[proj, t]
            * m.ProjFuelUseRate[proj, t, f]
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

