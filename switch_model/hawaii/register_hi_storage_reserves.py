"""
Defines types of reserve target and components that contribute to reserves,
and enforces the reserve targets.
"""
import os
from pyomo.environ import *

# TODO: use standard reserves module for this
# note: this is modeled off of hawaii.reserves, to avoid adding lots of
# reserve-related code to the pumped storage and (formerly) hydrogen modules.
# But eventually those modules should use the standard storage module and
# extend that as needed.

def define_arguments(argparser):
    argparser.add_argument('--hawaii-storage-reserve-types', nargs='+', default=['spinning'],
        help=
            "Type(s) of reserves to provide from " # hydrogen and/or
            "pumped-hydro storage "
            "(e.g., 'contingency regulation'). "
            "Default is generic 'spinning'. Specify 'none' to disable."
    )

def define_components(m):

    if [rt.lower() for rt in m.options.hawaii_storage_reserve_types] != ['none']:
        if hasattr(m, 'PumpedHydroProjGenerateMW'):
            m.PumpedStorageCharging = Var(m.PH_GENS, m.TIMEPOINTS, within=Binary)
            m.Set_PumpedStorageCharging_Flag = Constraint(m.PH_GENS, m.TIMEPOINTS, rule=lambda m, phg, tp:
                m.PumpedHydroProjGenerateMW[phg, tp]
                <=
                m.ph_max_capacity_mw[phg] * (1 - m.PumpedStorageCharging[phg, tp])
            )
            # choose how much pumped storage reserves to provide each hour, without reversing direction
            m.PumpedStorageSpinningUpReserves = Var(m.PH_GENS, m.TIMEPOINTS, within=NonNegativeReals)
            m.Limit_PumpedStorageSpinningUpReserves_When_Charging = Constraint(
                m.PH_GENS, m.TIMEPOINTS,
                rule=lambda m, phg, tp:
                    m.PumpedStorageSpinningUpReserves[phg, tp]
                    <=
                    m.PumpedHydroProjStoreMW[phg, tp]
                    + m.ph_max_capacity_mw[phg] * (1 - m.PumpedStorageCharging[phg, tp]) # relax when discharging
            )
            m.Limit_PumpedStorageSpinningUpReserves_When_Discharging = Constraint(
                m.PH_GENS, m.TIMEPOINTS,
                rule=lambda m, phg, tp:
                    m.PumpedStorageSpinningUpReserves[phg, tp]
                    <=
                    m.Pumped_Hydro_Proj_Capacity_MW[phg, m.tp_period[tp]] - m.PumpedHydroProjGenerateMW[phg, tp]
                    + m.ph_max_capacity_mw[phg] * m.PumpedStorageCharging[phg, tp] # relax when charging
            )
            m.PumpedStorageSpinningDownReserves = Var(m.PH_GENS, m.TIMEPOINTS, within=NonNegativeReals, bounds=(0,0))
            m.Limit_PumpedStorageSpinningDownReserves_When_Charging = Constraint(
                m.PH_GENS, m.TIMEPOINTS,
                rule=lambda m, phg, tp:
                    m.PumpedStorageSpinningDownReserves[phg, tp]
                    <=
                    m.Pumped_Hydro_Proj_Capacity_MW[phg, m.tp_period[tp]] - m.PumpedHydroProjStoreMW[phg, tp]
                    + m.ph_max_capacity_mw[phg] * (1 - m.PumpedStorageCharging[phg, tp]) # relax when discharging
            )
            m.Limit_PumpedStorageSpinningDownReserves_When_Discharging = Constraint(
                m.PH_GENS, m.TIMEPOINTS,
                rule=lambda m, phg, tp:
                    m.PumpedStorageSpinningDownReserves[phg, tp]
                    <=
                    m.PumpedHydroProjGenerateMW[phg, tp]
                    + m.ph_max_capacity_mw[phg] * m.PumpedStorageCharging[phg, tp] # relax when charging
            )

        # Register with spinning reserves
        if hasattr(m, 'Spinning_Reserve_Up_Provisions'): # using spinning_reserves_advanced
            # calculate available slack from hawaii storage
            def up_expr(m, a, tp):
                avail = 0.0
                # now handled in hydrogen module:
                # if hasattr(m, 'HydrogenSlackUp'):
                #     avail += sum(m.HydrogenSlackUp[z, tp] for z in m.ZONES_IN_BALANCING_AREA[a])
                if hasattr(m, 'PumpedStorageSpinningUpReserves'):
                    avail += sum(
                        m.PumpedStorageSpinningUpReserves[phg, tp]
                        for phg in m.PH_GENS
                        if m.ph_load_zone[phg] in m.ZONES_IN_BALANCING_AREA[a]
                    )
                return avail
            m.HawaiiStorageSlackUp = Expression(m.BALANCING_AREA_TIMEPOINTS, rule=up_expr)
            def down_expr(m, a, tp):
                avail = 0.0
                # if hasattr(m, 'HydrogenSlackDown'):
                #     avail += sum(m.HydrogenSlackDown[z, tp] for z in m.ZONES_IN_BALANCING_AREA[a])
                if hasattr(m, 'PumpedStorageSpinningDownReserves'):
                    avail += sum(
                        m.PumpedStorageSpinningDownReserves[phg, tp]
                        for phg in m.PH_GENS
                        if m.ph_load_zone[phg] in m.ZONES_IN_BALANCING_AREA[a]
                    )
                return avail
            m.HawaiiStorageSlackDown = Expression(m.BALANCING_AREA_TIMEPOINTS, rule=down_expr)

            if hasattr(m, 'GEN_SPINNING_RESERVE_TYPES'):
                # using advanced formulation, index by reserve type, balancing area, timepoint
                # define variables for each type of reserves to be provided
                # choose how to allocate the slack between the different reserve products
                m.HI_STORAGE_SPINNING_RESERVE_TYPES = Set(
                    initialize=m.options.hawaii_storage_reserve_types
                )
                m.HawaiiStorageSpinningReserveUp = Var(
                    m.HI_STORAGE_SPINNING_RESERVE_TYPES, m.BALANCING_AREA_TIMEPOINTS,
                    within=NonNegativeReals
                )
                m.HawaiiStorageSpinningReserveDown = Var(
                    m.HI_STORAGE_SPINNING_RESERVE_TYPES, m.BALANCING_AREA_TIMEPOINTS,
                    within=NonNegativeReals
                )
                # constrain reserve provision within available slack
                m.Limit_HawaiiStorageSpinningReserveUp = Constraint(
                    m.BALANCING_AREA_TIMEPOINTS,
                    rule=lambda m, ba, tp:
                        sum(
                            m.HawaiiStorageSpinningReserveUp[rt, ba, tp]
                            for rt in m.HI_STORAGE_SPINNING_RESERVE_TYPES
                        ) <= m.HawaiiStorageSlackUp[ba, tp]
                )
                m.Limit_HawaiiStorageSpinningReserveDown = Constraint(
                    m.BALANCING_AREA_TIMEPOINTS,
                    rule=lambda m, ba, tp:
                        sum(
                            m.HawaiiStorageSpinningReserveDown[rt, ba, tp]
                            for rt in m.HI_STORAGE_SPINNING_RESERVE_TYPES
                        ) <= m.HawaiiStorageSlackDown[ba, tp]
                )
                m.Spinning_Reserve_Up_Provisions.append('HawaiiStorageSpinningReserveUp')
                m.Spinning_Reserve_Down_Provisions.append('HawaiiStorageSpinningReserveDown')
            else:
                # using older formulation, only one type of spinning reserves, indexed by balancing area, timepoint
                if m.options.hawaii_storage_reserve_types != ['spinning']:
                    raise ValueError(
                        'Unable to use reserve types other than "spinning" with simple spinning reserves module.'
                    )
                m.Spinning_Reserve_Up_Provisions.append('HawaiiStorageSlackUp')
                m.Spinning_Reserve_Down_Provisions.append('HawaiiStorageSlackDown')
