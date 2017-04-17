import os
from pyomo.environ import *
from switch_model.financials import capital_recovery_factor as crf

def define_components(m):
    
    # TODO: change this to allow multiple storage technologies.

    # battery capital cost
    # TODO: accept a single battery_capital_cost_per_mwh_capacity value or the annual values shown here
    m.BATTERY_CAPITAL_COST_YEARS = Set() # list of all years for which capital costs are available
    m.battery_capital_cost_per_mwh_capacity_by_year = Param(m.BATTERY_CAPITAL_COST_YEARS)
    
    # TODO: merge this code with batteries.py and auto-select between fixed calendar life and cycle life
    # based on whether battery_n_years or battery_n_cycles is provided. (Or find some hybrid that can
    # handle both well?)
    # number of years the battery can last; we assume there is no limit on cycle life within this period
    m.battery_n_years = Param()
    # maximum depth of discharge
    m.battery_max_discharge = Param()
    # round-trip efficiency
    m.battery_efficiency = Param()
    # fastest time that storage can be emptied (down to max_discharge)
    m.battery_min_discharge_time = Param()

    # amount of battery capacity to build and use (in MWh)
    # TODO: integrate this with other project data, so it can contribute to reserves, etc.
    m.BuildBattery = Var(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)
    m.Battery_Capacity = Expression(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
        sum(
            m.BuildBattery[z, bld_yr] 
                for bld_yr in m.CURRENT_AND_PRIOR_PERIODS[p] if bld_yr + m.battery_n_years > p
        )
    )

    # rate of charging/discharging battery
    m.ChargeBattery = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    m.DischargeBattery = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)

    # storage level at start of each timepoint
    m.BatteryLevel = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)

    # add storage dispatch to the zonal energy balance
    m.Zone_Power_Injections.append('DischargeBattery')
    m.Zone_Power_Withdrawals.append('ChargeBattery')
    
    # add the batteries to the objective function

    # cost recovery for any battery capacity currently active
    m.BatteryAnnualCost = Expression(
        m.PERIODS,
        rule=lambda m, p: sum(
            m.BuildBattery[z, bld_yr] 
            * m.battery_capital_cost_per_mwh_capacity_by_year[bld_yr] 
            * crf(m.interest_rate, m.battery_n_years)
                for bld_yr in m.CURRENT_AND_PRIOR_PERIODS[p] if bld_yr + m.battery_n_years > p
                    for z in m.LOAD_ZONES 
        )
    )
    m.Cost_Components_Per_Period.append('BatteryAnnualCost')

    # Calculate the state of charge based on conservation of energy
    # NOTE: this is circular for each day
    # NOTE: the overall level for the day is free, but the levels each timepoint are chained.
    m.Battery_Level_Calc = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.BatteryLevel[z, t] == 
            m.BatteryLevel[z, m.tp_previous[t]]
            + m.tp_duration_hrs[t] * (
                m.battery_efficiency * m.ChargeBattery[z, m.tp_previous[t]] 
                - m.DischargeBattery[z, m.tp_previous[t]]
            )
    )
      
    # limits on storage level
    m.Battery_Min_Level = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t: 
        (1.0 - m.battery_max_discharge) * m.Battery_Capacity[z, m.tp_period[t]]
        <= 
        m.BatteryLevel[z, t]
    )
    m.Battery_Max_Level = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t: 
        m.BatteryLevel[z, t]
        <= 
        m.Battery_Capacity[z, m.tp_period[t]]
    )

    m.Battery_Max_Charge_Rate = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.ChargeBattery[z, t]
        <=
        m.Battery_Capacity[z, m.tp_period[t]] * m.battery_max_discharge / m.battery_min_discharge_time
    )
    m.Battery_Max_Discharge_Rate = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.DischargeBattery[z, t]
        <=
        m.Battery_Capacity[z, m.tp_period[t]] * m.battery_max_discharge / m.battery_min_discharge_time
    )

    # how much could output/input be increased on short notice (to provide reserves)
    m.BatterySlackUp = Expression(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.Battery_Capacity[z, m.tp_period[t]] * m.battery_max_discharge / m.battery_min_discharge_time
        - m.DischargeBattery[z, t]
        + m.ChargeBattery[z, t]
    )
    m.BatterySlackDown = Expression(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.Battery_Capacity[z, m.tp_period[t]] * m.battery_max_discharge / m.battery_min_discharge_time
        - m.ChargeBattery[z, t]
        + m.DischargeBattery[z, t]
    )

    # assume batteries can only complete one full cycle (charged to max discharge)
    # per day, averaged over each period
    m.Battery_Cycle_Limit = Constraint(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
        sum(m.DischargeBattery[z, tp] * m.tp_duration_hrs[tp] for tp in m.TPS_IN_PERIOD[p])
        <= 
        m.Battery_Capacity[z, p] * m.battery_max_discharge * m.period_length_hours[p]
    )
    
    # Register with spinning reserves if it is available
    if 'Spinning_Reserve_Up_Provisions' in dir(m):
        m.BatterySpinningReserveUp = Expression(
            m.BALANCING_AREA_TIMEPOINTS, 
            rule=lambda m, b, t:
                sum(m.BatterySlackUp[z, t]
                    for z in m.ZONES_IN_BALANCING_AREA[b])
        )
        m.Spinning_Reserve_Up_Provisions.append('BatterySpinningReserveUp')

        m.BatterySpinningReserveDown = Expression(
            m.BALANCING_AREA_TIMEPOINTS, 
            rule=lambda m, b, t: \
                sum(m.BatterySlackDown[g, t] 
                    for z in m.ZONES_IN_BALANCING_AREA[b])
        )
        m.Spinning_Reserve_Down_Provisions.append('BatterySpinningReserveDown')


def load_inputs(m, switch_data, inputs_dir):
    """
    Import battery data from .dat and .tab files. 
    """
    switch_data.load(filename=os.path.join(inputs_dir, 'batteries.dat'))
    switch_data.load_aug(
        optional=False,
        filename=os.path.join(inputs_dir, 'battery_capital_cost.tab'),
        autoselect=True,
        index=m.BATTERY_CAPITAL_COST_YEARS,
        param=(m.battery_capital_cost_per_mwh_capacity_by_year,))
