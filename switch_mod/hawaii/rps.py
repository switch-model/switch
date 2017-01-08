import os
from pprint import pprint
from pyomo.environ import *
import switch_mod.utilities as utilities
from util import get

def define_arguments(argparser):
    argparser.add_argument('--biofuel-limit', type=float, default=0.05, 
        help="Maximum fraction of power that can be obtained from biofuel in any period (default=0.05)")
    argparser.add_argument('--rps-activate', default='activate',
        dest='rps_level', action='store_const', const='activate', 
        help="Activate RPS (on by default).")
    argparser.add_argument('--rps-deactivate', 
        dest='rps_level', action='store_const', const='deactivate', 
        help="Dectivate RPS.")
    argparser.add_argument('--rps-no-renewables', 
        dest='rps_level', action='store_const', const='no_renewables', 
        help="Dectivate RPS and don't allow any new renewables.")
    argparser.add_argument('--rps-quadratic-allocation', action='store_true', default=False, 
        help="Use quadratic formulation to allocate power output among fuels.")
    
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

    # Define DispatchProjByFuel, which shows the amount of power produced 
    # by each project from each fuel during each time step.
    define_DispatchProjByFuel(m)

    # Note: this rule ignores pumped hydro and batteries, so it could be gamed by producing extra 
    # RPS-eligible power and burning it off in storage losses; on the other hand, 
    # it also neglects the (small) contribution from net flow of pumped hydro projects.
    # TODO: incorporate pumped hydro into this rule, maybe change the target to refer to 
    # sum(getattr(m, component)[lz, t] for lz in m.LOAD_ZONES) for component in m.LZ_Energy_Components_Produce)

    # power production that can be counted toward the RPS each period
    m.RPSEligiblePower = Expression(m.PERIODS, rule=lambda m, per:
        # sum(
        #     m.DispatchProjByFuel[p, tp, f] * m.tp_weight[tp]
        #         for f in m.FUELS if f in m.RPS_ENERGY_SOURCES
        #             for p in m.PROJECTS_BY_FUEL[f]
        #                 # could be accelerated a bit if we had m.ACTIVE_PERIODS_FOR_PROJECT[p]
        #                 for tp in m.PERIOD_TPS[per]
        #                     if (p, tp) in m.PROJ_DISPATCH_POINTS
        # )
        sum(
            m.DispatchProjRenewableMW[p, tp] * m.tp_weight[tp] 
                for p, tp in m.PROJ_WITH_FUEL_DISPATCH_POINTS
        )
        +
        sum(
            m.DispatchProj[p, tp] * m.tp_weight[tp]
                for f in m.NON_FUEL_ENERGY_SOURCES if f in m.RPS_ENERGY_SOURCES
                    for p in m.PROJECTS_BY_NON_FUEL_ENERGY_SOURCE[f]
                        for tp in m.PERIOD_TPS[per]
                            if (p, tp) in m.PROJ_DISPATCH_POINTS
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
                for p in m.PROJECTS 
                    for tp in m.PERIOD_TPS[per] 
                        if (p, tp) in m.PROJ_DISPATCH_POINTS
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
            if m.g_energy_source[m.proj_gen_tech[proj]] in m.RPS_ENERGY_SOURCES else
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
    
    m.RPSFuelPower = Expression(m.PERIODS, rule=lambda m, per:
        sum(
        #     m.DispatchProjByFuel[p, tp, f] * m.tp_weight[tp]
        #         for f in m.FUELS if m.f_rps_eligible[f]
        #             for p in m.PROJECTS_BY_FUEL[f]
        #                 # could be accelerated a bit if we had m.ACTIVE_PERIODS_FOR_PROJECT[p]
        #                 for tp in m.PERIOD_TPS[per]
        #                     if (p, tp) in m.PROJ_DISPATCH_POINTS
            m.DispatchProjRenewableMW[p, tp] * m.tp_weight[tp] 
                for p, tp in m.PROJ_WITH_FUEL_DISPATCH_POINTS
        )
    )
    m.RPS_Fuel_Cap = Constraint(m.PERIODS, rule = lambda m, per:
        m.RPSFuelPower[per] <= m.rps_fuel_limit * m.RPSTotalPower[per]
    )


def define_DispatchProjByFuel(m):
    # Define DispatchProjByFuel, which shows the amount of power produced 
    # by each project from each fuel during each time step.
    # This must be linear, because it may be used in RPS calculations.
    # This can get complex when a project uses multiple fuels and incremental
    # heat rate curves. 
    if m.options.rps_quadratic_allocation:
        if m.options.verbose:
            print "Using quadratic formulation to allocate DispatchProjByFuel."
        quadratic_DispatchProjByFuel(m)
    elif hasattr(m, 'PROJ_FUEL_USE_SEGMENTS'):
        # using heat rate curves and possibly startup fuel; 
        # have to do more advanced allocation of power to fuels
        if m.options.verbose:
            print "Using binary variables to allocate DispatchProjByFuel"
        advanced_DispatchProjByFuel(m)
    else:
        # only using full load heat rate; use simpler allocation strategy
        if m.options.verbose:
            print "Using simple ratio to allocate DispatchProjByFuel"
        simple_DispatchProjByFuel(m)


def simple_DispatchProjByFuel(m):
    # Allocate the power produced during each timepoint among the fuels.
    # When not using heat rate curves, this can be calculated directly from
    # fuel usage and the full load heat rate. This also allows use of 
    # multiple fuels in the same project at the same time.
    m.DispatchProjRenewableMW = Expression(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS,
        rule=lambda m, proj, t:
            sum(
                m.ProjFuelUseRate[proj, t, f] 
                    for f in m.G_FUELS[m.proj_gen_tech[proj]]
                        if f in m.RPS_ENERGY_SOURCES
            )
            / m.proj_full_load_heat_rate[proj]
    )

def simple1_DispatchProjByFuel(m):
    # Allocate the power produced during each timepoint among the fuels.
    # When not using heat rate curves, this can be calculated directly from
    # fuel usage and the full load heat rate. This also allows use of 
    # multiple fuels in the same project at the same time.
    m.DispatchProjByFuel = Expression(
        m.PROJ_FUEL_DISPATCH_POINTS,
        rule=lambda m, proj, t, f:
            m.ProjFuelUseRate[proj, t, f] / m.proj_full_load_heat_rate[proj]
    )

def advanced_DispatchProjByFuel(m):
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
        if f in m.RPS_ENERGY_SOURCES:
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

def advanced_by_timeseries_DispatchProjByFuel(m):
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
            Constraint.Skip if f in m.RPS_ENERGY_SOURCES
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



def advanced2_DispatchProjByFuel(m):
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
            Constraint.Skip if f in m.RPS_ENERGY_SOURCES
            else (
                m.ProjFuelUseRate[pr, tp, f] 
                <= 
                (1-m.DispatchRenewableFlag[pr, tp]) * m.proj_capacity_limit_mw[pr] * m.proj_full_load_heat_rate[pr]
            )
    )


def advanced1_DispatchProjByFuel(m):
    # Allocate the power produced during each timepoint among the fuels.

    m.DispatchProjByFuel = Var(m.PROJ_FUEL_DISPATCH_POINTS, within=NonNegativeReals)
    # make sure this matches total production
    m.DispatchProjByFuel_Total = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp: 
            sum(m.DispatchProjByFuel[pr, tp, f] for f in m.G_FUELS[m.proj_gen_tech[pr]])
            ==
            m.DispatchProj[pr, tp]
    )
    
    # choose a single fuel to use during each timestep
    m.DispatchFuelFlag = Var(m.PROJ_FUEL_DISPATCH_POINTS, within=Binary)
    m.DispatchFuelFlag_Total = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp: 
            sum(m.DispatchFuelFlag[pr, tp, f] for f in m.G_FUELS[m.proj_gen_tech[pr]])
            ==
            1
    )

    # consume only the selected fuel and allocate all production to that fuel (big-M constraints)
    m.Allocate_Dispatch_Output = Constraint(
        m.PROJ_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp, f: 
            m.DispatchProjByFuel[pr, tp, f] 
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
    # DispatchProjByFuel for that fuel to match DispatchProj, and possibly
    # eliminate the allocation constraints
    
    # possible simplifications:
    # omit binary variables and big-m constraints if len(m.G_FUELS[m.proj_gen_tech[p]]) == 1 
    #   (assign all production to the single fuel)
    # use m.ProjFuelUseRate[proj, t, f] / m.proj_full_load_heat_rate[proj]
    #    for projects with no heat rate curve and no startup fuel

    # note: a continuous, quadratic version of this function can be created as follows:
    # - make DispatchFuelFlag a PercentFraction instead of Binary
    # - replace proj_capacity_limit_mw with ProjCapacity in Allocate_Dispatch_Output
    # - replace m.proj_capacity_limit_mw * m.proj_full_load_heat_rate with 
    #   sum(m.ProjFuelUseRate[pr, t, f] for f in m.G_FUELS[m.proj_gen_tech[pr]])
    #   in Allocate_Dispatch_Fuel (define this as an Expression in dispatch.py)
    # - replace <= with == in the allocation constraints
    # - drop the DispatchProjByFuel_Total constraint
    
    # or this would also work:
    # m.DispatchProjByFuel = Var(m.PROJ_FUEL_DISPATCH_POINTS)
    # m.DispatchProjByFuel_Allocate = Constraint(
    #     m.PROJ_FUEL_DISPATCH_POINTS,
    #     rule = lambda m, proj, t, f:
    #         m.DispatchProjByFuel[proj, t, f]
    #         * sum(m.ProjFuelUseRate[proj, t, _f] for _f in m.G_FUELS[m.proj_gen_tech[proj]])
    #         ==
    #         DispatchProj[proj, t]
    #         * m.ProjFuelUseRate[proj, t, f]
    # )

def quadratic_DispatchProjByFuel(m):
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
                    for f in m.G_FUELS[m.proj_gen_tech[pr]] 
                        if f in m.RPS_ENERGY_SOURCES
            )
            >=
            m.DispatchRenewableFraction[pr, tp] *
            sum(
                m.ProjFuelUseRate[pr, tp, f] 
                    for f in m.G_FUELS[m.proj_gen_tech[pr]]
            )
    )

def quadratic1_DispatchProjByFuel(m):
    # Allocate the power produced during each timepoint among the fuels.
    m.DispatchProjByFuel = Var(m.PROJ_FUEL_DISPATCH_POINTS, within=NonNegativeReals)

    # make sure this matches total production
    m.DispatchProjByFuel_Total = Constraint(
        m.PROJ_WITH_FUEL_DISPATCH_POINTS, 
        rule=lambda m, pr, tp: 
            sum(m.DispatchProjByFuel[pr, tp, f] for f in m.G_FUELS[m.proj_gen_tech[pr]])
            ==
            m.DispatchProj[pr, tp]
    )
    
    m.DispatchProjByFuel_Allocate = Constraint(
        m.PROJ_FUEL_DISPATCH_POINTS,
        rule = lambda m, proj, t, f:
            m.DispatchProjByFuel[proj, t, f]
            * sum(m.ProjFuelUseRate[proj, t, _f] for _f in m.G_FUELS[m.proj_gen_tech[proj]])
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

