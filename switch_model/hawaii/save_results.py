"""Save results of current model in customized files.

Add this module to a standard SWITCH model, and the post_solve() callback will
be called automatically to store results.
"""

# TODO: eventually make this code more generic, e.g., create a general reporting module
# with functions like
# add_report(report_name, indexes, reporting_times=["post_iterate", "post_solve"], restart_times=["scenario batch", "scenario", "iteration"])
# add_columns(report_name, headers, value_rule)
# Then re-create the file with the right headers at each restart time
# (with a name reflecting the degree of generality for restart and reporting)
# Then add the rows of data at each reporting time.
# The reporting module could also define some or all of the reports below as standard reports.
# There could also be a drop_report() function or command line argument to prevent generating
# some of the standard reports or even reports defined by some of the loaded modules.
# (But generally we may want custom modules just to report their own results? Or maybe all
# standard modules add columns to the standard reports?)
# These definitions should be stored in model.config, so maybe the reporting functions should be
# added as methods (possibly by util rather than a separate reporting module).

import os
from collections import defaultdict
from pyomo.environ import *
import switch_model.hawaii.util as util
import switch_model.financials as financials

def define_components(m):
    # Make sure the model has a dual suffix
    if not hasattr(m, "dual"):
        m.dual = Suffix(direction=Suffix.IMPORT)

def post_solve(m, outputs_dir):
    write_results(m, outputs_dir)

def summary_headers(m):
    return (
        ("scenario", "max_demand_response_share", "total_cost", "cost_per_kwh")
        +tuple('cost_per_kwh_'+str(p) for p in m.PERIODS)
        +((("renewable_share_all_years",) + tuple('renewable_share_'+str(p) for p in m.PERIODS))
            if hasattr(m, 'RPSEligiblePower') else tuple())
        +((("biofuel_share_all_years",) + tuple('biofuel_share_'+str(p) for p in m.PERIODS))
            if hasattr(m, 'RPSEligiblePower') else tuple())
    )

def summary_values(m):
    demand_components = [c for c in ('zone_demand_mw', 'ShiftDemand', 'ChargeEVs') if hasattr(m, c)]
    values = []

    # Cache SystemCostPerPeriod and SystemCost to speed up saving large models
    # The time needed to directly access the expressions seems to rise quadratically
    # with the number of timepoints, so it gets very slow for big models and we don't
    # want to repeat it if possible (e.g., without caching, this function takes up
    # to an hour for an 8760 Oahu model)
    SystemCostPerPeriod = dict()
    for p in m.PERIODS:
        SystemCostPerPeriod[p] = value(m.SystemCostPerPeriod[p])
    SystemCost = sum(SystemCostPerPeriod[p] for p in m.PERIODS)

    # scenario name and looping variables
    values.extend([
        str(m.options.scenario_name),
        m.demand_response_max_share if hasattr(m, 'demand_response_max_share') else 0.0,
    ])

    # total cost (all periods)
    values.append(SystemCost) # m.SystemCost)

    # NPV of total cost / NPV of kWh generated (equivalent to spreading
    # all costs uniformly over all generation)
    values.append(
        SystemCost # m.SystemCost
        / sum(
            m.bring_timepoint_costs_to_base_year[t] * 1000.0 *
            sum(getattr(m, c)[z, t] for c in demand_components for z in m.LOAD_ZONES)
            for t in m.TIMEPOINTS
        )
    )

    #  total cost / kWh generated in each period
    # (both discounted to today, so the discounting cancels out)
    values.extend([
        SystemCostPerPeriod[p] # m.SystemCostPerPeriod[p]
        / sum(
            m.bring_timepoint_costs_to_base_year[t] * 1000.0 *
            sum(getattr(m, c)[z, t] for c in demand_components for z in m.LOAD_ZONES)
            for t in m.TPS_IN_PERIOD[p]
        )
        for p in m.PERIODS
    ])

    if hasattr(m, 'RPSEligiblePower'):
        # total renewable share over all periods
        values.append(
            sum(m.RPSEligiblePower[p] for p in m.PERIODS)
            /sum(m.RPSTotalPower[p] for p in m.PERIODS)
        )
        # renewable share during each period
        values.extend([m.RPSEligiblePower[p]/m.RPSTotalPower[p] for p in m.PERIODS])
        # total biofuel share over all periods
        values.append(
            sum(m.RPSFuelPower[p] for p in m.PERIODS)
            /sum(m.RPSTotalPower[p] for p in m.PERIODS)
        )
        # biofuel share during each period
        values.extend([m.RPSFuelPower[p]/m.RPSTotalPower[p] for p in m.PERIODS])

    return values

def annualize_present_value_period_cost(m, period, val):
    # convert a discounted, total cost per-period into an annual stream of costs
    discount_factor = (
        # this term is straight from financials.py
        # Conversion to lump sum at beginning of period
        financials.uniform_series_to_present_value(
            m.discount_rate, m.period_length_years[period]) *
        # Conversion to base year
        financials.future_to_present_value(
            m.discount_rate, (m.period_start[period] - m.base_financial_year))
    )
    return val / discount_factor

def DispatchGenByFuel(m, g, tp, fuel):
    """This is a replacement for mod.DispatchGenByFuel, which is only defined in
    project.no_commit, not project.unitcommit.fuel_use. In the unit commitment version
    it can only be defined as a quadratically constrained variable, which we don't
    want to force on all users."""
    if (g, tp) in m.DispatchGen:
        dispatch = value(m.DispatchGen[g, tp])
        total_fuel = value(sum(m.GenFuelUseRate[g, tp, f] for f in m.FUELS_FOR_GEN[g]))
    else:
        dispatch = 0.0
        total_fuel = 0.0

    if dispatch == 0.0:
        result = 0.0
    elif total_fuel == 0.0:
        # power produced, but no fuel used (e.g., steam generator on combined-cycle plant).
        # allocate evenly between fuels that could be used (should really be allocated the
        # same as the upstream generator, e.g., CT in combined-cycle plant, but we don't
        # know that allocation here).
        result = dispatch / len(m.FUELS_FOR_GEN[g])
    else:
        # allocate power production proportional to amount of each fuel used
        result = value(m.GenFuelUseRate[g, tp, fuel]) * dispatch / total_fuel
    return result

def write_results(m, outputs_dir):
    tag = "_" + m.options.scenario_name if m.options.scenario_name else ""

    util.write_table(m,
        output_file=os.path.join(outputs_dir, "summary{t}.tsv".format(t=tag)),
        headings=summary_headers(m),
        values=lambda m: summary_values(m)
    )

    if hasattr(m, 'Spinning_Reserve_Up_Requirements'):
        # pre-calculate amount of reserves provided and needed for each balancing area and timepoint
        spinning_reserve_provisions = defaultdict(float)
        spinning_reserve_requirements = defaultdict(float)
        if hasattr(m, 'GEN_SPINNING_RESERVE_TYPES'): # advanced module
            for component in m.Spinning_Reserve_Up_Provisions:
                for (rt, ba, tp), val in getattr(m, component).items():
                    spinning_reserve_provisions[ba, tp] += val
            for component in m.Spinning_Reserve_Up_Requirements:
                for (rt, ba, tp), val in getattr(m, component).items():
                    spinning_reserve_requirements[ba, tp] += val
        else: # basic module
            for component in m.Spinning_Reserve_Up_Provisions:
                for (ba, tp), val in getattr(m, component).items():
                    spinning_reserve_provisions[ba, tp] += val
            for component in m.Spinning_Reserve_Up_Requirements:
                for (ba, tp), val in getattr(m, component).items():
                    spinning_reserve_requirements[ba, tp] += val

    # # write out results
    # util.write_table(m, m.TIMEPOINTS,
    #     output_file=os.path.join(outputs_dir, "dispatch{t}.tsv".format(t=tag)),
    #     headings=("timepoint_label",)+tuple(m.GENERATION_PROJECTS),
    #     values=lambda m, t: (m.tp_timestamp[t],) + tuple(
    #         util.get(m.DispatchGen, (p, t), 0.0)
    #         for p in m.GENERATION_PROJECTS
    #     )
    # )

    # get a list of non-fuel technologies, to allow disaggregation by type
    non_fuel_techs = tuple(sorted(set(m.gen_tech[g] for g in m.NON_FUEL_BASED_GENS)))
    # get a list of ad-hoc technologies (not included in standard generation projects)
    ad_hoc_sources = tuple(
        s for s in m.Zone_Power_Injections
        if s not in {'ZoneTotalCentralDispatch', 'ZoneTotalDistributedDispatch'}
    )
    avg_ts_scale = float(sum(m.ts_scale_to_year[ts] for ts in m.TIMESERIES))/len(m.TIMESERIES)
    util.write_table(
        m, m.LOAD_ZONES, m.TIMEPOINTS,
        output_file=os.path.join(outputs_dir, "energy_sources{t}.tsv".format(t=tag)),
        headings=
            ("load_zone", "period", "timepoint_label")
            +tuple(m.FUELS)
            +tuple(m.NON_FUEL_ENERGY_SOURCES)
            +non_fuel_techs
            +tuple("curtail_"+s for s in m.NON_FUEL_ENERGY_SOURCES)
            +tuple(m.Zone_Power_Injections)
            +tuple(m.Zone_Power_Withdrawals)
            +("spinning_reserve_provision", "spinning_reserve_requirement")
            +("marginal_cost", "peak_day"),
        values=lambda m, z, t:
            (z, m.tp_period[t], m.tp_timestamp[t])
            +tuple(
                sum(
                    DispatchGenByFuel(m, p, t, f)
                        for p in m.GENS_BY_FUEL[f]
                        if (p, t) in m.GEN_TPS and m.gen_load_zone[p] == z
                )
                for f in m.FUELS
            )
            +tuple(
                sum(
                    util.get(m.DispatchGen, (p, t), 0.0)
                    for p in m.GENS_BY_NON_FUEL_ENERGY_SOURCE[s]
                    if m.gen_load_zone[p] == z
                )
                for s in m.NON_FUEL_ENERGY_SOURCES
            )
            +tuple(
                sum(
                    util.get(m.DispatchGen, (g, t), 0.0)
                    for g in m.GENS_BY_TECHNOLOGY[tech]
                    if m.gen_load_zone[g] == z
                )
                for tech in non_fuel_techs
            )
            +tuple(
                sum(
                    util.get(m.DispatchUpperLimit, (p, t), 0.0) - util.get(m.DispatchGen, (p, t), 0.0)
                    for p in m.GENS_BY_NON_FUEL_ENERGY_SOURCE[s]
                    if m.gen_load_zone[p] == z
                )
                for s in m.NON_FUEL_ENERGY_SOURCES
            )
            +tuple(getattr(m, component)[z, t] for component in m.Zone_Power_Injections)
            +tuple(getattr(m, component)[z, t] for component in m.Zone_Power_Withdrawals)
            +(  # save spinning reserve requirements and provisions; note: this assumes one zone per balancing area
                (spinning_reserve_provisions[m.zone_balancing_area[z], t], spinning_reserve_requirements[m.zone_balancing_area[z], t])
                if hasattr(m, 'Spinning_Reserve_Up_Requirements')
                else (0.0, 0.0)
            )
            +(util.get(m.dual, m.Zone_Energy_Balance[z, t], 0.0)/m.bring_timepoint_costs_to_base_year[t],
                # note: this uses 0.0 if no dual available, i.e., with glpk solver
            'peak' if m.ts_scale_to_year[m.tp_ts[t]] < avg_ts_scale else 'typical')
    )

    if hasattr(m, 'Spinning_Reserve_Up_Requirements') and hasattr(m, 'GEN_SPINNING_RESERVE_TYPES'): # advanced module
        # write the reserve values
        util.write_table(
            m, m.BALANCING_AREAS, m.TIMEPOINTS,
            output_file=os.path.join(outputs_dir, "up_reserve_sources{t}.tsv".format(t=tag)),
            headings=
                ("balancing_area", "period", "timepoint_label")
                +tuple(m.FUELS)
                +tuple(m.NON_FUEL_ENERGY_SOURCES)
                +tuple(m.Spinning_Reserve_Up_Provisions)
                +tuple(m.Spinning_Reserve_Up_Requirements)
                +tuple("marginal_cost_"+rt for rt in m.SPINNING_RESERVE_TYPES_FROM_GENS)
                +("peak_day",),
            values=lambda m, ba, t:
                (ba, m.tp_period[t], m.tp_timestamp[t])
                +tuple(
                    (
                        sum(
                            # total reserve production
                            sum(
                                m.CommitGenSpinningReservesUp[rt, p, t]
                                for rt in m.SPINNING_RESERVE_TYPES_FOR_GEN[p]
                            )
                            # prorated by energy source used
                            * DispatchGenByFuel(m, p, t, f) / m.DispatchGen[p, t]
                            for p in m.GENS_BY_FUEL[f]
                            if (p, t) in m.GEN_TPS and m.zone_balancing_area[m.gen_load_zone[p]] == ba
                        )
                    )
                    for f in m.FUELS
                )
                +tuple(
                    sum(
                        m.CommitGenSpinningReservesUp[rt, p, t]
                        for p in m.GENS_BY_NON_FUEL_ENERGY_SOURCE[s]
                        if (p, t) in m.SPINNING_RESERVE_CAPABLE_GEN_TPS and m.zone_balancing_area[m.gen_load_zone[p]] == ba
                        for rt in m.SPINNING_RESERVE_TYPES_FOR_GEN[p]
                    )
                    for s in m.NON_FUEL_ENERGY_SOURCES
                )
                +tuple(
                    sum(util.get(getattr(m, component), (rt, ba, t), 0.0) for rt in m.SPINNING_RESERVE_TYPES_FROM_GENS)
                    for component in m.Spinning_Reserve_Up_Provisions
                )
                +tuple(
                    sum(util.get(getattr(m, component), (rt, ba, t), 0.0) for rt in m.SPINNING_RESERVE_TYPES_FROM_GENS)
                    for component in m.Spinning_Reserve_Up_Requirements
                )
                +tuple(
                    util.get(
                        m.dual,
                        util.get(m.Satisfy_Spinning_Reserve_Up_Requirement, (rt, ba, t), None),
                        0.0  # note: this uses 0.0 if no dual available, i.e., with glpk solver
                    ) / m.bring_timepoint_costs_to_base_year[t]
                    for rt in m.SPINNING_RESERVE_TYPES_FROM_GENS
                )
                +(('peak' if m.ts_scale_to_year[m.tp_ts[t]] < avg_ts_scale else 'typical'),)
        )

    sorted_projects = tuple(sorted(g for g in m.GENERATION_PROJECTS))
    util.write_table(
        m, m.TIMEPOINTS,
        output_file=os.path.join(outputs_dir, "gen_dispatch{t}.tsv".format(t=tag)),
        headings=("period", "timepoint_label")+sorted_projects,
        values=lambda m, t:
            (m.tp_period[t], m.tp_timestamp[t])
            + tuple(util.get(m.DispatchGen, (p, t), 0.0) for p in sorted_projects)
    )

    # installed capacity information
    def gen_energy_source(g):
        return (
            '/'.join(sorted(m.FUELS_FOR_GEN[g]))
            if m.gen_uses_fuel[g]
            else m.gen_energy_source[g]
        )
    built_gens = tuple(sorted(set(
        g for pe in m.PERIODS for g in m.GENERATION_PROJECTS if value(m.GenCapacity[g, pe]) > 0.001
    )))
    active_periods_for_gen = defaultdict(set)
    used_cap = getattr(m, 'CommitGen', m.DispatchGen) # use CommitGen if available, otherwise DispatchGen
    for (g, tp) in m.GEN_TPS:
        if value(used_cap[g, tp]) > 0.001:
            active_periods_for_gen[g].add(m.tp_period[tp])
    # add the periods between the first and last active period if capacity was available then
    operate_gen_in_period = set()
    for g, active_periods in active_periods_for_gen.items():
        start = min(active_periods)
        end = max(active_periods)
        for p in m.PERIODS:
            if start <= p <= end and value(m.GenCapacity[g, p]) > 0:
                operate_gen_in_period.add((g, p))

    built_tech = tuple(sorted(set(m.gen_tech[g] for g in built_gens)))
    built_energy_source = tuple(sorted(set(gen_energy_source(g) for g in built_gens)))

    battery_capacity_mw = lambda m, z, pe: (
        (m.Battery_Capacity[z, pe] / m.battery_min_discharge_time)
            if hasattr(m, "Battery_Capacity") else 0.0
    )

    util.write_table(m, m.LOAD_ZONES, m.PERIODS,
        output_file=os.path.join(outputs_dir, "capacity_by_technology{t}.tsv".format(t=tag)),
        headings=("load_zone", "period") + built_tech + ("hydro", "batteries", "fuel cells"),
        values=lambda m, z, pe: (z, pe,) + tuple(
            sum(
                (m.GenCapacity[g, pe] if ((g, pe) in operate_gen_in_period) else 0.0)
                    for g in built_gens
                        if m.gen_tech[g] == t and m.gen_load_zone[g] == z
            )
            for t in built_tech
        ) + (
            m.Pumped_Hydro_Capacity_MW[z, pe] if hasattr(m, "Pumped_Hydro_Capacity_MW") else 0,
            battery_capacity_mw(m, z, pe),
            m.FuelCellCapacityMW[z, pe] if hasattr(m, "FuelCellCapacityMW") else 0
        )
    )
    util.write_table(m, m.LOAD_ZONES, m.PERIODS,
        output_file=os.path.join(outputs_dir, "capacity_by_energy_source{t}.tsv".format(t=tag)),
        headings=("load_zone", "period") + built_energy_source + ("hydro", "batteries", "fuel cells"),
        values=lambda m, z, pe: (z, pe,) + tuple(
            sum(
                (m.GenCapacity[g, pe] if ((g, pe) in operate_gen_in_period) else 0.0)
                    for g in built_gens
                        if gen_energy_source(g) == s and m.gen_load_zone[g] == z
            )
            for s in built_energy_source
        ) + (
            m.Pumped_Hydro_Capacity_MW[z, pe] if hasattr(m, "Pumped_Hydro_Capacity_MW") else 0,
            battery_capacity_mw(m, z, pe),
            m.FuelCellCapacityMW[z, pe] if hasattr(m, "FuelCellCapacityMW") else 0
        )
    )

    util.write_table(m, m.LOAD_ZONES, m.PERIODS,
        output_file=os.path.join(outputs_dir, "production_by_technology{t}.tsv".format(t=tag)),
        headings=("load_zone", "period") + built_tech + ad_hoc_sources,
        values=lambda m, z, pe:
            (z, pe,)
            + tuple(
                sum(
                    m.DispatchGen[g, tp] * m.tp_weight_in_year[tp] * 0.001 # MWh -> GWh
                    for g in built_gens if m.gen_tech[g] == t and m.gen_load_zone[g] == z
                    for tp in m.TPS_FOR_GEN_IN_PERIOD[g, pe]
                )
                for t in built_tech
            )
            + tuple(  # ad hoc techs: hydrogen, pumped storage, etc.
                sum(
                    comp[z, tp] * m.tp_weight_in_year[tp] * 0.001
                    for tp in m.TPS_IN_PERIOD[pe]
                )
                for comp in [getattr(m, cname) for cname in ad_hoc_sources]
            )
    )

    # option 1: make separate tables of production_by_technology and production_by_energy_source,
    # and use columns from production_by_technology to replace corresponding columns from
    # production_by_energy_source in order to disaggregate certain energy sources.
    # option 2: make a single table that shows production by technology and energy source
    # (sub slices); but this has to either have two heading levels or concatenate them or
    # use a database format rather than a table format, which will then require post-processing
    # by pandas or an Excel pivot table.
    # For now, we go with option 1.
    util.write_table(m, m.LOAD_ZONES, m.PERIODS,
        output_file=os.path.join(outputs_dir, "production_by_energy_source{t}.tsv".format(t=tag)),
        headings=
            ("load_zone", "period")
            + tuple(m.FUELS)
            + tuple(m.NON_FUEL_ENERGY_SOURCES)
            + ad_hoc_sources,
        values=lambda m, z, pe:
            (z, pe,)
            + tuple(
                sum(
                    DispatchGenByFuel(m, g, tp, f) * m.tp_weight_in_year[tp] * 0.001 # MWh -> GWh
                    for g in m.GENS_BY_FUEL[f]
                    if m.gen_load_zone[g] == z
                    for tp in m.TPS_FOR_GEN_IN_PERIOD[g, pe]
                )
                for f in m.FUELS
            )
            + tuple(
                sum(
                    m.DispatchGen[g, tp] * m.tp_weight_in_year[tp] * 0.001 # MWh -> GWh
                    for g in m.GENS_BY_NON_FUEL_ENERGY_SOURCE[s]
                    if m.gen_load_zone[g] == z
                    for tp in m.TPS_FOR_GEN_IN_PERIOD[g, pe]
                )
                for s in m.NON_FUEL_ENERGY_SOURCES
            )
            + tuple(  # ad hoc techs: hydrogen, pumped storage, etc.
                sum(
                    comp[z, tp] * m.tp_weight_in_year[tp] * 0.001
                    for tp in m.TPS_IN_PERIOD[pe]
                )
                for comp in [getattr(m, cname) for cname in ad_hoc_sources]
            )
    )



    # def cost_breakdown_details(m, z, pe):
    #     values = [z, pe]
    #     # capacity built, conventional plants
    #
    #     values += [
    #         sum(
    #             m.BuildGen[g, pe]
    #                 for g in built_gens
    #                     if m.gen_tech[g] == t and m.gen_load_zone[g] == z and (g, pe) in m.BuildGen
    #         )
    #         for t in built_tech
    #     ]
    #     # capacity built, batteries, MW and MWh
    #     if hasattr(m, "BuildBattery"):
    #         values.extend([
    #             m.BuildBattery[z, pe]/m.battery_min_discharge_time,
    #             m.BuildBattery[z, pe]
    #         ])
    #     else:
    #         values.extend([0.0, 0.0])
    #     # capacity built, hydro
    #     values.append(
    #         sum(
    #             m.BuildPumpedHydroMW[g, pe]
    #                 for g in m.PH_GENS if m.ph_load_zone[g]==z
    #         ) if hasattr(m, "BuildPumpedHydroMW") else 0.0,
    #     )
    #     # capacity built, hydrogen
    #     if hasattr(m, "BuildElectrolyzerMW"):
    #         values.extend([
    #             m.BuildElectrolyzerMW[z, pe],
    #             m.BuildLiquifierKgPerHour[z, pe],
    #             m.BuildLiquidHydrogenTankKg[z, pe],
    #             m.BuildFuelCellMW[z, pe]
    #         ])
    #     else:
    #         values.extend([0.0, 0.0, 0.0, 0.0])
    #
    #     # number of EVs and conventional vehicles
    #     if hasattr(m, 'ev_share'):
    #         values.append(m.n_all_vehicles[z, pe] * m.ev_share[z, pe])
    #         values.append(m.n_all_vehicles[z, pe] * (1.0 - m.ev_share[z, pe]))
    #         # import pdb; pdb.set_trace()
    #
    #     # capital investments
    #     # regular projects
    #     values += [
    #         sum(
    #             m.BuildGen[g, pe] * (m.gen_overnight_cost[g, pe] + m.gen_connect_cost_per_mw[g])
    #                 for g in built_gens
    #                     if m.gen_tech[g] == t and m.gen_load_zone[g] == z \
    #                         and (g, pe) in m.GEN_BLD_YRS
    #         )
    #         for t in built_tech
    #     ]
    #     # batteries
    #     if hasattr(m, 'battery_capital_cost_per_mwh_capacity'):
    #         # models with single capital cost (defunct)
    #         values.append(m.BuildBattery[z, pe] * m.battery_capital_cost_per_mwh_capacity)
    #     elif hasattr(m, 'battery_capital_cost_per_mwh_capacity_by_year'):
    #         values.append(m.BuildBattery[z, pe] * m.battery_capital_cost_per_mwh_capacity_by_year[pe])
    #     else:
    #         values.append(0.0)
    #     # hydro
    #     values.append(
    #         sum(
    #             m.BuildPumpedHydroMW[g, pe] * m.ph_capital_cost_per_mw[g]
    #                 for g in m.PH_GENS if m.ph_load_zone[g]==z
    #         ) if hasattr(m, "BuildPumpedHydroMW") else 0.0,
    #     )
    #     # hydrogen
    #     if hasattr(m, "BuildElectrolyzerMW"):
    #         values.extend([
    #             m.BuildElectrolyzerMW[z, pe] * m.hydrogen_electrolyzer_capital_cost_per_mw,
    #             m.BuildLiquifierKgPerHour[z, pe] * m.hydrogen_liquifier_capital_cost_per_kg_per_hour,
    #             m.BuildLiquidHydrogenTankKg[z, pe] * m.liquid_hydrogen_tank_capital_cost_per_kg,
    #             m.BuildFuelCellMW[z, pe] * m.hydrogen_fuel_cell_capital_cost_per_mw
    #         ])
    #     else:
    #         values.extend([0.0, 0.0, 0.0, 0.0])
    #
    #     # _annual_ fuel expenditures
    #     if hasattr(m, "REGIONAL_FUEL_MARKETS"):
    #         values.extend([
    #             sum(m.ConsumeFuelTier[rfm_st] * m.rfm_supply_tier_cost[rfm_st] for rfm_st in m.SUPPLY_TIERS_FOR_RFM_PERIOD[rfm, pe])
    #                 for rfm in m.REGIONAL_FUEL_MARKETS
    #         ])
    #     # costs to expand fuel markets (this could later be disaggregated by market and tier)
    #     if hasattr(m, "RFM_Fixed_Costs_Annual"):
    #         values.append(m.RFM_Fixed_Costs_Annual[pe])
    #     # TODO: add similar code for fuel_costs module instead of fuel_markets module
    #
    #     # total cost per period
    #     values.append(annualize_present_value_period_cost(m, pe, m.SystemCostPerPeriod[pe]))
    #
    #     #  total cost per year for transport
    #     if hasattr(m, "ev_extra_annual_cost"):
    #         values.append(m.ev_extra_annual_cost[pe])
    #         values.append(m.ice_annual_fuel_cost[pe])
    #
    #     return values
    #
    # util.write_table(m, m.LOAD_ZONES, m.PERIODS,
    #     output_file=os.path.join(outputs_dir, "cost_breakdown{t}.tsv".format(t=tag)),
    #     headings=("load_zone", "period") + tuple(t+"_mw_added" for t in built_tech)
    #         + ("batteries_mw_added", "batteries_mwh_added", "hydro_mw_added")
    #         + ( "h2_electrolyzer_mw_added", "h2_liquifier_kg_per_hour_added",
    #             "liquid_h2_tank_kg_added", "fuel_cell_mw_added")
    #         + (('ev_count', 'ice_count') if hasattr(m, 'ev_share') else ())
    #         + tuple(t+"_overnight_cost" for t in built_tech)
    #         + ("batteries_overnight_cost", "hydro_overnight_cost")
    #         + ( "h2_electrolyzer_overnight_cost", "h2_liquifier_overnight_cost",
    #             "liquid_h2_tank_overnight_cost", "fuel_cell_overnight_cost")
    #         + (tuple(rfm+"_annual_cost" for rfm in m.REGIONAL_FUEL_MARKETS)
    #                 if hasattr(m, "REGIONAL_FUEL_MARKETS") else ())
    #         + (("fuel_market_expansion_annual_cost",)
    #                 if hasattr(m, "RFM_Fixed_Costs_Annual") else ())
    #         + ('total_electricity_cost',)
    #         + (('ev_extra_capital_recovery',)
    #                 if hasattr(m, 'ev_extra_annual_cost') else ())
    #         + (('ice_annual_fuel_cost',) if hasattr(m, 'ice_annual_fuel_cost') else ()),
    #     values=cost_breakdown_details
    # )

    # util.write_table(m, m.PERIODS,
    #     output_file=os.path.join(outputs_dir, "capacity{t}.tsv".format(t=t)),
    #     headings=("period",)+built_gens,
    #     values=lambda m, pe: (pe,) + tuple(m.GenCapacity[g, pe] for g in built_gens)
    # )


    if hasattr(m, 'RFMSupplyTierActivate'):
        util.write_table(m, m.RFM_SUPPLY_TIERS,
            output_file=os.path.join(outputs_dir, "rfm_activate{t}.tsv".format(t=tag)),
            headings=("market", "period", "tier", "activate"),
            values=lambda m, r, p, st: (r, p, st, m.RFMSupplyTierActivate[r, p, st])
        )


    # import pprint
    # b=[(g, pe, value(m.BuildGen[g, pe]), m.gen_tech[g], m.gen_overnight_cost[g, pe]) for (g, pe) in m.BuildGen if value(m.BuildGen[g, pe]) > 0]
    # bt=set(x[3] for x in b) # technologies
    # pprint([(t, sum(x[2] for x in b if x[3]==t), sum(x[4] for x in b if x[3]==t)/sum(1.0 for x in b if x[3]==t)) for t in bt])
