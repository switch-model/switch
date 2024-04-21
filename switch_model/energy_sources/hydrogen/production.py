from __future__ import division
import os
from pyomo.environ import *
from switch_model.financials import capital_recovery_factor as crf

"""
Produce hydrogen for use in power plants. This conservatively assumes that
all hydrogen must be used the same day or else liquefied and stored in a
tank. Further, we only consider one kind of tank (spheres similar to those
used for rockets) and assume tank capacity must be large enough to hold the
full year's withdrawals. (This avoids needing to track the sequence of
dates within the year.)

The hydrogen fuel ("Hydrogen" by default) must also be added to fuels.csv and
fuel_cost.csv or fuel_supply_curves.csv. It should usually be added with a zero
cost; if a non-zero cost is used, that will be treated as an extra cost per
MMBtu of hydrogen produced and used.

TODO: change the spinning reserves code to model the energy requirements
for providing up reserves (due to cycling occasionally above zero point),
to force construction of a suitable amount of hydrogen infrastructure and
avoid using hydrogen fuel cells for reserves without ever actually making
or storing any hydrogen. (For now, it is recommended to include a non-zero
value for gen_min_load_fraction for fuel cells, as a proxy for the duty cycle
while in up-reserve mode.)
"""


def define_arguments(argparser):
    argparser.add_argument(
        "--no-hydrogen",
        action="store_true",
        default=False,
        help="Don't allow use of any hydrogen (note: hydrogen-based generators may still be built or operated as reserves.).",
    )


def define_components(m):
    # name of the hydrogen fuel (will be constrained to come from the hydrogen
    # infrastructure; should be defined as a standard fuel with $0 cost)
    m.hydrogen_fuel_name = Param(default="Hydrogen", within=m.FUELS)

    # def Check_Hydrogen_Fuel_Exists_rule(m):
    #     if m.hydrogen_fuel_name not in m.FUELS: # doesn't work in Pyomo
    #         raise ValueError(
    #             f"Hydrogen not found in the fuels list. When using the {__name__} "
    #             f"module, hydrogen must be added to 'fuels.csv (as "
    #             f'"{m.hydrogen_fuel_name}") and to fuel_cost.csv '
    #             f"or fuel_supply_curves.csv (usually with a zero cost). "
    #             f"It should also be listed as a fuel for one or more "
    #             f"generators in gen_info.csv."
    #         )

    # m.Check_Hydrogen_Fuel_Exists = BuildAction(rule=Check_Hydrogen_Fuel_Exists_rule)

    # lower heating value, from PNNL, https://h2tools.org/hyarc/calculator-tools/lower-and-higher-heating-values-fuels
    # (we use LHV because that is what power plant heat rates are usually based
    # on: https://www.powermag.com/plant-efficiency-begin-with-the-right-definitions/)
    # Users could override this if using heat heat rates based on HHV (or quoted in MJ)
    m.hydrogen_mmbtu_per_kg = Param(within=NonNegativeReals, default=0.113745)

    # electrolyzer details
    m.hydrogen_electrolyzer_capital_cost_per_mw = Param(within=NonNegativeReals)
    m.hydrogen_electrolyzer_fixed_cost_per_mw_year = Param(
        within=NonNegativeReals, default=0.0
    )
    # assumed to include any refurbishment needed
    m.hydrogen_electrolyzer_variable_cost_per_kg = Param(
        within=NonNegativeReals, default=0.0
    )
    # assumed to deliver H2 at enough pressure for liquefier and daily buffering
    m.hydrogen_electrolyzer_kg_per_mwh = Param(within=NonNegativeReals)
    m.hydrogen_electrolyzer_life_years = Param(within=NonNegativeReals)
    m.BuildElectrolyzerMW = Var(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)
    m.ElectrolyzerCapacityMW = Expression(
        m.LOAD_ZONES,
        m.PERIODS,
        rule=lambda m, z, p: sum(
            m.BuildElectrolyzerMW[z, p_]
            for p_ in m.CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD[p]
        ),
    )
    m.RunElectrolyzerMW = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    m.ProduceHydrogenKgPerHour = Expression(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.RunElectrolyzerMW[z, t]
        * m.hydrogen_electrolyzer_kg_per_mwh,
    )

    # note: we assume there is a gaseous hydrogen storage tank that is big enough to buffer
    # daily production, storage and withdrawals of hydrogen, but we don't include a cost
    # for this (because it will be negligible compared to the rest of the costs)
    # This allows the system to do some intra-day arbitrage without going all the way to liquefaction

    # liquefier details
    m.hydrogen_liquefier_capital_cost_per_kg_per_hour = Param(within=NonNegativeReals)
    m.hydrogen_liquefier_fixed_cost_per_kg_hour_year = Param(
        within=NonNegativeReals, default=0.0
    )
    m.hydrogen_liquefier_variable_cost_per_kg = Param(
        within=NonNegativeReals, default=0.0
    )
    m.hydrogen_liquefier_mwh_per_kg = Param(within=NonNegativeReals)
    m.hydrogen_liquefier_life_years = Param(within=NonNegativeReals)
    m.BuildLiquefierKgPerHour = Var(
        m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals
    )  # capacity to build, measured in kg/hour of throughput
    m.LiquefierCapacityKgPerHour = Expression(
        m.LOAD_ZONES,
        m.PERIODS,
        rule=lambda m, z, p: sum(
            m.BuildLiquefierKgPerHour[z, p_]
            for p_ in m.CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD[p]
        ),
    )
    m.LiquefyHydrogenKgPerHour = Var(
        m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals
    )
    m.LiquefyHydrogenMW = Expression(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.LiquefyHydrogenKgPerHour[z, t]
        * m.hydrogen_liquefier_mwh_per_kg,
    )

    # storage tank details
    m.liquid_hydrogen_tank_capital_cost_per_kg = Param(within=NonNegativeReals)
    m.liquid_hydrogen_tank_minimum_size_kg = Param(within=NonNegativeReals, default=0.0)
    m.liquid_hydrogen_tank_life_years = Param(within=NonNegativeReals)
    m.BuildLiquidHydrogenTankKg = Var(
        m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals
    )  # in kg
    m.LiquidHydrogenTankCapacityKg = Expression(
        m.LOAD_ZONES,
        m.PERIODS,
        rule=lambda m, z, p: sum(
            m.BuildLiquidHydrogenTankKg[z, p_]
            for p_ in m.CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD[p]
        ),
    )
    m.StoreLiquidHydrogenKg = Expression(
        m.LOAD_ZONES,
        m.DATES,
        rule=lambda m, z, d: sum(
            m.ts_duration_of_tp[m.tp_ts[tp]] * m.LiquefyHydrogenKgPerHour[z, tp]
            for tp in m.TPS_IN_DATE[d]
        ),
    )
    m.WithdrawLiquidHydrogenKg = Var(m.LOAD_ZONES, m.DATES, within=NonNegativeReals)
    # note: we assume the system will be large enough to neglect boil-off

    ############
    # Calculate total use of hydrogen (hydrogen_fuel_name) in each zone during
    # each timepoint
    # first, identify all generators that can use hydrogen
    m.HYDROGEN_GENS = Set(
        initialize=m.FUEL_BASED_GENS,
        filter=lambda m, g: value(m.hydrogen_fuel_name) in m.FUELS_FOR_GEN[g],
    )

    # next, identify all the hydrogen generators that are active in each zone in each period
    def HYDROGEN_GENS_IN_ZONE_PERIOD_init(m, z, p):
        try:
            d = m.HYDROGEN_GENS_IN_ZONE_PERIOD_dict
        except AttributeError:
            d = m.HYDROGEN_GENS_IN_ZONE_PERIOD_dict = {
                (z2, p2): [] for z2 in m.LOAD_ZONES for p2 in m.PERIODS
            }
            # tabulate all hydrogen gens active in each zone in each period
            for g in m.HYDROGEN_GENS:
                for p2 in m.PERIODS_FOR_GEN[g]:
                    d[m.gen_load_zone[g], p2].append(g)
        return d.pop((z, p))

    m.HYDROGEN_GENS_IN_ZONE_PERIOD = Set(
        m.LOAD_ZONES,
        m.PERIODS,
        initialize=HYDROGEN_GENS_IN_ZONE_PERIOD_init,
        within=m.HYDROGEN_GENS,
    )

    # calculate fuel consumption by all hydrogen generators in each zone during
    # each timepoint and convert to kg
    m.ConsumeHydrogenKgPerHour = Expression(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, tp: (
            sum(
                m.GenFuelUseRate[g, tp, m.hydrogen_fuel_name]  # H2 MMBtu/hr
                for g in m.HYDROGEN_GENS_IN_ZONE_PERIOD[z, m.tp_period[tp]]
            )
            / m.hydrogen_mmbtu_per_kg
        ),
    )
    if m.options.no_hydrogen:
        m.Consume_No_Hydrogen = Constraint(
            m.LOAD_ZONES,
            m.TIMEPOINTS,
            rule=lambda m, z, tp: m.ConsumeHydrogenKgPerHour[z, tp] == 0,
        )

    ######################
    # hydrogen mass balances
    # note: this allows for buffering of same-day production and consumption
    # of hydrogen without ever liquefying it
    m.Hydrogen_Conservation_of_Mass_Daily = Constraint(
        m.LOAD_ZONES,
        m.DATES,
        rule=lambda m, z, d: (
            m.StoreLiquidHydrogenKg[z, d] - m.WithdrawLiquidHydrogenKg[z, d]
            == sum(
                m.ts_duration_of_tp[m.tp_ts[tp]]
                * (
                    m.ProduceHydrogenKgPerHour[z, tp]
                    - m.ConsumeHydrogenKgPerHour[z, tp]
                )
                for tp in m.TPS_IN_DATE[d]
            )
        ),
    )
    m.Hydrogen_Conservation_of_Mass_Annual = Constraint(
        m.LOAD_ZONES,
        m.PERIODS,
        rule=lambda m, z, p: sum(
            (m.StoreLiquidHydrogenKg[z, d] - m.WithdrawLiquidHydrogenKg[z, d])
            * m.ts_scale_to_year[ts]
            for ts in m.TS_IN_PERIOD[p]
            for d in m.DATES_IN_TS[ts]
        )
        == 0,
    )

    ##############
    # limits on equipment
    m.Max_Run_Electrolyzer = Constraint(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.RunElectrolyzerMW[z, t]
        <= m.ElectrolyzerCapacityMW[z, m.tp_period[t]],
    )
    m.Max_Run_Liquefier = Constraint(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.LiquefyHydrogenKgPerHour[z, t]
        <= m.LiquefierCapacityKgPerHour[z, m.tp_period[t]],
    )

    # Enforce minimum size for hydrogen tank if specified. We only define these
    # variables and constraints if needed, to avoid warnings about variables
    # with no values assigned.
    def action(m):
        if m.liquid_hydrogen_tank_minimum_size_kg != 0.0:
            m.BuildAnyLiquidHydrogenTank = Var(m.LOAD_ZONES, m.PERIODS, within=Binary)
            m.Set_BuildAnyLiquidHydrogenTank_Flag = Constraint(
                m.LOAD_ZONES,
                m.PERIODS,
                rule=lambda m, z, p: m.BuildLiquidHydrogenTankKg[z, p]
                <= 1000
                * m.BuildAnyLiquidHydrogenTank[z, p]
                * m.liquid_hydrogen_tank_minimum_size_kg,
            )
            m.Build_Minimum_Liquid_Hydrogen_Tank = Constraint(
                m.LOAD_ZONES,
                m.PERIODS,
                rule=lambda m, z, p: m.BuildLiquidHydrogenTankKg[z, p]
                >= m.BuildAnyLiquidHydrogenTank[z, p]
                * m.liquid_hydrogen_tank_minimum_size_kg,
            )

    m.Apply_liquid_hydrogen_tank_minimum_size = BuildAction(rule=action)

    # there must be enough storage to hold _all_ the production each period (net of same-day consumption)
    # note: this assumes we cycle the system only once per year (store all energy, then release all energy)
    # alternatives: allow monthly or seasonal cycling, or directly model the whole year with inter-day linkages
    m.Max_Store_Liquid_Hydrogen = Constraint(
        m.LOAD_ZONES,
        m.PERIODS,
        rule=lambda m, z, p: sum(
            m.StoreLiquidHydrogenKg[z, d] * m.ts_scale_to_year[ts]
            for ts in m.TS_IN_PERIOD[p]
            for d in m.DATES_IN_TS[ts]
        )
        <= m.LiquidHydrogenTankCapacityKg[z, p],
    )

    # add electricity consumption and production to the zonal energy balance
    m.Zone_Power_Withdrawals.append("RunElectrolyzerMW")
    m.Zone_Power_Withdrawals.append("LiquefyHydrogenMW")

    # add costs to the model
    m.HydrogenVariableCost = Expression(
        m.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.ProduceHydrogenKgPerHour[z, t]
            * m.hydrogen_electrolyzer_variable_cost_per_kg
            + m.LiquefyHydrogenKgPerHour[z, t]
            * m.hydrogen_liquefier_variable_cost_per_kg
            for z in m.LOAD_ZONES
        ),
    )
    m.HydrogenFixedCostAnnual = Expression(
        m.PERIODS,
        rule=lambda m, p: sum(
            m.ElectrolyzerCapacityMW[z, p]
            * (
                m.hydrogen_electrolyzer_capital_cost_per_mw
                * crf(m.interest_rate, m.hydrogen_electrolyzer_life_years)
                + m.hydrogen_electrolyzer_fixed_cost_per_mw_year
            )
            + m.LiquefierCapacityKgPerHour[z, p]
            * (
                m.hydrogen_liquefier_capital_cost_per_kg_per_hour
                * crf(m.interest_rate, m.hydrogen_liquefier_life_years)
                + m.hydrogen_liquefier_fixed_cost_per_kg_hour_year
            )
            + m.LiquidHydrogenTankCapacityKg[z, p]
            * (
                m.liquid_hydrogen_tank_capital_cost_per_kg
                * crf(m.interest_rate, m.liquid_hydrogen_tank_life_years)
            )
            for z in m.LOAD_ZONES
        ),
    )
    m.Cost_Components_Per_TP.append("HydrogenVariableCost")
    m.Cost_Components_Per_Period.append("HydrogenFixedCostAnnual")


def load_inputs(m, switch_data, inputs_dir):
    """
    Import hydrogen data from a .csv file.
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "hydrogen.csv"),
        param=(
            m.hydrogen_fuel_name,
            m.hydrogen_mmbtu_per_kg,
            m.hydrogen_electrolyzer_capital_cost_per_mw,
            m.hydrogen_electrolyzer_fixed_cost_per_mw_year,
            m.hydrogen_electrolyzer_kg_per_mwh,
            m.hydrogen_electrolyzer_life_years,
            m.hydrogen_electrolyzer_variable_cost_per_kg,
            m.hydrogen_liquefier_capital_cost_per_kg_per_hour,
            m.hydrogen_liquefier_fixed_cost_per_kg_hour_year,
            m.hydrogen_liquefier_life_years,
            m.hydrogen_liquefier_mwh_per_kg,
            m.hydrogen_liquefier_variable_cost_per_kg,
            m.liquid_hydrogen_tank_capital_cost_per_kg,
            m.liquid_hydrogen_tank_life_years,
            m.liquid_hydrogen_tank_minimum_size_kg,
        ),
    )
