import os
from pprint import pprint
from pyomo.environ import *
import switch_mod.utilities as utilities
from util import get

def define_arguments(argparser):
    argparser.add_argument('--biofuel-limit', type=float, default=0.05, 
        help="Maximum fraction of power that can be obtained from biofuel in any period (default=0.05)")
    
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
        latest_target = max(y for y in m.RPS_YEARS if y <= m.period_end[p])
        return m.rps_target[latest_target]
    m.rps_target_for_period = Param(m.PERIODS, initialize=rps_target_for_period_rule)

    # maximum share of (bio)fuels in rps
    # note: using Infinity as the upper limit causes the solution to take forever
    # m.rps_fuel_limit = Param(default=float("inf"), mutable=True)
    m.rps_fuel_limit = Param(initialize=m.options.biofuel_limit, mutable=True)

    # Note: this rule ignores pumped hydro, so it could be gamed by producing extra 
    # RPS-eligible power and burning it off in storage losses; on the other hand, 
    # it also neglects the (small) contribution from net flow of pumped hydro projects.
    # TODO: incorporate pumped hydro into this rule, maybe change the target to refer to 
    # sum(getattr(m, component)[lz, t] for lz in m.LOAD_ZONES) for component in m.LZ_Energy_Components_Produce)

    # power production that can be counted toward the RPS each period
    m.RPSEligiblePower = Expression(m.PERIODS, rule=lambda m, per:
        sum(
            m.DispatchProjByFuel[p, tp, f] * m.tp_weight[tp]
                for f in m.FUELS if f in m.RPS_ENERGY_SOURCES
                    for p in m.PROJECTS_BY_FUEL[f]
                        # could be accelerated a bit if we had m.ACTIVE_PERIODS_FOR_PROJECT[p]
                        for tp in m.PERIOD_TPS[per]
                            if (p, tp) in m.PROJ_DISPATCH_POINTS
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
    
    m.RPS_Enforce = Constraint(m.PERIODS, rule=lambda m, per:
        m.RPSEligiblePower[per] >= m.rps_target_for_period[per] * m.RPSTotalPower[per]
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
            m.DispatchProjByFuel[p, tp, f] * m.tp_weight[tp]
                for f in m.FUELS if m.f_rps_eligible[f]
                    for p in m.PROJECTS_BY_FUEL[f]
                        # could be accelerated a bit if we had m.ACTIVE_PERIODS_FOR_PROJECT[p]
                        for tp in m.PERIOD_TPS[per]
                            if (p, tp) in m.PROJ_DISPATCH_POINTS
        )
    )
    m.RPS_Fuel_Cap = Constraint(m.PERIODS, rule = lambda m, per:
        m.RPSFuelPower[per] <= m.rps_fuel_limit * m.RPSTotalPower[per]
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

