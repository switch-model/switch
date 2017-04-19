"""
Defines types of reserve target and components that contribute to reserves,
and enforces the reserve targets.
"""
import os
from pyomo.environ import *


def define_components(m):
    """
    Note: In this simple model, we assume all reserves must be spinning. In more complex
    models you could define products and portions of those products that must be spinning,
    then use that to set the spinning reserve requirement.

    Reserves don't have a deliverability requirement, so they are calculated for the whole region.
    """

    # projects that can provide reserves
    # TODO: add batteries, hydrogen and pumped storage to this
    m.FIRM_GENECTS = Set(
        initialize=m.GENERATION_PROJECTS, 
        #filter=lambda m, p: m.gen_energy_source[p] not in ['Wind', 'Solar']
    )
    m.FIRM_GEN_TPS = Set(
        initialize=m.GEN_TPS, 
        filter=lambda m, p, tp: p in m.FIRM_GENECTS
    )
    m.CONTINGENCY_GENECTS = Set(
        initialize=m.GENERATION_PROJECTS, 
        filter=lambda m, p: p in m.DISCRETELY_SIZED_GENS
    )
    m.CONTINGENCY_GEN_TPS = Set(
        initialize=m.GEN_TPS, 
        filter=lambda m, p, tp: p in m.CONTINGENCY_GENECTS
    )
    
    # Calculate spinning reserve requirements.

    # these parameters were found by regressing the reserve requirements from the GE RPS Study
    # against wind and solar conditions each hour 
    # (see Dropbox/Research/Shared/Switch-Hawaii/ge_validation/source_data/reserve_requirements_oahu_scenarios charts.xlsx
    # and Dropbox/Research/Shared/Switch-Hawaii/ge_validation/fit_renewable_reserves.ipynb )
    # TODO: supply these parameters in input files

    # regulating reserves required, as fraction of potential output (up to limit)
    m.regulating_reserve_fraction = Param(['CentralTrackingPV', 'DistPV', 'OnshoreWind', 'OffshoreWind'], initialize={
        'CentralTrackingPV': 1.0,
        'DistPV': 1.0, # 0.81270193,
        'OnshoreWind': 1.0,
        'OffshoreWind': 1.0, # assumed equal to OnshoreWind
    })
    # maximum regulating reserves required, as fraction of installed capacity
    m.regulating_reserve_limit = Param(['CentralTrackingPV', 'DistPV', 'OnshoreWind', 'OffshoreWind'], initialize={
        'CentralTrackingPV': 0.21288916,
        'DistPV': 0.21288916, # 0.14153171,
        'OnshoreWind': 0.21624407,
        'OffshoreWind': 0.21624407, # assumed equal to OnshoreWind
    })
    # more conservative values (found by giving 10x weight to times when we provide less reserves than GE):
    # [1., 1., 1., 0.25760558, 0.18027923, 0.49123101]

    m.regulating_reserve_requirement_mw = Expression(m.TIMEPOINTS, rule=lambda m, tp: sum(
        m.GenCapacity[g, m.tp_period[tp]] 
        * min(
            m.regulating_reserve_fraction[m.gen_tech[g]] * m.gen_max_capacity_factor[g, tp], 
            m.regulating_reserve_limit[m.gen_tech[g]]
        )
            for g in m.GENERATION_PROJECTS 
                if m.gen_tech[g] in m.regulating_reserve_fraction and (g, tp) in m.GEN_TPS
    ))
    
    # Calculate contingency reserve requirements
    m.ContingencyReserveUpRequirement = Var(m.TIMEPOINTS, within=NonNegativeReals)
    # Apply a simple n-1 contingency reserve requirement; 
    # we treat each project as a separate contingency
    # Note: we provide reserves for the full committed amount of the project so that
    # if any of the capacity is being used for regulating reserves, that will be backed
    # up by contingency reserves.
    # TODO: convert this to a big-m constraint with the following elements:
    # binary on/off flag for each g, tp in CONTINGENCY_GEN_TPS
    # constraint that ProjDispatch[g, tp] <= binary * gen_max_capacity[g]
    # constraint that m.ContingencyReserveUpRequirement[tp] >= binary * m.gen_unit_size[g]
    # (but this may make the model too slow to solve!)
    m.CommitGenFlag = Var(m.CONTINGENCY_GEN_TPS, within=Binary)
    m.Set_CommitGenFlag = Constraint(
        m.CONTINGENCY_GEN_TPS,
        rule = lambda m, g, tp: 
            m.CommitGen[g, tp] <= m.CommitGenFlag[g, tp] * m.gen_capacity_limit_mw[g]
    )
    m.ContingencyReserveUpRequirement_Calculate = Constraint(
        m.CONTINGENCY_GEN_TPS, 
        rule=lambda m, g, tp: 
            # m.ContingencyReserveUpRequirement[tp] >= m.CommitGen[g, tp]
            m.ContingencyReserveUpRequirement[tp] >= m.CommitGenFlag[g, tp] * m.gen_unit_size[g]
    )
    
    # Calculate total spinning reserve requirement
    m.SpinningReserveUpRequirement = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        m.regulating_reserve_requirement_mw[tp] + m.ContingencyReserveUpRequirement[tp]
    )
    # require 10% down reserves at all times
    m.SpinningReserveDownRequirement = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        0.10 * sum(m.zone_demand_mw[z, tp] for z in m.LOAD_ZONES)
    )

def define_dynamic_components(m):
    # these are defined late, so they can check whether various components have been defined by other modules
    # TODO: create a central registry for components that contribute to reserves

    # Available reserves
    m.SpinningReservesUpAvailable = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        sum(m.DispatchSlackUp[p, tp] for p in m.FIRM_GENECTS if (p, tp) in m.GEN_TPS)
        + (
            sum(m.BatterySlackUp[z, tp] for z in m.LOAD_ZONES)
            if hasattr(m, 'BatterySlackDown')
            else 0.0
        )
        + (
            sum(m.HydrogenSlackUp[z, tp] for z in m.LOAD_ZONES) 
            if hasattr(m, 'HydrogenSlackUp') 
            else 0.0
        )
        + (
            sum(m.DemandUpReserves[z, tp] for z in m.LOAD_ZONES) 
            if hasattr(m, 'DemandUpReserves') 
            else 0.0
        )
        + (
            sum(m.ShiftDemand[z, tp] -  m.ShiftDemand[z, tp].lb for z in m.LOAD_ZONES) 
            if hasattr(m, 'ShiftDemand') 
            else 0.0
        )
        + (
            sum(m.ChargeEVs[z, tp] for z in m.LOAD_ZONES) 
            if hasattr(m, 'ChargeEVs') and hasattr(m.options, 'ev_timing') and m.options.ev_timing=='optimal'
            else 0.0
        )
    )
    m.SpinningReservesDownAvailable = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        sum(m.DispatchSlackDown[p, tp] for p in m.FIRM_GENECTS if (p, tp) in m.GEN_TPS)
        + (
            sum(m.BatterySlackDown[z, tp] for z in m.LOAD_ZONES)
            if hasattr(m, 'BatterySlackDown')
            else 0.0
        )
        + (
            sum(m.HydrogenSlackDown[z, tp] for z in m.LOAD_ZONES) 
            if hasattr(m, 'HydrogenSlackDown') 
            else 0.0
        )
        + (
            sum(m.DemandDownReserves[z, tp] for z in m.LOAD_ZONES) 
            if hasattr(m, 'DemandDownReserves') 
            else 0.0
        )
        # note: we currently ignore down-reserves (option of increasing consumption) 
        # from EVs and simple demand response, since it's not clear how high they could go
    )

    # Meet the reserve requirements
    m.Satisfy_Spinning_Reserve_Up_Requirement = Constraint(m.TIMEPOINTS, rule=lambda m, tp:
        m.SpinningReservesUpAvailable[tp] - m.SpinningReserveUpRequirement[tp] >= 0
    )
    m.Satisfy_Spinning_Reserve_Down_Requirement = Constraint(m.TIMEPOINTS, rule=lambda m, tp:
        m.SpinningReservesDownAvailable[tp] - m.SpinningReserveDownRequirement[tp] >= 0
    )
    

    # NOTE: the shutdown constraints below are not used, because they conflict with
    # the baseload status set in build_scenario_data.py. You should set the plant type
    # to "Off" in "source_data/Hawaii RPS Study Generator Table OCR.xlsx" instead.
    
    # # shutdown Kahe_6
    # m.KAHE_6_TIMEPOINTS = Set(initialize=lambda m: m.TPS_FOR_GEN['Kahe_6'])
    # m.ShutdownGenCapacity_Kahe_6 = Constraint(m.KAHE_6_TIMEPOINTS, rule=lambda m, tp:
    #     m.CommitGen['Kahe_6', tp] == 0
    # )

    # # shutdown Kahe_1 and Kahe_2
    # m.SHUTDOWN_TIMEPOINTS = Set(dimen=2, initialize=lambda m: [
    #     (p, tp) for p in ['Kahe_1', 'Kahe_2'] for tp in m.TPS_FOR_GEN[p]
    # ])
    # m.ShutdownGenCapacity_Projects = Constraint(m.SHUTDOWN_TIMEPOINTS, rule=lambda m, p, tp:
    #     m.CommitGen[p, tp] == 0
    # )
    
    # Force cycling plants to be online 0700-2000 and offline at other times
    # (based on inspection of Fig. 8)
    # project reporting types are defined in save_custom_results.py
    # Note: this assumes timepoints are evenly spaced, and timeseries begin at midnight
    # m.CYCLING_PLANTS_TIMEPOINTS = Set(dimen=2, initialize=lambda m: [
    #     (g, tp) for g in m.REPORTING_TYPE_GENECTS['Cycling']
    #         for tp in m.TPS_FOR_GEN[g]
    # ])
    # m.Cycle_Plants = Constraint(m.CYCLING_PLANTS_TIMEPOINTS, rule=lambda m, g, tp:
    #     m.CommitSlackUp[g, tp] == 0
    #         if (7 <= ((m.TPS_IN_TS[m.tp_ts[tp]].ord(tp)-1) * m.tp_duration_hrs[tp]) % 24 <= 20)
    #         else m.CommitGen[g, tp] == 0
    # )
    # def show_it(m):
    #     print "CYCLING_PLANTS_TIMEPOINTS:"
    #     print list(m.CYCLING_PLANTS_TIMEPOINTS)
    # m.ShowCyclingPlants = BuildAction(rule=show_it)

# def load_inputs(m, switch_data, inputs_dir):
#     switch_data.load_aug(
#         filename=os.path.join(inputs_dir, 'reserve_requirements.tab'),
#         auto_select=True,
#         param=(m.regulating_reserve_requirement_mw))


