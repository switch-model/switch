import os
from pyomo.environ import *

def define_components(m):
    
    # It's not clear how best to model battery cell replacement
    # One option: facility has a specific life, and variable O&M builds up a replacement fund for
    # intermediate cell replacement (but there's no extra salvage value from this?)?

    # Should battery facilities be priced per MW (power conversion) and per MWh (cells)?
    # Should we switch to modeling batteries with standard cost components - 
    # capital, fixed O&M, variable O&M (which includes the cost of any early replacements)?
    # note: sodium sulfur is widely reported to have 15-year calendar life (due to corrosion at
    # high temperatures) and 4500 cycle life (which can be much longer with shallow cycles, much 
    # shorter with deep cycles). So one cycle per day comes for "free" (i.e., is included in the 
    # capital cost), but if there are two cycles per day, there should be a higher cost, included 
    # in the variable O&M. This is tricky to model. If there were no limit on the calendar life,
    # we could omit the cell cost from fixed O&M and include it entirely in variable O&M. But then
    # it looks like you can get a high-capacity low-usage system for cheap (i.e., you ignore the
    # money tied up in the system while you wait to use it). So maybe my current approach is best:
    # only pay interest on the system (not full cost recovery), and pay into a fund every time you
    # use the battery, so on average you can always have a refurbished battery on hand.
    
    # battery capital cost
    m.battery_capital_cost_per_mwh_capacity = Param()
    # number of full cycles the battery can do; we assume shallower cycles do proportionally less damage
    m.battery_n_cycles = Param()
    # maximum depth of discharge
    m.battery_max_discharge = Param()
    # round-trip efficiency
    m.battery_efficiency = Param()
    # fastest time that storage can be emptied (down to max_discharge)
    m.battery_min_discharge_time = Param()

    # we treat storage as infinitely long-lived (so we pay just interest on the loan),
    # but charge a usage fee corresponding to the reduction in life during each cycle 
    # (i.e., enough to restore it to like-new status, on average)
    m.battery_cost_per_mwh_cycled = Param(initialize = lambda m:
        m.battery_capital_cost_per_mwh_capacity / (m.battery_n_cycles * m.battery_max_discharge)
    )
    m.battery_fixed_cost_per_year = Param(initialize = lambda m:
        m.battery_capital_cost_per_mwh_capacity * m.interest_rate
    )

    # amount of battery capacity to build and use (in MWh)
    # TODO: integrate this with other project data, so it can contribute to reserves, etc.
    m.BuildBattery = Var(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)
    m.Battery_Capacity = Expression(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, p:
        sum(m.BuildBattery[z, pp] for pp in m.CURRENT_AND_PRIOR_PERIODS[p])
    )

    # rate of charging/discharging battery
    m.ChargeBattery = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    m.DischargeBattery = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)

    # storage level at start of each timepoint
    m.BatteryLevel = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)

    # add storage to the zonal energy balance
    m.Zone_Power_Injections.append('DischargeBattery')
    m.Zone_Power_Withdrawals.append('ChargeBattery')
    
    # add the batteries to the objective function
    m.Battery_Variable_Cost = Expression(m.TIMEPOINTS, rule=lambda m, t:
        sum(m.battery_cost_per_mwh_cycled * m.DischargeBattery[z, t] for z in m.LOAD_ZONES)
    )
    m.Battery_Fixed_Cost_Annual = Expression(m.PERIODS, rule=lambda m, p:
        sum(m.battery_fixed_cost_per_year * m.Battery_Capacity[z, p] for z in m.LOAD_ZONES)
    )
    m.Cost_Components_Per_TP.append('Battery_Variable_Cost')
    m.Cost_Components_Per_Period.append('Battery_Fixed_Cost_Annual')

    # Calculate the state of charge based on conservation of energy
    # NOTE: this is circular for each day
    # NOTE: the overall level for the day is free, but the levels each timepoint are chained.
    m.Battery_Level_Calc = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.BatteryLevel[z, t] == 
            m.BatteryLevel[z, m.tp_previous[t]]
            + m.battery_efficiency * m.ChargeBattery[z, m.tp_previous[t]] 
            - m.DischargeBattery[z, m.tp_previous[t]]
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

    m.Battery_Max_Charge = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.ChargeBattery[z, t]
        <=
        m.Battery_Capacity[z, m.tp_period[t]] * m.battery_max_discharge / m.battery_min_discharge_time
    )
    m.Battery_Max_Disharge = Constraint(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        m.DischargeBattery[z, t]
        <=
        m.Battery_Capacity[z, m.tp_period[t]] * m.battery_max_discharge / m.battery_min_discharge_time
    )


def load_inputs(mod, switch_data, inputs_dir):
    """
    Import battery data from a .dat file. 
    TODO: change this to allow multiple storage technologies.
    """
    switch_data.load(filename=os.path.join(inputs_dir, 'batteries.dat'))
