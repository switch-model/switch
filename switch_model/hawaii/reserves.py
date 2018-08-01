"""
Defines types of reserve target and components that contribute to reserves,
and enforces the reserve targets.
"""
import os
from pyomo.environ import *

# TODO: use standard reserves module for this

def define_arguments(argparser):
    argparser.add_argument('--reserves-from-storage', action='store_true', default=True, 
        help="Allow storage (batteries and hydrogen) to provide up- and down-reserves.")
    argparser.add_argument('--no-reserves-from-storage', dest='reserves_from_storage', 
        action='store_false', 
        help="Don't allow storage (batteries and hydrogen) to provide up- and down-reserves.")
    argparser.add_argument('--reserves-from-demand-response', action='store_true', default=True, 
        help="Allow demand response to provide up- and down-reserves.")
    argparser.add_argument('--no-reserves-from-demand-response', dest='reserves_from_demand_response', 
        action='store_false', 
        help="Don't allow demand response to provide up- and down-reserves.")

def define_components(m):
    """
    Note: In this simple model, we assume all reserves must be spinning. In more complex
    models you could define products and portions of those products that must be spinning,
    then use that to set the spinning reserve requirement.

    Reserves don't have a deliverability requirement, so they are calculated for the whole region.
    """

    # projects that can provide reserves
    # TODO: add batteries, hydrogen and pumped storage to this
    m.FIRM_GENS = Set(
        initialize=m.GENERATION_PROJECTS, 
        #filter=lambda m, p: m.gen_energy_source[p] not in ['Wind', 'Solar']
    )
    m.FIRM_GEN_TPS = Set(
        initialize=m.GEN_TPS, 
        filter=lambda m, p, tp: p in m.FIRM_GENS
    )
    m.CONTINGENCY_GENS = Set(
        initialize=m.GENERATION_PROJECTS, 
        filter=lambda m, p: p in m.DISCRETELY_SIZED_GENS
    )
    m.CONTINGENCY_GEN_TPS = Set(
        initialize=m.GEN_TPS, 
        filter=lambda m, p, tp: p in m.CONTINGENCY_GENS
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

    m.RegulatingReserveRequirementMW = Expression(m.TIMEPOINTS, rule=lambda m, tp: sum(
        m.GenCapacity[g, m.tp_period[tp]] 
        * min(
            m.regulating_reserve_fraction[m.gen_tech[g]] * m.gen_max_capacity_factor[g, tp], 
            m.regulating_reserve_limit[m.gen_tech[g]]
        )
            for g in m.GENERATION_PROJECTS 
                if m.gen_tech[g] in m.regulating_reserve_fraction and (g, tp) in m.GEN_TPS
    ))
    
def define_dynamic_components(m):
    # these are defined late, so they can check whether various components have been defined by other modules
    # TODO: create a central registry for components that contribute to reserves

    # Calculate contingency reserve requirements
    m.ContingencyReserveUpRequirement = Var(m.TIMEPOINTS, within=NonNegativeReals)
    # Apply a simple n-1 contingency reserve requirement; 
    # we treat each project as a separate contingency
    # Note: we provide reserves for the full committed amount of each unit so that
    # if any of the capacity is being used for regulating reserves, that will be backed
    # up by contingency reserves.
    # note: this uses a binary run/no-run flag, so it only provides one unit's worth of reserves
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

    m.ContingencyReserveDownRequirement = Var(m.TIMEPOINTS, within=NonNegativeReals)
    # For now, we provide down reserves equal to 10% of all loads, including 
    # baseline load, demand response adjustment, electric vehicles, battery charging
    # and hydrogen. It would be possible to split these into centralized and distributed
    # loads and allocate separately for them (e.g., contingency reserves exceed 
    # 10% of total decentralized load and the size of the contingency for each 
    # centralized load; however, it's not obvious how to set the contingency for
    # centralized loads, which are modular and may be divided between several locations.
    # So we just assume we could lose 10% of all loads of any type, at any time.)
    m.ContingencyReserveDownRequirement_Calculate = Constraint(
        m.TIMEPOINTS, 
        rule=lambda m, tp: 
            m.ContingencyReserveDownRequirement[tp] >= 
            0.1 * sum(getattr(m, x)[z, tp] for x in m.Zone_Power_Withdrawals for z in m.LOAD_ZONES)
    )
    
    # Calculate total spinning reserve requirements
    m.SpinningReserveUpRequirement = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        m.RegulatingReserveRequirementMW[tp] + m.ContingencyReserveUpRequirement[tp]
    )
    m.SpinningReserveDownRequirement = Expression(m.TIMEPOINTS, rule=lambda m, tp:
        m.ContingencyReserveDownRequirement[tp]
    )


    # Available reserves
    def expr(m, tp):
        STORAGE_GENS = getattr(m, 'STORAGE_GENS', [])
        # all regular generators; omit storage because they'll be added separately if needed
        avail = sum(
            m.DispatchSlackUp[g, tp] 
            for g in m.FIRM_GENS 
            if (g, tp) in m.GEN_TPS and g not in STORAGE_GENS
        )
        if m.options.reserves_from_storage:
            # hawaii battery and hydrogen modules
            if hasattr(m, 'BatterySlackUp'):
                avail += sum(m.BatterySlackUp[z, tp] for z in m.LOAD_ZONES)
            if hasattr(m, 'HydrogenSlackUp'):
                avail += sum(m.HydrogenSlackUp[z, tp] for z in m.LOAD_ZONES)
            # standard storage module (can stop charging and raise output to max)
            avail += sum(
                m.DispatchSlackUp[g, tp] + m.ChargeStorage[g, tp]
                for g in STORAGE_GENS 
                if (g, tp) in m.GEN_TPS
            )
        if m.options.reserves_from_demand_response:
            if hasattr(m, 'DemandUpReserves'):
                avail += sum(m.DemandUpReserves[z, tp] for z in m.LOAD_ZONES) 
            if hasattr(m, 'ShiftDemand'):
                avail += sum(m.ShiftDemand[z, tp] -  m.ShiftDemand[z, tp].lb for z in m.LOAD_ZONES) 
            if hasattr(m, 'ChargeEVs') and hasattr(m.options, 'ev_timing') and m.options.ev_timing=='optimal':
                avail += sum(m.ChargeEVs[z, tp] for z in m.LOAD_ZONES) 
        if hasattr(m, 'UnservedUpReserves'):
            avail += m.UnservedUpReserves[tp]
        # if tp == 2045012604:
        #     print "inspect avail to see up reserve calculation"
        #     import pdb; pdb.set_trace()
        return avail
    m.SpinningReservesUpAvailable = Expression(m.TIMEPOINTS, rule=expr)
    def expr(m, tp):
        STORAGE_GENS = getattr(m, 'STORAGE_GENS', [])
        # all regular generators; omit storage because they'll be added separately if needed    
        avail = sum(
            m.DispatchSlackDown[g, tp] 
            for g in m.FIRM_GENS 
            if (g, tp) in m.GEN_TPS and g not in STORAGE_GENS
        )
        if m.options.reserves_from_storage:
            if hasattr(m, 'BatterySlackDown'):
                avail += sum(m.BatterySlackDown[z, tp] for z in m.LOAD_ZONES)
            if hasattr(m, 'HydrogenSlackDown'):
                avail += sum(m.HydrogenSlackDown[z, tp] for z in m.LOAD_ZONES)
            # standard storage module (can stop producing power and raise charging to max)
            avail += sum(
                m.DispatchSlackDown[g, tp] 
                + m.DispatchUpperLimit[g, tp] * m.gen_store_to_release_ratio[g]
                - m.ChargeStorage[g, tp]
                for g in STORAGE_GENS 
                if (g, tp) in m.GEN_TPS
            )
            
        if m.options.reserves_from_demand_response:
            if hasattr(m, 'DemandDownReserves'):
                avail += sum(m.DemandDownReserves[z, tp] for z in m.LOAD_ZONES)
            if hasattr(m, 'ShiftDemand'):
                # avail += sum(m.ShiftDemand[z, tp].ub - m.ShiftDemand[z, tp] for z in m.LOAD_ZONES) 
                avail += sum(
                    24/3 * m.demand_response_max_share * m.zone_demand_mw[z, tp]
                    - m.ShiftDemand[z, tp] 
                    for z in m.LOAD_ZONES
                ) 
            # note: we currently ignore down-reserves (option of increasing consumption) 
            # from EVs since it's not clear how high they could go; we could revisit this if
            # down-reserves have a positive price at equilibrium (probabably won't)
        if hasattr(m, 'UnservedDownReserves'):
            avail += m.UnservedDownReserves[tp]
        return avail
    m.SpinningReservesDownAvailable = Expression(m.TIMEPOINTS, rule=expr)

    # Meet the reserve requirements (we use zero on RHS to enforce the right sign for the duals)
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
    #     (g, tp) for g in m.REPORTING_TYPE_GENS['Cycling']
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
#         param=(m.RegulatingReserveRequirementMW))


