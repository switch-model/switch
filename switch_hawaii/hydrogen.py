import os
from pyomo.environ import *
from switch_mod.financials import capital_recovery_factor as crf

def define_components(m):
    
    # make helper set identifying all timeseries in each period
    if hasattr(m, "PERIOD_TS"):
        print "DEPRECATION NOTE: PERIOD_TS is defined in hydrogen.py, but it already exists, so this can be removed."
    else:
        m.PERIOD_TS = Set(m.PERIODS, ordered=True, within=m.TIMESERIES, initialize=lambda m, p:
            [ts for ts in m.TIMESERIES if m.ts_period[ts] == p])

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
    m.liquid_hydrogen_tank_life_years = Param()
    m.BuildLiquidHydrogenTankKg = Var(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals) # in kg
    m.LiquidHydrogenTankCapacityKg = Expression(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
        sum(m.BuildLiquidHydrogenTankKg[z, p_] for p_ in m.CURRENT_AND_PRIOR_PERIODS[p]))
    m.StoreLiquidHydrogenKg = Expression(m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, z, ts:
        m.ts_duration_of_tp[ts] * sum(m.LiquifyHydrogenKgPerHour[z, tp] for tp in m.TS_TPS[ts])
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
            for tp in m.TS_TPS[ts]
        )
    )
    m.Hydrogen_Conservation_of_Mass_Annual = Constraint(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
        sum(
            (m.StoreLiquidHydrogenKg[z, ts] - m.WithdrawLiquidHydrogenKg[z, ts]) 
                * m.ts_scale_to_year[ts]
            for ts in m.PERIOD_TS[p]
        ) == 0
    )

    # limits on equipment
    m.Max_Run_Electrolyzer = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.RunElectrolyzerMW[z, t] <= m.ElectrolyzerCapacityMW[z, m.tp_period[t]])
    m.Max_Run_Fuel_Cell = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.DispatchFuelCellMW[z, t] <= m.FuelCellCapacityMW[z, m.tp_period[t]])
    m.Max_Run_Liquifier = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.LiquifyHydrogenKgPerHour[z, t] <= m.LiquifierCapacityKgPerHour[z, m.tp_period[t]])
    
    # there must be enough storage to hold _all_ the production each period (net of same-day consumption)
    # note: this assumes we cycle the system only once per year (store all energy, then release all energy)
    # alternatives: allow monthly or seasonal cycling, or directly model the whole year with inter-day linkages
    m.Max_Store_Liquid_Hydrogen = Constraint(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
        sum(m.StoreLiquidHydrogenKg[z, ts] * m.ts_scale_to_year[ts] for ts in m.PERIOD_TS[p])
        <= m.LiquidHydrogenTankCapacityKg[z, p]
    )
    
    # add electricity consumption and production to the model
    m.LZ_Energy_Components_Consume.append('RunElectrolyzerMW')
    m.LZ_Energy_Components_Consume.append('LiquifyHydrogenMW')
    m.LZ_Energy_Components_Produce.append('DispatchFuelCellMW')

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
    m.cost_components_tp.append('HydrogenVariableCost')
    m.cost_components_annual.append('HydrogenFixedCostAnnual')
    


def load_inputs(mod, switch_data, inputs_dir):
    """
    Import hydrogen data from a .dat file. 
    TODO: change this to allow multiple storage technologies.
    """
    switch_data.load(filename=os.path.join(inputs_dir, 'hydrogen.dat'))
