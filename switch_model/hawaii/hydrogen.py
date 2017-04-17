import os
from pyomo.environ import *
from switch_model.financials import capital_recovery_factor as crf

def define_components(m):

    # electrolyzer details
    m.hydrogen_electrolyzer_capital_cost_per_mw = Param()
    m.hydrogen_electrolyzer_fixed_cost_per_mw_year = Param(default=0.0)
    m.hydrogen_electrolyzer_variable_cost_per_kg = Param(default=0.0)  # assumed to include any refurbishment needed
    m.hydrogen_electrolyzer_kg_per_mwh = Param() # assumed to deliver H2 at enough pressure for liquifier and daily buffering
    m.hydrogen_electrolyzer_life_years = Param()
    m.BuildElectrolyzerMW = Var(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)
    m.ElectrolyzerCapacityMW = Expression(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p: 
        sum(m.BuildElectrolyzerMW[z, p_] for p_ in m.CURRENT_AND_PRIOR_PERIODS[p]))
    m.RunElectrolyzerMW = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    m.ProduceHydrogenKgPerHour = Expression(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.RunElectrolyzerMW[z, t] * m.hydrogen_electrolyzer_kg_per_mwh)

    # note: we assume there is a gaseous hydrogen storage tank that is big enough to buffer
    # daily production, storage and withdrawals of hydrogen, but we don't include a cost
    # for this (because it will be negligible compared to the rest of the costs)
    # This allows the system to do some intra-day arbitrage without going all the way to liquification

    # liquifier details
    m.hydrogen_liquifier_capital_cost_per_kg_per_hour = Param()
    m.hydrogen_liquifier_fixed_cost_per_kg_hour_year = Param(default=0.0)
    m.hydrogen_liquifier_variable_cost_per_kg = Param(default=0.0)
    m.hydrogen_liquifier_mwh_per_kg = Param()
    m.hydrogen_liquifier_life_years = Param()
    m.BuildLiquifierKgPerHour = Var(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)  # capacity to build, measured in kg/hour of throughput
    m.LiquifierCapacityKgPerHour = Expression(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p: 
        sum(m.BuildLiquifierKgPerHour[z, p_] for p_ in m.CURRENT_AND_PRIOR_PERIODS[p]))
    m.LiquifyHydrogenKgPerHour = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    m.LiquifyHydrogenMW = Expression(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.LiquifyHydrogenKgPerHour[z, t] * m.hydrogen_liquifier_mwh_per_kg
    )
    
    # storage tank details
    m.liquid_hydrogen_tank_capital_cost_per_kg = Param()
    m.liquid_hydrogen_tank_minimum_size_kg = Param(default=0.0)
    m.liquid_hydrogen_tank_life_years = Param()
    m.BuildLiquidHydrogenTankKg = Var(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals) # in kg
    m.LiquidHydrogenTankCapacityKg = Expression(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
        sum(m.BuildLiquidHydrogenTankKg[z, p_] for p_ in m.CURRENT_AND_PRIOR_PERIODS[p]))
    m.StoreLiquidHydrogenKg = Expression(m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, z, ts:
        m.ts_duration_of_tp[ts] * sum(m.LiquifyHydrogenKgPerHour[z, tp] for tp in m.TPS_IN_TS[ts])
    )
    m.WithdrawLiquidHydrogenKg = Var(m.LOAD_ZONES, m.TIMESERIES, within=NonNegativeReals)
    # note: we assume the system will be large enough to neglect boil-off

    # fuel cell details
    m.hydrogen_fuel_cell_capital_cost_per_mw = Param()
    m.hydrogen_fuel_cell_fixed_cost_per_mw_year = Param(default=0.0)
    m.hydrogen_fuel_cell_variable_cost_per_mwh = Param(default=0.0) # assumed to include any refurbishment needed
    m.hydrogen_fuel_cell_mwh_per_kg = Param()
    m.hydrogen_fuel_cell_life_years = Param()
    m.BuildFuelCellMW = Var(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)
    m.FuelCellCapacityMW = Expression(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p: 
        sum(m.BuildFuelCellMW[z, p_] for p_ in m.CURRENT_AND_PRIOR_PERIODS[p]))
    m.DispatchFuelCellMW = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    m.ConsumeHydrogenKgPerHour = Expression(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.DispatchFuelCellMW[z, t] / m.hydrogen_fuel_cell_mwh_per_kg
    )

    # hydrogen mass balances
    # note: this allows for buffering of same-day production and consumption 
    # of hydrogen without ever liquifying it
    m.Hydrogen_Conservation_of_Mass_Daily = Constraint(m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, z, ts:
        m.StoreLiquidHydrogenKg[z, ts] - m.WithdrawLiquidHydrogenKg[z, ts]
        == 
        m.ts_duration_of_tp[ts] * sum(
            m.ProduceHydrogenKgPerHour[z, tp] - m.ConsumeHydrogenKgPerHour[z, tp] 
            for tp in m.TPS_IN_TS[ts]
        )
    )
    m.Hydrogen_Conservation_of_Mass_Annual = Constraint(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
        sum(
            (m.StoreLiquidHydrogenKg[z, ts] - m.WithdrawLiquidHydrogenKg[z, ts]) 
                * m.ts_scale_to_year[ts]
            for ts in m.TS_IN_PERIOD[p]
        ) == 0
    )

    # limits on equipment
    m.Max_Run_Electrolyzer = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.RunElectrolyzerMW[z, t] <= m.ElectrolyzerCapacityMW[z, m.tp_period[t]])
    m.Max_Run_Fuel_Cell = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.DispatchFuelCellMW[z, t] <= m.FuelCellCapacityMW[z, m.tp_period[t]])
    m.Max_Run_Liquifier = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.LiquifyHydrogenKgPerHour[z, t] <= m.LiquifierCapacityKgPerHour[z, m.tp_period[t]])

    # minimum size for hydrogen tank
    m.BuildAnyLiquidHydrogenTank = Var(m.LOAD_ZONES, m.PERIODS, within=Binary)
    m.Set_BuildAnyLiquidHydrogenTank_Flag = Constraint(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
        Constraint.Skip if m.liquid_hydrogen_tank_minimum_size_kg == 0.0
        else (
            m.BuildLiquidHydrogenTankKg[z, p] 
            <= 
            1000 * m.BuildAnyLiquidHydrogenTank[z, p] * m.liquid_hydrogen_tank_minimum_size_kg
        )
    )
    m.Build_Minimum_Liquid_Hydrogen_Tank = Constraint(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
        Constraint.Skip if m.liquid_hydrogen_tank_minimum_size_kg == 0.0
        else (
            m.BuildLiquidHydrogenTankKg[z, p] 
            >= 
            m.BuildAnyLiquidHydrogenTank[z, p] * m.liquid_hydrogen_tank_minimum_size_kg
        )
    )

    # maximum amount that hydrogen fuel cells can contribute to system reserves
    # Note: we assume we can't use fuel cells for reserves unless we've also built at least half 
    # as much electrolyzer capacity and a tank that can provide the reserves for 12 hours
    # (this is pretty arbitrary, but avoids just installing a fuel cell as a "free" source of reserves)
    m.HydrogenFuelCellMaxReservePower = Var(m.LOAD_ZONES, m.TIMEPOINTS)
    m.Hydrogen_FC_Reserve_Capacity_Limit = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.HydrogenFuelCellMaxReservePower[z, t]
        <=
        m.FuelCellCapacityMW[z, m.tp_period[t]]
    )
    m.Hydrogen_FC_Reserve_Storage_Limit = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.HydrogenFuelCellMaxReservePower[z, t]
        <=
        m.LiquidHydrogenTankCapacityKg[z, m.tp_period[t]] * m.hydrogen_fuel_cell_mwh_per_kg / 12.0
    )
    m.Hydrogen_FC_Reserve_Electrolyzer_Limit = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.HydrogenFuelCellMaxReservePower[z, t]
        <=
        2.0 * m.ElectrolyzerCapacityMW[z, m.tp_period[t]]
    )

    # how much extra power could hydrogen equipment produce or absorb on short notice (for reserves)
    m.HydrogenSlackUp = Expression(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.RunElectrolyzerMW[z, t] 
        + m.LiquifyHydrogenMW[z, t]
        + m.HydrogenFuelCellMaxReservePower[z, t]
        - m.DispatchFuelCellMW[z, t]
    )
    m.HydrogenSlackDown = Expression(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.ElectrolyzerCapacityMW[z, m.tp_period[t]] - m.RunElectrolyzerMW[z, t] 
        # ignore liquifier potential since it's small and this is a low-value reserve product
        + m.DispatchFuelCellMW[z, t]
    )
    
    # there must be enough storage to hold _all_ the production each period (net of same-day consumption)
    # note: this assumes we cycle the system only once per year (store all energy, then release all energy)
    # alternatives: allow monthly or seasonal cycling, or directly model the whole year with inter-day linkages
    m.Max_Store_Liquid_Hydrogen = Constraint(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
        sum(m.StoreLiquidHydrogenKg[z, ts] * m.ts_scale_to_year[ts] for ts in m.TS_IN_PERIOD[p])
        <= m.LiquidHydrogenTankCapacityKg[z, p]
    )
    
    # add electricity consumption and production to the zonal energy balance
    m.Zone_Power_Withdrawals.append('RunElectrolyzerMW')
    m.Zone_Power_Withdrawals.append('LiquifyHydrogenMW')
    m.Zone_Power_Injections.append('DispatchFuelCellMW')

    # add costs to the model
    m.HydrogenVariableCost = Expression(m.TIMEPOINTS, rule=lambda m, t:
        sum(
            m.ProduceHydrogenKgPerHour[z, t] * m.hydrogen_electrolyzer_variable_cost_per_kg
            + m.LiquifyHydrogenKgPerHour[z, t] * m.hydrogen_liquifier_variable_cost_per_kg
            + m.DispatchFuelCellMW[z, t] * m.hydrogen_fuel_cell_variable_cost_per_mwh
            for z in m.LOAD_ZONES
        )
    )
    m.HydrogenFixedCostAnnual = Expression(m.PERIODS, rule=lambda m, p:
        sum(
            m.ElectrolyzerCapacityMW[z, p] * (
                m.hydrogen_electrolyzer_capital_cost_per_mw * crf(m.interest_rate, m.hydrogen_electrolyzer_life_years)
                + m.hydrogen_electrolyzer_fixed_cost_per_mw_year)
            + m.LiquifierCapacityKgPerHour[z, p] * (
                m.hydrogen_liquifier_capital_cost_per_kg_per_hour * crf(m.interest_rate, m.hydrogen_liquifier_life_years)
                + m.hydrogen_liquifier_fixed_cost_per_kg_hour_year)
            + m.LiquidHydrogenTankCapacityKg[z, p] * (
                m.liquid_hydrogen_tank_capital_cost_per_kg * crf(m.interest_rate, m.liquid_hydrogen_tank_life_years))
            + m.FuelCellCapacityMW[z, p] * (
                m.hydrogen_fuel_cell_capital_cost_per_mw * crf(m.interest_rate, m.hydrogen_fuel_cell_life_years)
                + m.hydrogen_fuel_cell_fixed_cost_per_mw_year)
            for z in m.LOAD_ZONES
        )
    )
    m.Cost_Components_Per_TP.append('HydrogenVariableCost')
    m.Cost_Components_Per_Period.append('HydrogenFixedCostAnnual')
    
    # Register with spinning reserves if it is available
    if 'Spinning_Reserve_Up_Provisions' in dir(m):
        m.HydrogenSpinningReserveUp = Expression(
            m.BALANCING_AREA_TIMEPOINTS, 
            rule=lambda m, b, t:
                sum(m.HydrogenSlackUp[z, t]
                    for z in m.ZONES_IN_BALANCING_AREA[b])
        )
        m.Spinning_Reserve_Up_Provisions.append('HydrogenSpinningReserveUp')

        m.HydrogenSpinningReserveDown = Expression(
            m.BALANCING_AREA_TIMEPOINTS, 
            rule=lambda m, b, t: \
                sum(m.HydrogenSlackDown[g, t] 
                    for z in m.ZONES_IN_BALANCING_AREA[b])
        )
        m.Spinning_Reserve_Down_Provisions.append('HydrogenSpinningReserveDown')


def load_inputs(mod, switch_data, inputs_dir):
    """
    Import hydrogen data from a .dat file. 
    TODO: change this to allow multiple storage technologies.
    """
    switch_data.load(filename=os.path.join(inputs_dir, 'hydrogen.dat'))
