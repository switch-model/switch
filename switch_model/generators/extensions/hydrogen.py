from __future__ import division
import os
from pyomo.environ import *
from switch_model.financials import capital_recovery_factor as crf
from switch_model.reporting import write_table
from switch_model.tools.graph import graph
import pandas as pd


def define_arguments(argparser):
    argparser.add_argument(
        "--hydrogen-reserve-types",
        nargs="+",
        default=["spinning"],
        help="Type(s) of reserves to provide from hydrogen infrastructure (e.g., 'contingency regulation'). "
        "Specify 'none' to disable.",
    )
    argparser.add_argument(
        "--no-hydrogen",
        action="store_true",
        default=False,
        help="Don't allow construction of any hydrogen infrastructure.",
    )


def define_components(m):
    if not m.options.no_hydrogen:
        define_hydrogen_components(m)


def define_hydrogen_components(m):
    """Simplified hydrogen model with electrolyzer, liquefier, storage, and fuel cell

    This module allows the model to build hyrogen storage capacity at each of the load zones.

    There are four mandatory input files to use with the hydrogen module:
    hydrogen_timepoints.csv, hydrogen_timeseries.csv, hydrogen_periods.csv, and
    hydrogen.csv (a list of single-value parameters).

    Users can use the hydrogen_timepoints.csv, hydrogen_timeseries.csv and
    hydrogen_periods.csv files to customize the hydrogen storage duration and cycle.

    ------------------------------------------
    hydrogen_timepoints.csv:
    The hydrogen_timepoints.csv input file must include all the timepoint_ids in the
    switch timepoints.csv input file. The hydrogen_timeseries column contains the new
    timeseries names that correspond to the maximum frequency at which hydrogen will
    be stored or withdrawn from liquid storage. For example, if hydrogen can be stored
    daily (but not hourly) to the tank, timepoints would be grouped into daily time
    series regardless of how long the main time series are in the switch timeseries.csv
    input file. The only requirement is that the hydrogen timeseries (hgts) must be
    equal to or of a longer duration than the timepoints it includes.
    hydrogen_timepoints.csv
        timepoint_id, hydrogen_timeseries

    ------------------------------------------
    hydrogen_timeseries.csv:
    The hydrogen_timeseries.csv input file allows users to further describe the hydrogen timeseries
    defined in hydrogen_timepoints.csv and specify a new HYDROGEN PERIOD (hgp) that corresponds to how
    often hydrogen storage is cycled. For example, if hydrogen should not be stored for longer than 1
    month, then each hgp would represent a one month period. Hydrogen storage is constrained to have
    zero net hydrogen stored from one hgp to the next hgp (H2 at hgp start - H2 at hgp end = 0).
    The hydrogen_timseries.csv input file must include the following:
        HYDROGEN_TIMESERIES: the exact same hydrogen timeseries names defined in hydrogen_timepoints.csv
        hgts_period: the PERIOD (from the switch timeseries.csv input file) containing the hydrogen timeseries in col 1
        hgts_hydrogen_period: the NEW HYDROGEN PERIOD containing the hydrogen timeseries in col 1
        hgts_duration_of_tp: the duration in hours of the timepoints in the hgts in col 1. Must match the
        ts_duration_of_tp for the corresponding timeseries in switch
        hgts_scale_to_hgp: the number of times that the hgts in col 1 occurs in the hgp
    The file format is as follows.
    hydrogen_timeseries.csv
        HYDROGEN_TIMESERIES,hgts_period,hgts_hydrogen_period,hgts_duration_of_tp,ts_duration_of_tp,
        hgts_scale_to_hgp

    ------------------------------------------
    hydrogen_periods.csv:
    The hydrogen_periods.csv input file maps hydrogen periods to the switch model periods.
    It must include the following:
    hydrogen_periods.csv
        hydrogen_period, period
    where hydrogen_period exactly matches the hgp in hydrogen_timeseries.csv and period exactly matches
    the periods in periods.csv.
    """

    # HYDROGEN TIMESCALES DETAILS
    m.tp_to_hgts = Param(
        m.TIMEPOINTS,
        input_file="hydrogen_timepoints.csv",
        input_column="hydrogen_timeseries",
        default=lambda m, tp: m.tp_ts[
            tp
        ],  # default is to use the main model time series
        doc="Mapping of timepoints to a hydrogen timeseries.",
        within=Any,
    )
    m.HGTS = Set(
        dimen=1,
        ordered=False,
        initialize=lambda m: set(m.tp_to_hgts[tp] for tp in m.TIMEPOINTS),
        doc="Set of hydrogen timeseries that correspond to max storage frequency as defined in the mapping.",
    )

    m.hgts_period = Param(
        m.HGTS,
        input_file="hydrogen_timeseries.csv",
        input_column="hgts_period",
        doc="Mapping of hydrogen time series to the main model periods.",
        within=m.PERIODS,
    )
    m.hgts_hg_period = Param(
        m.HGTS,
        input_file="hydrogen_timeseries.csv",
        input_column="hgts_hydrogen_period",
        doc="Mapping of hydrogen time series to the hydrogen periods.",
        within=Any,
    )
    m.HGP = Set(
        dimen=1,
        ordered=False,
        initialize=lambda m: set(m.hgts_hg_period[hgts] for hgts in m.HGTS),
        doc="Set of hydrogen periods that correspond to the storage cycling period.",
    )
    m.TPS_IN_HGTS = Set(
        m.HGTS,
        within=m.TIMEPOINTS,
        ordered=False,
        initialize=lambda m, hgts: set(
            t for t in m.TIMEPOINTS if m.tp_to_hgts[t] == hgts
        ),
        doc="Set of timepoints in each hydrogen timeseries.",
    )
    m.HGTS_IN_HGP = Set(
        m.HGP,
        within=m.HGTS,
        ordered=False,
        initialize=lambda m, hgp: set(
            hgts for hgts in m.HGTS if m.hgts_hg_period[hgts] == hgp
        ),
        doc="Set of hydrogen time series in each hydrogen period.",
    )
    m.HGTS_IN_PERIOD = Set(
        m.PERIODS,
        within=m.HGTS,
        ordered=False,
        initialize=lambda m, p: set(
            hgts for hgts in m.HGTS if m.hgts_period[hgts] == p
        ),
        doc="Set of hydrogen time series in each main model period.",
    )

    m.hgts_duration_of_tp = Param(
        m.HGTS,
        within=PositiveReals,
        input_file="hydrogen_timeseries.csv",
        input_column="hgts_duration_of_tp",
        doc="Duration in hours of the timepoints in each hydrogen time series",
    )
    m.hgts_scale_to_hgp = Param(
        m.HGTS,
        within=PositiveReals,
        input_file="hydrogen_timeseries.csv",
        input_column="hgts_scale_to_hgp",
        doc="Number of times a hydrogen time series occurs in its hydrogen period",
    )
    m.hgp_p = Param(
        m.HGP,
        within=m.PERIODS,
        input_file="hydrogen_periods.csv",
        input_column="period",
        doc="Mapping of hydrogen periods to normal model periods.",
    )

    # ELECTROLYZER DETAILS
    m.hydrogen_electrolyzer_variable_cost_per_kg = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_electrolyzer_variable_cost_per_kg",
        within=NonNegativeReals,
        default=0,
        doc="Variable cost per period in $/kg",
    )  # assumed to include any refurbishment needed

    m.hydrogen_electrolyzer_kg_per_mwh = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_electrolyzer_kg_per_mwh",
        within=NonNegativeReals,
        default=30,
    )  # assumed to deliver H2 at enough pressure for liquifier and daily buffering
    m.hydrogen_electrolyzer_life_years = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_electrolyzer_life_years",
        within=NonNegativeReals,
        default=20,
    )
    # Hydrogen electrolyzer capital cost per mw
    m.hydrogen_electrolyzer_capital_cost_per_mw = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_electrolyzer_capital_cost_per_mw",
        within=NonNegativeReals,
        default=0,
    )
    # Hydrogen electrolyzer capital cost learning curve Cost
    # m.hydrogen_electrolyzer_capital_cost_per_mw = Param(
    #    m.PERIODS,
    #    input_file="hydrogen_flexible.csv",
    #    input_column="hydrogen_electrolyzer_capital_cost_per_mw",
    #    within=NonNegativeReals,
    #    default=0,
    # )
    # Hydrogen sell price vary by Period
    # m.hydrogen_sell_price = Param(
    #    m.PERIODS,
    #    input_file="hydrogen_flexible.csv",
    #    input_column="hydrogen_sell_price",
    #    within=NonNegativeReals,
    #    default=1,
    # )
    # Hydrogen fixed cost vary by period
    m.hydrogen_electrolyzer_fixed_cost_per_mw_year = Param(
        # m.PERIODS,
        # input_file="hydrogen_flexible.csv",
        input_file="hydrogen.csv",  # no longer indexing by period
        input_column="hydrogen_electrolyzer_fixed_cost_per_mw_year",
        within=NonNegativeReals,
        default=0,
    )
    # m.hydrogen_sell_price = Param(default=2,input_file='hydrogen.csv')
    m.BuildElectrolyzerMW = Var(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)
    # what is the constraint bounding this "buildelectrolyzerMW" variable? it is constrained below
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
    # This allows the system to do some intra-day arbitrage without going all the way to liquification

    # LIQUIFIER DETAILS
    m.hydrogen_liquifier_capital_cost_per_kg_per_hour = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_liquifier_capital_cost_per_kg_per_hour",
        within=NonNegativeReals,
        default=0,
    )

    m.hydrogen_liquifier_fixed_cost_per_kg_hour_year = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_liquifier_fixed_cost_per_kg_hour_year",
        within=NonNegativeReals,
        default=0,
    )

    m.hydrogen_liquifier_variable_cost_per_kg = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_liquifier_variable_cost_per_kg",
        within=NonNegativeReals,
        default=0,
    )

    m.hydrogen_liquifier_mwh_per_kg = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_liquifier_mwh_per_kg",
        within=NonNegativeReals,
        default=0.005,
    )

    m.hydrogen_liquifier_life_years = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_liquifier_life_years",
        within=NonNegativeReals,
        default=20,
    )

    m.BuildLiquifierKgPerHour = Var(
        m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals
    )  # capacity to build, measured in kg/hour of throughput
    m.LiquifierCapacityKgPerHour = Expression(
        m.LOAD_ZONES,
        m.PERIODS,
        rule=lambda m, z, p: sum(
            m.BuildLiquifierKgPerHour[z, p_]
            for p_ in m.CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD[p]
        ),
    )
    m.LiquifyHydrogenKgPerHour = Var(
        m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals
    )
    m.LiquifyHydrogenMW = Expression(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.LiquifyHydrogenKgPerHour[z, t]
        * m.hydrogen_liquifier_mwh_per_kg,
    )

    # STORAGE TANK DETAILS
    m.liquid_hydrogen_tank_capital_cost_per_kg = Param(
        input_file="hydrogen.csv",
        input_column="liquid_hydrogen_tank_capital_cost_per_kg",
        within=NonNegativeReals,
        default=0,
    )

    # m.liquid_hydrogen_tank_minimum_size_kg = Param(
    #    input_file="hydrogen.csv"
    #    input_column="liquid_hydrogen_tank_minimum_size_kg"
    #    within=NonNegativeReals,
    #    default=0,
    # )

    # Now model liquid_hydrogen_tank_minimum_size_kg as a constant (zero), not a param
    m.liquid_hydrogen_tank_minimum_size_kg = Param(
        initialize=0.0,
    )
    # Added in maximum tank size parameter to constrain the tank capacity.
    m.liquid_hydrogen_tank_maximum_size_kg = Param(
        input_file="hydrogen.csv",
        input_column="liquid_hydrogen_tank_maximum_size_kg",
        within=NonNegativeReals,
        default=5000,
    )

    m.liquid_hydrogen_tank_life_years = Param(
        input_file="hydrogen.csv",
        input_column="liquid_hydrogen_tank_life_years",
        within=NonNegativeReals,
        default=20,
    )

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
        m.HGTS,
        rule=lambda m, z, hgts: m.hgts_duration_of_tp[hgts]
        * sum(m.LiquifyHydrogenKgPerHour[z, tp] for tp in m.TPS_IN_HGTS[hgts]),
    )
    m.WithdrawLiquidHydrogenKg = Var(m.LOAD_ZONES, m.HGTS, within=NonNegativeReals)
    # note: we assume the system will be large enough to neglect boil-off

    # FUEL CELL DETAILS
    m.hydrogen_fuel_cell_capital_cost_per_mw = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_fuel_cell_capital_cost_per_mw",
        within=NonNegativeReals,
        default=0,
    )
    m.hydrogen_fuel_cell_fixed_cost_per_mw_year = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_fuel_cell_fixed_cost_per_mw_year",
        within=NonNegativeReals,
        default=0,
    )
    m.hydrogen_fuel_cell_variable_cost_per_mwh = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_fuel_cell_variable_cost_per_mwh",
        within=NonNegativeReals,
        default=0,
    )
    m.hydrogen_fuel_cell_mwh_per_kg = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_fuel_cell_mwh_per_kg",
        within=NonNegativeReals,
        default=0.02,
    )
    m.hydrogen_fuel_cell_life_years = Param(
        input_file="hydrogen.csv",
        input_column="hydrogen_fuel_cell_life_years",
        within=NonNegativeReals,
        default=20,
    )

    m.BuildFuelCellMW = Var(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)
    m.FuelCellCapacityMW = Expression(
        m.LOAD_ZONES,
        m.PERIODS,
        rule=lambda m, z, p: sum(
            m.BuildFuelCellMW[z, p_] for p_ in m.CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD[p]
        ),
    )
    m.DispatchFuelCellMW = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    m.ConsumeHydrogenKgPerHour = Expression(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.DispatchFuelCellMW[z, t]
        / m.hydrogen_fuel_cell_mwh_per_kg,
    )

    # Constraints - Hydrogen Mass Balances
    # note: this allows for buffering of same-day production and consumption
    # of hydrogen without ever liquifying it
    m.Hydrogen_Conservation_of_Mass_Daily = Constraint(
        m.LOAD_ZONES,
        m.HGTS,
        rule=lambda m, z, hgts: m.StoreLiquidHydrogenKg[z, hgts]
        - m.WithdrawLiquidHydrogenKg[z, hgts]
        == m.hgts_duration_of_tp[hgts]
        * sum(
            m.ProduceHydrogenKgPerHour[z, tp] - m.ConsumeHydrogenKgPerHour[z, tp]
            for tp in m.TPS_IN_HGTS[hgts]
        ),
    )
    m.Hydrogen_Conservation_of_Mass_Annual = Constraint(
        m.LOAD_ZONES,
        m.HGP,
        rule=lambda m, z, hgp: sum(
            (m.StoreLiquidHydrogenKg[z, hgts] - m.WithdrawLiquidHydrogenKg[z, hgts])
            * m.hgts_scale_to_hgp[hgts]
            for hgts in m.HGTS_IN_HGP[hgp]
        )
        == 0,
    )

    # Constraints - limits on equipment
    m.Max_Run_Electrolyzer = Constraint(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.RunElectrolyzerMW[z, t]
        <= m.ElectrolyzerCapacityMW[z, m.tp_period[t]],
    )
    m.Max_Run_Fuel_Cell = Constraint(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.DispatchFuelCellMW[z, t]
        <= m.FuelCellCapacityMW[z, m.tp_period[t]],
    )
    m.Max_Run_Liquifier = Constraint(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.LiquifyHydrogenKgPerHour[z, t]
        <= m.LiquifierCapacityKgPerHour[z, m.tp_period[t]],
    )
    # size constrants for hydrogen tank - removed to no longer use binary variable
    # m.BuildAnyLiquidHydrogenTank = Var(m.LOAD_ZONES, m.PERIODS, within=Binary)
    # m.Set_BuildAnyLiquidHydrogenTank_Flag = Constraint(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
    #    Constraint.Skip if m.liquid_hydrogen_tank_minimum_size_kg == 0.0
    #    else (
    #        m.BuildLiquidHydrogenTankKg[z, p]
    #        <=
    #        1000 * m.BuildAnyLiquidHydrogenTank[z, p] * m.liquid_hydrogen_tank_minimum_size_kg
    #    )
    # )
    # m.Build_Minimum_Liquid_Hydrogen_Tank = Constraint(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
    #    Constraint.Skip if m.liquid_hydrogen_tank_minimum_size_kg == 0.0
    #    else (
    #        m.BuildLiquidHydrogenTankKg[z, p]
    #        >=
    #        m.BuildAnyLiquidHydrogenTank[z, p] * m.liquid_hydrogen_tank_minimum_size_kg
    #    )
    # )
    # New constraint to limit maximum tank size (can remove if not needed)
    m.Build_Maximum_Liquid_Hydrogen_Tank = Constraint(
        m.LOAD_ZONES,
        m.PERIODS,
        rule=lambda m, z, p: m.BuildLiquidHydrogenTankKg[z, p]
        <= m.liquid_hydrogen_tank_maximum_size_kg,
    )

    # there must be enough storage to hold _all_ the production each period (net of same-day consumption)
    # note: this assumes we cycle the system only once per year (store all energy, then release all energy)
    # alternatives: allow monthly or seasonal cycling, or directly model the whole year with inter-day linkages
    m.Max_Store_Liquid_Hydrogen = Constraint(
        m.LOAD_ZONES,
        m.HGP,
        rule=lambda m, z, hgp: sum(
            m.StoreLiquidHydrogenKg[z, hgts] * m.hgts_scale_to_hgp[hgts]
            for hgts in m.HGTS_IN_HGP[hgp]
        )
        <= m.LiquidHydrogenTankCapacityKg[z, m.hgp_p[hgp]],
    )

    # RESERVES - VARIABLES AND CONSTRAINTS
    # maximum amount that hydrogen fuel cells can contribute to system reserves
    # Note: we assume we can't use fuel cells for reserves unless we've also built at least half
    # as much electrolyzer capacity and a tank that can provide the reserves for 12 hours
    # (this is pretty arbitrary, but avoids just installing a fuel cell as a "free" source of reserves)
    m.HydrogenFuelCellMaxReservePower = Var(m.LOAD_ZONES, m.TIMEPOINTS)
    m.Hydrogen_FC_Reserve_Capacity_Limit = Constraint(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.HydrogenFuelCellMaxReservePower[z, t]
        <= m.FuelCellCapacityMW[z, m.tp_period[t]],
    )
    m.Hydrogen_FC_Reserve_Storage_Limit = Constraint(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.HydrogenFuelCellMaxReservePower[z, t]
        <= m.LiquidHydrogenTankCapacityKg[z, m.tp_period[t]]
        * m.hydrogen_fuel_cell_mwh_per_kg
        / 12.0,
    )
    m.Hydrogen_FC_Reserve_Electrolyzer_Limit = Constraint(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.HydrogenFuelCellMaxReservePower[z, t]
        <= 2.0 * m.ElectrolyzerCapacityMW[z, m.tp_period[t]],
    )
    # how much extra power could hydrogen equipment produce or absorb on short notice (for reserves)
    m.HydrogenSlackUp = Expression(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.RunElectrolyzerMW[z, t]
        + m.LiquifyHydrogenMW[z, t]
        + m.HydrogenFuelCellMaxReservePower[z, t]
        - m.DispatchFuelCellMW[z, t],
    )
    m.HydrogenSlackDown = Expression(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, t: m.ElectrolyzerCapacityMW[z, m.tp_period[t]]
        - m.RunElectrolyzerMW[z, t]
        # ignore liquifier potential since it's small and this is a low-value reserve product
        + m.DispatchFuelCellMW[z, t],
    )

    # Update dynamic lists

    # add electricity consumption and production to the zonal energy balance
    m.Zone_Power_Withdrawals.append("RunElectrolyzerMW")
    m.Zone_Power_Withdrawals.append("LiquifyHydrogenMW")
    m.Zone_Power_Injections.append("DispatchFuelCellMW")

    # add costs to the model
    m.HydrogenVariableCost = Expression(
        m.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.ProduceHydrogenKgPerHour[z, t]
            * m.hydrogen_electrolyzer_variable_cost_per_kg
            + m.LiquifyHydrogenKgPerHour[z, t]
            * m.hydrogen_liquifier_variable_cost_per_kg
            + m.DispatchFuelCellMW[z, t] * m.hydrogen_fuel_cell_variable_cost_per_mwh
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
            + m.LiquifierCapacityKgPerHour[z, p]
            * (
                m.hydrogen_liquifier_capital_cost_per_kg_per_hour
                * crf(m.interest_rate, m.hydrogen_liquifier_life_years)
                + m.hydrogen_liquifier_fixed_cost_per_kg_hour_year
            )
            + m.LiquidHydrogenTankCapacityKg[z, p]
            * (
                m.liquid_hydrogen_tank_capital_cost_per_kg
                * crf(m.interest_rate, m.liquid_hydrogen_tank_life_years)
            )
            + m.FuelCellCapacityMW[z, p]
            * (
                m.hydrogen_fuel_cell_capital_cost_per_mw
                * crf(m.interest_rate, m.hydrogen_fuel_cell_life_years)
                + m.hydrogen_fuel_cell_fixed_cost_per_mw_year
            )
            for z in m.LOAD_ZONES
        ),
    )

    # We need to know how much it costs to sell the hydrogen as an expression of the price.
    # m.HydrogenSelling = Expression(
    #    m.TIMEPOINTS,
    #    rule=lambda m, t: sum(
    #        # m.ProduceHydrogenKgPerHour[z, t] * m.hydrogenprofit
    #        m.hydrogen_sell_price[m.tp_period[t]] * m.ProduceHydrogenKgPerHour[z, t]
    #        for z in m.LOAD_ZONES
    #    ),
    #    doc="Hydrogen sell per time point for all the load zones ($)",
    # )

    # Creating hydrogen profit m. which is a function of how much we sell and the price which is a constraint given - total costs
    # m.HydrogenProfit = Expression(
    #    m.TIMEPOINTS,
    #    rule=lambda m, t: (-m.HydrogenSelling[t] + m.HydrogenVariableCost[t]),
    # )

    # #This is a new function that combines hydrogne selling and hydrogen variable costs
    # m.Netvariablecostsell = Expression(m.TIMEPOINTS, rule=lambda m, t:
    #     sum(m.HydrogenVariableCost[t]) - sum(m.Hydrogenselling[t])
    #     )
    # New fixed costs defined above
    # m.HydrogenFixedCostAnnual = Expression(
    #    m.PERIODS,
    #    rule=lambda m, p: sum(
    #        m.ElectrolyzerCapacityMW[z, p]
    #        * (
    #            m.hydrogen_electrolyzer_capital_cost_per_mw[p]
    #            * crf(m.interest_rate, m.hydrogen_electrolyzer_life_years)
    #            + m.hydrogen_electrolyzer_fixed_cost_per_mw_year[p]
    #        )
    #        for z in m.LOAD_ZONES
    #    ),
    # )
    m.Cost_Components_Per_TP.append("HydrogenVariableCost")
    # m.Cost_Components_Per_TP.append('Netvariablecostsell')
    # m.Cost_Components_Per_TP.append("HydrogenProfit")
    m.Cost_Components_Per_Period.append("HydrogenFixedCostAnnual")

    # Define additional expressions as needed to include in outputs:

    # Hydrogen income per PERIODS
    # m.hydrogen_income_per_period = Expression(
    #    m.PERIODS,
    #    rule=lambda m, p: m.hydrogen_sell_price[p]
    #    * sum(
    #        sum(m.ProduceHydrogenKgPerHour[z, t] for t in m.TPS_IN_PERIOD[p])
    #        for z in m.LOAD_ZONES
    #    ),
    #    doc="Hydrogen Income per Period ($/period)",
    # )
    # Hydrogen generation cost per period ($/y)
    m.hydrogen_generation_cost_per_period = Expression(
        m.PERIODS,
        rule=lambda m, p: m.hydrogen_electrolyzer_variable_cost_per_kg
        * sum(
            sum(m.ProduceHydrogenKgPerHour[z, t] for t in m.TPS_IN_PERIOD[p])
            for z in m.LOAD_ZONES
        ),
        doc="Hydrogen generation cost per Period ($/y)",
    )
    # Hydrogen generation per Period
    m.HydrogenGeneration = Expression(
        m.PERIODS,
        rule=lambda m, p: sum(
            sum(m.ProduceHydrogenKgPerHour[z, t] for t in m.TPS_IN_PERIOD[p])
            for z in m.LOAD_ZONES
        ),
    )

    # Hydrogen profit per Period
    # m.hydrogen_profit_per_period = Expression(
    #    m.PERIODS,
    #    rule=lambda m, p: sum(m.HydrogenProfit[t] for t in m.TPS_IN_PERIOD[p]),
    #    doc="Hydrogen Profit per Period ($/y)",
    # )
    # Electrolyzer capacity MW per Period... not correct, needs fixing
    m.electrolyzer_capacity_per_period = Expression(
        m.PERIODS,
        rule=lambda m, p: sum(m.ElectrolyzerCapacityMW[z, p] for z in m.LOAD_ZONES),
        doc="Electrolyzer Capacity per Period MW",
    )
    # Electrolyzer use per Period
    m.electrolyzer_use_per_period = Expression(
        m.PERIODS,
        rule=lambda m, p: sum(
            sum(m.RunElectrolyzerMW[z, t] for t in m.TPS_IN_PERIOD[p])
            for z in m.LOAD_ZONES
        ),
        doc="Electrolyzer use per Period",
    )


def post_solve(m, outdir):
    df = pd.DataFrame(
        {
            "period": p,
            "load_zone": z,
            "build_electrolyzer_MW": value(m.BuildElectrolyzerMW[z, p]),
            "total_capacity_electrolyzer_MW": value(m.ElectrolyzerCapacityMW[z, p]),
            "build_liquifier_kg_hour": value(m.BuildLiquifierKgPerHour[z, p]),
            "total_capacity_liquifier_kg_hour": value(
                m.LiquifierCapacityKgPerHour[z, p]
            ),
            "build_tank_kg": value(m.BuildLiquidHydrogenTankKg[z, p]),
            "total_capacity_tank_kg": value(m.LiquidHydrogenTankCapacityKg[z, p]),
            "build_fuelcell_MW": value(m.BuildFuelCellMW[z, p]),
            "total_capacity_fuelcell_MW": value(m.FuelCellCapacityMW[z, p]),
        }
        for z in m.LOAD_ZONES
        for p in m.PERIODS
    )
    write_table(
        m,
        output_file=os.path.join(outdir, "hydrogen_output_period.csv"),
        df=df,
        index=False,
    )
    df = pd.DataFrame(
        {
            "hgtimeseries": hgts,
            "load_zone": z,
            "hg_period": m.hgts_hg_period[hgts],
            "period": m.hgts_period[hgts],
            "tank_store_hydrogen_kg": value(m.StoreLiquidHydrogenKg[z, hgts]),
            "tank_withdraw_hydrogen_kg": value(m.WithdrawLiquidHydrogenKg[z, hgts]),
        }
        for z in m.LOAD_ZONES
        for hgts in m.HGTS
    )
    write_table(
        m,
        output_file=os.path.join(outdir, "hydrogen_output_hgtimeseries.csv"),
        df=df,
        index=False,
    )
    df = pd.DataFrame(
        {
            "timepoint": t,
            "load_zone": z,
            "hg_timeseries": m.tp_to_hgts[t],
            "electrolyzer_demand_MW": value(m.RunElectrolyzerMW[z, t]),
            "electrolyzer_hydrogen_produced_kg_hour": value(
                m.ProduceHydrogenKgPerHour[z, t]
            ),
            "liquified_hydrogen_kg_hour": value(m.LiquifyHydrogenKgPerHour[z, t]),
            "liquifier_demand_MW": value(m.LiquifyHydrogenMW[z, t]),
            "fuelcell_dispatch_MW": value(m.DispatchFuelCellMW[z, t]),
            "fuelcell_hydrogen_consumed_kg_hour": value(
                m.ConsumeHydrogenKgPerHour[z, t]
            ),
        }
        for z in m.LOAD_ZONES
        for t in m.TIMEPOINTS
    )
    write_table(
        m,
        output_file=os.path.join(outdir, "hydrogen_output_timepoint.csv"),
        df=df,
        index=False,
    )
    df = pd.DataFrame(
        {
            "period": p,
            # "hydrogen_income": value(m.hydrogen_income_per_period[p]),
            "hydrogen_cost_per_period": value(m.hydrogen_generation_cost_per_period[p]),
            "hydrogen_NPV_period": value(m.HydrogenFixedCostAnnual[p]),
            # "hydrogen_profit_per_period": value(m.hydrogen_profit_per_period[p]),
            "hydrogen_generation_per_period": value(m.HydrogenGeneration[p]),
            # "electrolyzer_use_per_period": value(m.electrolyzer_use_per_period[p]),
            "electrolyzer_capacity_per_period": value(
                m.electrolyzer_capacity_per_period[p]
            ),
        }
        for p in m.PERIODS
    )
    write_table(
        m, output_file=os.path.join(outdir, "hydrogen_profit.csv"), df=df, index=False
    )
    df = pd.DataFrame(
        {
            "timestamp": t,
            "load_zone": z,
            "hydrogen_production": value(m.ProduceHydrogenKgPerHour[z, t]),
            "electrolyzer_electricity_demand": value(m.RunElectrolyzerMW[z, t]),
        }
        for z in m.LOAD_ZONES
        for t in m.TIMEPOINTS
    )
    write_table(
        m,
        output_file=os.path.join(outdir, "hydrogen_production.csv"),
        df=df,
        index=False,
    )


@graph("electrolyzer_capacity_per_period_s", title="Total Capacity by Period")
def graph_electrolyzer_capacity(tools):
    elec_capacity = tools.get_dataframe("hydrogen_profit.csv")
    # elec_capacity = tools.pd.read_csv("hydrogen_profit.csv")
    # elec_capacity = elec_capacity.drop("hydrogen_income", axis=1)
    elec_capacity = elec_capacity.drop("hydrogen_cost_per_period", axis=1)
    # elec_capacity = elec_capacity.drop("hydrogen_NPV_period", axis=1)
    # elec_capacity = elec_capacity.drop("hydrogen_profit_per_period", axis=1)
    elec_capacity = elec_capacity.drop("hydrogen_generation_per_period", axis=1)
    elec_capacity.plot(
        kind="bar",
        ylabel="Capacity MW",
        ax=tools.get_axes(),
        xlabel="Period",
        x="period",
    )


# @graph("hydrogen_income_s", title="Hydrogen Income by Period")
# is this aggregating income or showing the profit by period (ie. if you make 2$ in p1 then 5$ in p2 will the second bar show 7$)
# def graph_hydrogen_income(tools):
#    hydrogen_income = tools.get_dataframe("hydrogen_profit.csv")
# hydrogen_income = tools.pd.read_csv("hydrogen_profit.csv")
#    hydrogen_income = hydrogen_income.drop("electrolyzer_capacity_per_period", axis=1)
#    hydrogen_income = hydrogen_income.drop("hydrogen_cost_per_period", axis=1)
#    hydrogen_income = hydrogen_income.drop("hydrogen_NPV_period", axis=1)
#    hydrogen_income = hydrogen_income.drop("hydrogen_profit_per_period", axis=1)
#    hydrogen_income = hydrogen_income.drop("hydrogen_generation_per_period", axis=1)
#    hydrogen_income.plot(
#        kind="bar", ax=tools.get_axes(), ylabel="Income USD", xlabel="Period"
#    )


# @graph("hydrogen_profit_per_period_s", title="Hydrogen Profit per Period")
# def graph_hydrogen_profit_per_period(tools):
#    hydrogen_profit_pp = tools.get_dataframe("hydrogen_profit.csv")
#    hydrogen_profit_pp = hydrogen_profit_pp.drop(
#        "electrolyzer_capacity_per_period", axis=1
#    )
#    hydrogen_profit_pp = hydrogen_profit_pp.drop("hydrogen_cost_per_period", axis=1)
#    hydrogen_profit_pp = hydrogen_profit_pp.drop("hydrogen_NPV_period", axis=1)
#    hydrogen_profit_pp = hydrogen_profit_pp.drop("hydrogen_income", axis=1)
#    hydrogen_profit_pp = hydrogen_profit_pp.drop(
#        "hydrogen_generation_per_period", axis=1
#    )
#    hydrogen_profit_pp.plot(
#        kind="bar", ax=tools.get_axes(), ylabel="Profit USD", xlabel="Period"
#    )


# @graph("hydrogen_generation_per_period_s", title="Total Hydrogen Generation by Period")
# is the correct  unit mwh?
# def graph_hydrogen_generation_per_period(tools):
#    hydrogen_generation_pp = tools.get_dataframe("hydrogen_profit.csv")
#    hydrogen_generation_pp = hydrogen_generation_pp.drop("hydrogen_income", axis=1)
#    hydrogen_generation_pp = hydrogen_generation_pp.drop(
#        "hydrogen_cost_per_period", axis=1
#    )
#    hydrogen_generation_pp = hydrogen_generation_pp.drop("hydrogen_NPV_period", axis=1)
#    hydrogen_generation_pp = hydrogen_generation_pp.drop(
#        "hydrogen_profit_per_period", axis=1
#    )
#    hydrogen_generation_pp = hydrogen_generation_pp.drop(
#        "electrolyzer_capacity_per_period", axis=1
#    )
#    hydrogen_generation_pp.plot(
#        kind="bar", ax=tools.get_axes(), ylabel="Generation mWh", xlabel="Period"
#    )
