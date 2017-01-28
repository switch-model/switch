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
    m.FIRM_PROJECTS = Set(
        initialize=m.PROJECTS, 
        #filter=lambda m, p: m.proj_energy_source[p] not in ['Wind', 'Solar']
    )
    m.FIRM_PROJ_DISPATCH_POINTS = Set(
        initialize=m.PROJ_DISPATCH_POINTS, 
        filter=lambda m, p, tp: p in m.FIRM_PROJECTS
    )
    m.CONTINGENCY_PROJECTS = Set(
        initialize=m.PROJECTS, 
        filter=lambda m, p: p in m.PROJECTS_WITH_UNIT_SIZES
    )
    m.CONTINGENCY_PROJ_DISPATCH_POINTS = Set(
        initialize=m.PROJ_DISPATCH_POINTS, 
        filter=lambda m, p, tp: p in m.CONTINGENCY_PROJECTS
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
        m.ProjCapacity[pr, m.tp_period[tp]] 
        * min(
            m.regulating_reserve_fraction[m.proj_gen_tech[pr]] * m.proj_max_capacity_factor[pr, tp], 
            m.regulating_reserve_limit[m.proj_gen_tech[pr]]
        )
            for pr in m.PROJECTS 
                if m.proj_gen_tech[pr] in m.regulating_reserve_fraction and (pr, tp) in m.PROJ_DISPATCH_POINTS
    ))
    
    # Calculate contingency reserve requirements
    m.ContingencyReserveUpRequirement = Var(m.TIMEPOINTS, within=NonNegativeReals)
    # Apply a simple n-1 contingency reserve requirement; 
    # we treat each project as a separate contingency
    # Note: we provide reserves for the full committed amount of the project so that
    # if any of the capacity is being used for regulating reserves, that will be backed
    # up by contingency reserves.
    # TODO: convert this to a big-m constraint with the following elements:
    # binary on/off flag for each pr, tp in CONTINGENCY_PROJ_DISPATCH_POINTS
    # constraint that ProjDispatch[pr, tp] <= binary * proj_max_capacity[pr]
    # constraint that m.ContingencyReserveUpRequirement[tp] >= binary * m.proj_unit_size[pr]
    # (but this may make the model too slow to solve!)
    m.CommitProjectFlag = Var(m.CONTINGENCY_PROJ_DISPATCH_POINTS, within=Binary)
    m.Set_CommitProjectFlag = Constraint(
        m.CONTINGENCY_PROJ_DISPATCH_POINTS,
        rule = lambda m, pr, tp: 
            m.CommitProject[pr, tp] <= m.CommitProjectFlag[pr, tp] * m.proj_capacity_limit_mw[pr]
    )
    m.ContingencyReserveUpRequirement_Calculate = Constraint(
        m.CONTINGENCY_PROJ_DISPATCH_POINTS, 
        rule=lambda m, pr, tp: 
            # m.ContingencyReserveUpRequirement[tp] >= m.CommitProject[pr, tp]
            m.ContingencyReserveUpRequirement[tp] >= m.CommitProjectFlag[pr, tp] * m.proj_unit_size[pr]
    )
    
    # Calculate total spinning reserve requirement
    m.SpinningReserveUpRequirement = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        m.regulating_reserve_requirement_mw[tp] + m.ContingencyReserveUpRequirement[tp]
    )
    # require 10% down reserves at all times
    m.SpinningReserveDownRequirement = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        0.10 * sum(m.lz_demand_mw[z, tp] for z in m.LOAD_ZONES)
    )

def define_dynamic_components(m):
    # these are defined late, so they can check whether various components have been defined by other modules
    # TODO: create a central registry for components that contribute to reserves

    # Available reserves
    m.SpinningReservesUpAvailable = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        sum(m.DispatchSlackUp[p, tp] for p in m.FIRM_PROJECTS if (p, tp) in m.PROJ_DISPATCH_POINTS)
        + (
            sum(m.BatterySlackUp[lz, tp] for lz in m.LOAD_ZONES)
            if hasattr(m, 'BatterySlackDown')
            else 0.0
        )
        + (
            sum(m.HydrogenSlackUp[lz, tp] for lz in m.LOAD_ZONES) 
            if hasattr(m, 'HydrogenSlackUp') 
            else 0.0
        )
        + (
            sum(m.DemandUpReserves[lz, tp] for lz in m.LOAD_ZONES) 
            if hasattr(m, 'DemandUpReserves') 
            else 0.0
        )
        + (
            sum(m.DemandResponse[lz, tp] -  m.DemandResponse[lz, tp].lb for lz in m.LOAD_ZONES) 
            if hasattr(m, 'DemandResponse') 
            else 0.0
        )
        + (
            sum(m.ChargeEVs[lz, tp] for lz in m.LOAD_ZONES) 
            if hasattr(m, 'ChargeEVs') and hasattr(m.options, 'ev_timing') and m.options.ev_timing=='optimal'
            else 0.0
        )
    )
    m.SpinningReservesDownAvailable = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        sum(m.DispatchSlackDown[p, tp] for p in m.FIRM_PROJECTS if (p, tp) in m.PROJ_DISPATCH_POINTS)
        + (
            sum(m.BatterySlackDown[lz, tp] for lz in m.LOAD_ZONES)
            if hasattr(m, 'BatterySlackDown')
            else 0.0
        )
        + (
            sum(m.HydrogenSlackDown[lz, tp] for lz in m.LOAD_ZONES) 
            if hasattr(m, 'HydrogenSlackDown') 
            else 0.0
        )
        + (
            sum(m.DemandDownReserves[lz, tp] for lz in m.LOAD_ZONES) 
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
    # m.KAHE_6_TIMEPOINTS = Set(initialize=lambda m: m.PROJ_ACTIVE_TIMEPOINTS['Kahe_6'])
    # m.Shutdown_Kahe_6 = Constraint(m.KAHE_6_TIMEPOINTS, rule=lambda m, tp:
    #     m.CommitProject['Kahe_6', tp] == 0
    # )

    # # shutdown Kahe_1 and Kahe_2
    # m.SHUTDOWN_TIMEPOINTS = Set(dimen=2, initialize=lambda m: [
    #     (p, tp) for p in ['Kahe_1', 'Kahe_2'] for tp in m.PROJ_ACTIVE_TIMEPOINTS[p]
    # ])
    # m.Shutdown_Projects = Constraint(m.SHUTDOWN_TIMEPOINTS, rule=lambda m, p, tp:
    #     m.CommitProject[p, tp] == 0
    # )
    
    # Force cycling plants to be online 0700-2000 and offline at other times
    # (based on inspection of Fig. 8)
    # project reporting types are defined in save_custom_results.py
    # Note: this assumes timepoints are evenly spaced, and timeseries begin at midnight
    # m.CYCLING_PLANTS_TIMEPOINTS = Set(dimen=2, initialize=lambda m: [
    #     (pr, tp) for pr in m.REPORTING_TYPE_PROJECTS['Cycling']
    #         for tp in m.PROJ_ACTIVE_TIMEPOINTS[pr]
    # ])
    # m.Cycle_Plants = Constraint(m.CYCLING_PLANTS_TIMEPOINTS, rule=lambda m, pr, tp:
    #     m.CommitSlackUp[pr, tp] == 0
    #         if (7 <= ((m.TS_TPS[m.tp_ts[tp]].ord(tp)-1) * m.tp_duration_hrs[tp]) % 24 <= 20)
    #         else m.CommitProject[pr, tp] == 0
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


