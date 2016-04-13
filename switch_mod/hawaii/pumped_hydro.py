import os
from pyomo.environ import *
from switch_mod.financials import capital_recovery_factor as crf

def define_components(m):
    
    m.PH_PROJECTS = Set()
    
    m.ph_load_zone = Param(m.PH_PROJECTS)
    
    m.ph_capital_cost_per_mw = Param(m.PH_PROJECTS, within=NonNegativeReals)
    m.ph_project_life = Param(m.PH_PROJECTS, within=NonNegativeReals)
    
    # annual O&M cost for pumped hydro project, percent of capital cost
    m.ph_fixed_om_percent = Param(m.PH_PROJECTS, within=NonNegativeReals)
    
    # total annual cost
    m.ph_fixed_cost_per_mw_per_year = Param(m.PH_PROJECTS, initialize=lambda m, p:
        m.ph_capital_cost_per_mw[p] * 
            (crf(m.interest_rate, m.ph_project_life[p]) + m.ph_fixed_om_percent[p])
    )
    
    # round-trip efficiency of the pumped hydro facility
    m.ph_efficiency = Param(m.PH_PROJECTS)
    
    # average energy available from water inflow each day
    # (system must balance energy net of this each day)
    m.ph_inflow_mw = Param(m.PH_PROJECTS)
    
    # maximum size of pumped hydro project
    m.ph_max_capacity_mw = Param(m.PH_PROJECTS)
    
    # How much pumped hydro to build
    m.BuildPumpedHydroMW = Var(m.PH_PROJECTS, m.PERIODS, within=NonNegativeReals)
    m.Pumped_Hydro_Proj_Capacity_MW = Expression(m.PH_PROJECTS, m.PERIODS, rule=lambda m, pr, pe:
        sum(m.BuildPumpedHydroMW[pr, pp] for pp in m.CURRENT_AND_PRIOR_PERIODS[pe])
    )

    # flag indicating whether any capacity is added to each project each year
    m.BuildAnyPumpedHydro = Var(m.PH_PROJECTS, m.PERIODS, within=Binary)    

    # How to run pumped hydro
    m.PumpedHydroProjGenerateMW = Var(m.PH_PROJECTS, m.TIMEPOINTS, within=NonNegativeReals)
    m.PumpedHydroProjStoreMW = Var(m.PH_PROJECTS, m.TIMEPOINTS, within=NonNegativeReals)

    # constraints on construction of pumped hydro

    # don't build more than the max allowed capacity
    m.Pumped_Hydro_Max_Build = Constraint(m.PH_PROJECTS, m.PERIODS, rule=lambda m, pr, pe:
        m.Pumped_Hydro_Proj_Capacity_MW[pr, pe] <= m.ph_max_capacity_mw[pr]
    )
    
    # force the build flag on for the year(s) when pumped hydro is built
    m.Pumped_Hydro_Set_Build_Flag = Constraint(m.PH_PROJECTS, m.PERIODS, rule=lambda m, pr, pe:
        m.BuildPumpedHydroMW[pr, pe] <= m.BuildAnyPumpedHydro[pr, pe] * m.ph_max_capacity_mw[pr]
    )
    # only build in one year (can be deactivated to allow incremental construction)
    m.Pumped_Hydro_Build_Once = Constraint(m.PH_PROJECTS, rule=lambda m, pr:
        sum(m.BuildAnyPumpedHydro[pr, pe] for pe in m.PERIODS) <= 1)
    # only build full project size (deactivated by default, to allow smaller projects)
    m.Pumped_Hydro_Build_All_Or_None = Constraint(m.PH_PROJECTS, m.PERIODS, rule=lambda m, pr, pe:
        m.BuildPumpedHydroMW[pr, pe] == m.BuildAnyPumpedHydro[pr, pe] * m.ph_max_capacity_mw[pr]
    )
    m.Deactivate_Pumped_Hydro_Build_All_Or_None = BuildAction(rule=lambda m:
        m.Pumped_Hydro_Build_All_Or_None.deactivate()
    )
    
    # limits on pumping and generation
    m.Pumped_Hydro_Max_Generate_Rate = Constraint(m.PH_PROJECTS, m.TIMEPOINTS, rule=lambda m, pr, t:
        m.PumpedHydroProjGenerateMW[pr, t]
        <=
        m.Pumped_Hydro_Proj_Capacity_MW[pr, m.tp_period[t]]
    )
    m.Pumped_Hydro_Max_Store_Rate = Constraint(m.PH_PROJECTS, m.TIMEPOINTS, rule=lambda m, pr, t:
        m.PumpedHydroProjStoreMW[pr, t]
        <=
        m.Pumped_Hydro_Proj_Capacity_MW[pr, m.tp_period[t]]
    )

    # return reservoir to at least the starting level every day, net of any inflow
    # it can also go higher than starting level, which indicates spilling surplus water
    m.Pumped_Hydro_Daily_Balance = Constraint(m.PH_PROJECTS, m.TIMESERIES, rule=lambda m, pr, ts:
        sum(
            m.PumpedHydroProjStoreMW[pr, tp] * m.ph_efficiency[pr]
            + m.ph_inflow_mw[pr]
            - m.PumpedHydroProjGenerateMW[pr, tp]
            for tp in m.TS_TPS[ts]
         ) >= 0
    )

    m.GeneratePumpedHydro = Expression(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        sum(m.PumpedHydroProjGenerateMW[pr, t] for pr in m.PH_PROJECTS if m.ph_load_zone[pr]==z)
    )
    m.StorePumpedHydro = Expression(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        sum(m.PumpedHydroProjStoreMW[pr, t] for pr in m.PH_PROJECTS if m.ph_load_zone[pr]==z)
    )
    
    # calculate costs
    m.Pumped_Hydro_Fixed_Cost_Annual = Expression(m.PERIODS, rule=lambda m, pe:
        sum(m.ph_fixed_cost_per_mw_per_year[pr] * m.Pumped_Hydro_Proj_Capacity_MW[pr, pe] for pr in m.PH_PROJECTS)
    )
    m.cost_components_annual.append('Pumped_Hydro_Fixed_Cost_Annual')
    
    # add the pumped hydro to the model's energy balance
    m.LZ_Energy_Components_Produce.append('GeneratePumpedHydro')
    m.LZ_Energy_Components_Consume.append('StorePumpedHydro')
    
    # total pumped hydro capacity in each zone each period (for reporting)
    m.Pumped_Hydro_Capacity_MW = Expression(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, pe:
        sum(m.Pumped_Hydro_Proj_Capacity_MW[pr, pe] for pr in m.PH_PROJECTS if m.ph_load_zone[pr]==z)
    )
        

def load_inputs(m, switch_data, inputs_dir):
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'pumped_hydro.tab'),
        autoselect=True,
        index=m.PH_PROJECTS,
        param=(
            m.ph_load_zone, m.ph_capital_cost_per_mw, m.ph_project_life, m.ph_fixed_om_percent,
            m.ph_efficiency, m.ph_inflow_mw, m.ph_max_capacity_mw))
        