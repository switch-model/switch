import os
from pyomo.environ import *
from switch_model.financials import capital_recovery_factor as crf

def define_arguments(argparser):
    argparser.add_argument("--ph-mw", type=float, default=None,
        help="Force construction of a certain total capacity of pumped storage hydro during one or more periods chosen by SWITCH")
    argparser.add_argument("--ph-year", type=int, default=None,
        help="Force all pumped storage hydro to be constructed during one particular year (must be in the list of periods)")    

def define_components(m):
    
    m.PH_GENS = Set()
    
    m.ph_load_zone = Param(m.PH_GENS)
    
    m.ph_capital_cost_per_mw = Param(m.PH_GENS, within=NonNegativeReals)
    m.ph_gect_life = Param(m.PH_GENS, within=NonNegativeReals)
    
    # annual O&M cost for pumped hydro project, percent of capital cost
    m.ph_fixed_om_percent = Param(m.PH_GENS, within=NonNegativeReals)
    
    # total annual cost
    m.ph_fixed_cost_per_mw_per_year = Param(m.PH_GENS, initialize=lambda m, p:
        m.ph_capital_cost_per_mw[p] * 
            (crf(m.interest_rate, m.ph_gect_life[p]) + m.ph_fixed_om_percent[p])
    )
    
    # round-trip efficiency of the pumped hydro facility
    m.ph_efficiency = Param(m.PH_GENS)
    
    # average energy available from water inflow each day
    # (system must balance energy net of this each day)
    m.ph_inflow_mw = Param(m.PH_GENS)
    
    # maximum size of pumped hydro project
    m.ph_max_capacity_mw = Param(m.PH_GENS)
    
    # How much pumped hydro to build
    m.BuildPumpedHydroMW = Var(m.PH_GENS, m.PERIODS, within=NonNegativeReals)
    m.Pumped_Hydro_Proj_Capacity_MW = Expression(m.PH_GENS, m.PERIODS, rule=lambda m, g, pe:
        sum(m.BuildPumpedHydroMW[g, pp] for pp in m.CURRENT_AND_PRIOR_PERIODS[pe])
    )

    # flag indicating whether any capacity is added to each project each year
    m.BuildAnyPumpedHydro = Var(m.PH_GENS, m.PERIODS, within=Binary)    

    # How to run pumped hydro
    m.PumpedHydroProjGenerateMW = Var(m.PH_GENS, m.TIMEPOINTS, within=NonNegativeReals)
    m.PumpedHydroProjStoreMW = Var(m.PH_GENS, m.TIMEPOINTS, within=NonNegativeReals)

    # constraints on construction of pumped hydro

    # don't build more than the max allowed capacity
    m.Pumped_Hydro_Max_Build = Constraint(m.PH_GENS, m.PERIODS, rule=lambda m, g, pe:
        m.Pumped_Hydro_Proj_Capacity_MW[g, pe] <= m.ph_max_capacity_mw[g]
    )
    
    # force the build flag on for the year(s) when pumped hydro is built
    m.Pumped_Hydro_Set_Build_Flag = Constraint(m.PH_GENS, m.PERIODS, rule=lambda m, g, pe:
        m.BuildPumpedHydroMW[g, pe] <= m.BuildAnyPumpedHydro[g, pe] * m.ph_max_capacity_mw[g]
    )
    # only build in one year (can be deactivated to allow incremental construction)
    m.Pumped_Hydro_Build_Once = Constraint(m.PH_GENS, rule=lambda m, g:
        sum(m.BuildAnyPumpedHydro[g, pe] for pe in m.PERIODS) <= 1)
    # only build full project size (deactivated by default, to allow smaller projects)
    m.Pumped_Hydro_Build_All_Or_None = Constraint(m.PH_GENS, m.PERIODS, rule=lambda m, g, pe:
        m.BuildPumpedHydroMW[g, pe] == m.BuildAnyPumpedHydro[g, pe] * m.ph_max_capacity_mw[g]
    )
    # m.Deactivate_Pumped_Hydro_Build_All_Or_None = BuildAction(rule=lambda m:
    #     m.Pumped_Hydro_Build_All_Or_None.deactivate()
    # )
    
    # limits on pumping and generation
    m.Pumped_Hydro_Max_Generate_Rate = Constraint(m.PH_GENS, m.TIMEPOINTS, rule=lambda m, g, t:
        m.PumpedHydroProjGenerateMW[g, t]
        <=
        m.Pumped_Hydro_Proj_Capacity_MW[g, m.tp_period[t]]
    )
    m.Pumped_Hydro_Max_Store_Rate = Constraint(m.PH_GENS, m.TIMEPOINTS, rule=lambda m, g, t:
        m.PumpedHydroProjStoreMW[g, t]
        <=
        m.Pumped_Hydro_Proj_Capacity_MW[g, m.tp_period[t]]
    )

    # return reservoir to at least the starting level every day, net of any inflow
    # it can also go higher than starting level, which indicates spilling surplus water
    m.Pumped_Hydro_Daily_Balance = Constraint(m.PH_GENS, m.TIMESERIES, rule=lambda m, g, ts:
        sum(
            m.PumpedHydroProjStoreMW[g, tp] * m.ph_efficiency[g]
            + m.ph_inflow_mw[g]
            - m.PumpedHydroProjGenerateMW[g, tp]
            for tp in m.TPS_IN_TS[ts]
         ) >= 0
    )

    m.GeneratePumpedHydro = Expression(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        sum(m.PumpedHydroProjGenerateMW[g, t] for g in m.PH_GENS if m.ph_load_zone[g]==z)
    )
    m.StorePumpedHydro = Expression(m.LOAD_ZONES, m.TIMEPOINTS, rule=lambda m, z, t:
        sum(m.PumpedHydroProjStoreMW[g, t] for g in m.PH_GENS if m.ph_load_zone[g]==z)
    )
    
    # calculate costs
    m.Pumped_Hydro_Fixed_Cost_Annual = Expression(m.PERIODS, rule=lambda m, pe:
        sum(m.ph_fixed_cost_per_mw_per_year[g] * m.Pumped_Hydro_Proj_Capacity_MW[g, pe] for g in m.PH_GENS)
    )
    m.Cost_Components_Per_Period.append('Pumped_Hydro_Fixed_Cost_Annual')
    
    # add pumped hydro to zonal energy balance
    m.Zone_Power_Injections.append('GeneratePumpedHydro')
    m.Zone_Power_Withdrawals.append('StorePumpedHydro')
    
    # total pumped hydro capacity in each zone each period (for reporting)
    m.Pumped_Hydro_Capacity_MW = Expression(m.LOAD_ZONES, m.PERIODS, rule=lambda m, z, pe:
        sum(m.Pumped_Hydro_Proj_Capacity_MW[g, pe] for g in m.PH_GENS if m.ph_load_zone[g]==z)
    )
        
    # force construction of a fixed amount of pumped hydro
    if m.options.ph_mw is not None:
        print "Forcing construction of {m} MW of pumped hydro.".format(m=m.options.ph_mw)
        m.Build_Pumped_Hydro_MW = Constraint(m.LOAD_ZONES, rule=lambda m, z:
            m.Pumped_Hydro_Capacity_MW[z, m.PERIODS.last()] == m.options.ph_mw
        )
    # force construction of pumped hydro only in a certain period
    if m.options.ph_year is not None:
        print "Allowing construction of pumped hydro only in {p}.".format(p=m.options.ph_year)
        m.Build_Pumped_Hydro_Year = Constraint(
            m.PH_GENS, m.PERIODS,
            rule=lambda m, g, pe:
                m.BuildPumpedHydroMW[g, pe] == 0.0 if pe != m.options.ph_year else Constraint.Skip
        )


def load_inputs(m, switch_data, inputs_dir):
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'pumped_hydro.tab'),
        autoselect=True,
        index=m.PH_GENS,
        param=(
            m.ph_load_zone, m.ph_capital_cost_per_mw, m.ph_gect_life, m.ph_fixed_om_percent,
            m.ph_efficiency, m.ph_inflow_mw, m.ph_max_capacity_mw))
        