# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to describe generation projects build-outs for
the SWITCH-Pyomo model. This module requires either generators.core.unitcommit or
generators.core.no_commit to constrain project dispatch to either committed or
installed capacity.

"""

import os, collections
from pyomo.environ import *
from switch_model.reporting import write_table
import pandas as pd
try:
    from ggplot import *
    can_plot = True
except:
    can_plot = False

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials', 'switch_model.energy_sources.properties', \
    'switch_model.generators.core.build'
optional_dependencies = 'switch_model.transmission.local_td'

def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe the
    dispatch decisions and constraints of generation and storage
    projects. Unless otherwise stated, all power capacity is specified
    in units of MW and all sets and parameters are mandatory.

    GEN_TPS is a set of projects and timepoints in which
    they can be dispatched. A dispatch decisions is made for each member
    of this set. Members of this set can be abbreviated as (g, t) or
    (g, t).
    
    TPS_FOR_GEN[g] is a set array showing all timepoints when a 
    project is active. These are the timepoints corresponding to 
    PERIODS_FOR_GEN. This is the same data as GEN_TPS, 
    but split into separate sets for each project.

    TPS_FOR_GEN_IN_PERIOD[g, period] is the same as 
    TPS_FOR_GEN, but broken down by period. Periods when
    the project is inactive will yield an empty set.

    GenCapacityInTP[(g, t) in GEN_TPS] is the same as
    GenCapacity but indexed by timepoint rather than period to allow
    more compact statements.

    DispatchGen[(g, t) in GEN_TPS] is the set
    of generation dispatch decisions: how much average power in MW to
    produce in each timepoint. This value can be multiplied by the
    duration of the timepoint in hours to determine the energy produced
    by a project in a timepoint.

    gen_forced_outage_rate[g] and gen_scheduled_outage_rate[g]
    describe the forces and scheduled outage rates for each project.
    These parameters can be specified for individual projects via an
    input file (see load_inputs() documentation), or generically for all
    projects of a given generation technology via
    g_scheduled_outage_rate and g_forced_outage_rate. You will get an
    error if any project is missing values for either of these
    parameters.

    gen_availability[g] describes the fraction of a time a project is
    expected to be available. This is derived from the forced and
    scheduled outage rates of the project. For baseload or flexible
    baseload, this is determined from both forced and scheduled outage
    rates. For all other types of generation technologies, we assume the
    scheduled outages can be performed when the generators were not
    scheduled to produce power, so their availability is only derated
    based on their forced outage rates.

    gen_max_capacity_factor[g, t] is defined for variable renewable
    projects and is the ratio of average power output to nameplate
    capacity in that timepoint. Most renewable capacity factors should
    be in the range of 0 to 1. Some solar capacity factors will be above
    1 because the nameplate capacity is based on solar radiation of 1.0
    kW/m^2 and solar radiation can exceed that value on very clear days
    or on partially cloudy days when light bounces off the bottom of
    clouds onto a solar panel. Some solar thermal capacity factors can
    be less than 0 because of auxillary loads: for example, parts of
    those plants need to be kept warm during winter nights to avoid
    freezing. Those heating loads can be significant during certain
    timepoints.

    gen_variable_om[g] is the variable Operations and Maintenance
    costs (O&M) per MWh of dispatched capacity for a given project.

    gen_full_load_heat_rate[g] is the full load heat rate in units
    of MMBTU/MWh that describes the thermal efficiency of a project when
    running at full load. This optional parameter overrides the generic
    heat rate of a generation technology. In the future, we may expand
    this to be indexed by fuel source as well if we need to support a
    multi-fuel generator whose heat rate depends on fuel source.

    Proj_Var_Costs_Hourly[t in TIMEPOINTS] is the sum of all variable
    costs associated with project dispatch for each timepoint expressed
    in $base_year/hour in the future period (rather than Net Present
    Value).

    _FUEL_BASED_GEN_TPS is a subset of GEN_TPS
    showing all times when fuel-consuming projects could be dispatched 
    (used to identify timepoints when fuel use must match power production).

    GEN_TP_FUELS is a subset of GEN_TPS * FUELS,
    showing all the valid combinations of project, timepoint and fuel,
    i.e., all the times when each project could consume a fuel that is 
    limited, costly or produces emissions.

    GenFuelUseRate[(g, t, f) in GEN_TP_FUELS] is a
    variable that describes fuel consumption rate in MMBTU/h. This
    should be constrained to the fuel consumed by a project in each
    timepoint and can be calculated as Dispatch [MW] *
    effective_heat_rate [MMBTU/MWh] -> [MMBTU/h]. The choice of how to
    constrain it depends on the treatment of unit commitment. Currently
    the project.no_commit module implements a simple treatment that
    ignores unit commitment and assumes a full load heat rate, while the
    project.unitcommit module implements unit commitment decisions with
    startup fuel requirements and a marginal heat rate.

    DispatchEmissions[(g, t, f) in GEN_TP_FUELS] is the
    emissions produced by dispatching a fuel-based project in units of
    metric tonnes CO2 per hour. This is derived from the fuel
    consumption GenFuelUseRate, the fuel's direct carbon intensity, the
    fuel's upstream emissions, as well as Carbon Capture efficiency for
    generators that implement Carbon Capture and Sequestration. This does
    not yet support multi-fuel generators.
    
    AnnualEmissions[p in PERIODS]:The system's annual emissions, in metric
    tonnes of CO2 per year.

    --- Delayed implementation, possibly relegated to other modules. ---

    Flexible baseload support for plants that can ramp slowly over the
    course of days. These kinds of generators can provide important
    seasonal support in high renewable and low emission futures.

    Parasitic loads that make solar thermal plants consume energy from
    the grid on cold nights to keep their fluids from getting too cold.

    Storage support.

    Hybrid project support (pumped hydro & CAES) will eventually get
    implemented in separate modules.

    """

    def period_active_gen_rule(m, period):
        if not hasattr(m, 'period_active_gen_dict'):
            m.period_active_gen_dict = collections.defaultdict(set)
            for (_g, _period) in m.GEN_PERIODS:
                m.period_active_gen_dict[_period].add(_g)
        result = m.period_active_gen_dict.pop(period)
        if len(m.period_active_gen_dict) == 0:
            delattr(m, 'period_active_gen_dict')
        return result
    mod.GENS_IN_PERIOD = Set(mod.PERIODS, initialize=period_active_gen_rule,
        doc="The set of projects active in a given period.")

    def TPS_FOR_GEN_rule(m, gen):
        if not hasattr(m, '_TPS_FOR_GEN_dict'):
            m._TPS_FOR_GEN_dict = collections.defaultdict(set)
            for (_gen, period) in m.GEN_PERIODS:
                for t in m.TPS_IN_PERIOD[period]:
                    m._TPS_FOR_GEN_dict[_gen].add(t)
        result = m._TPS_FOR_GEN_dict.pop(gen)
        if len(m._TPS_FOR_GEN_dict) == 0:
            delattr(m, '_TPS_FOR_GEN_dict')
        return result        
    mod.TPS_FOR_GEN = Set(
        mod.GENERATION_PROJECTS, within=mod.TIMEPOINTS,
        rule=TPS_FOR_GEN_rule)

    def TPS_FOR_GEN_IN_PERIOD_rule(m, gen, period):
        if not hasattr(m, '_TPS_FOR_GEN_IN_PERIOD_dict'):
            m._TPS_FOR_GEN_IN_PERIOD_dict = collections.defaultdict(set)
            for _gen in m.GENERATION_PROJECTS:
                for t in m.TPS_FOR_GEN[_gen]:
                    m._TPS_FOR_GEN_IN_PERIOD_dict[(_gen, m.tp_period[t])].add(t)
        if (gen, period) not in m._TPS_FOR_GEN_IN_PERIOD_dict:
            return ()
        result = m._TPS_FOR_GEN_IN_PERIOD_dict.pop((gen, period))
        if len(m._TPS_FOR_GEN_IN_PERIOD_dict) == 0:
            delattr(m, '_TPS_FOR_GEN_IN_PERIOD_dict')
        return result
    mod.TPS_FOR_GEN_IN_PERIOD = Set(mod.GENERATION_PROJECTS, mod.PERIODS, 
        within=mod.TIMEPOINTS,
        rule=TPS_FOR_GEN_IN_PERIOD_rule)

    mod.GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) 
                for g in m.GENERATION_PROJECTS 
                    for tp in m.TPS_FOR_GEN[g]))
    mod.VARIABLE_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) 
                for g in m.VARIABLE_GENS
                    for tp in m.TPS_FOR_GEN[g]))
    mod._FUEL_BASED_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) 
                for g in m.FUEL_BASED_GENS
                    for tp in m.TPS_FOR_GEN[g]))
    mod.GEN_TP_FUELS = Set(
        dimen=3,
        initialize=lambda m: (
            (g, t, f) 
                for (g, t) in m._FUEL_BASED_GEN_TPS 
                    for f in m.FUELS_FOR_GEN[g]))

    mod.GenCapacityInTP = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: m.GenCapacity[g, m.tp_period[t]])
    mod.DispatchGen = Var(
        mod.GEN_TPS,
        within=NonNegativeReals)
    mod.ZoneTotalCentralDispatch = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, z, t: \
            sum(m.DispatchGen[p, t]
                for p in m.GENS_IN_ZONE[z]
                if (p, t) in m.GEN_TPS and not m.gen_is_distributed[p]) -
            sum(m.DispatchGen[p, t] * m.gen_ccs_energy_load[p]
                for p in m.GENS_IN_ZONE[z]
                if (p, t) in m.GEN_TPS and p in m.CCS_EQUIPPED_GENS),
        doc="Net power from grid-tied generation projects.")
    mod.Zone_Power_Injections.append('ZoneTotalCentralDispatch')

    # Divide distributed generation into a separate expression so that we can
    # put it in the distributed node's power balance equations if local_td is
    # included.
    mod.ZoneTotalDistributedDispatch = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, z, t: \
            sum(m.DispatchGen[g, t]
                for g in m.GENS_IN_ZONE[z]
                if (g, t) in m.GEN_TPS and m.gen_is_distributed[g]),
        doc="Total power from distributed generation projects."
    )
    if 'Distributed_Power_Injections' in dir(mod):
        mod.Distributed_Power_Injections.append('ZoneTotalDistributedDispatch')
    else:
        mod.Zone_Power_Injections.append('ZoneTotalDistributedDispatch')

    def init_gen_availability(m, g):
        if m.gen_is_baseload[g]:
            return (
                (1 - m.gen_forced_outage_rate[g]) *
                (1 - m.gen_scheduled_outage_rate[g]))
        else:
            return (1 - m.gen_forced_outage_rate[g])
    mod.gen_availability = Param(
        mod.GENERATION_PROJECTS,
        within=PositiveReals,
        initialize=init_gen_availability)

    mod.gen_max_capacity_factor = Param(
        mod.VARIABLE_GEN_TPS,
        within=Reals,
        validate=lambda m, val, g, t: -1 < val < 2)
    mod.min_data_check('gen_max_capacity_factor')

    mod.GenFuelUseRate = Var(
        mod.GEN_TP_FUELS,
        within=NonNegativeReals,
        doc=("Other modules constraint this variable based on DispatchGen and "
             "module-specific formulations of unit commitment and heat rates."))

    def DispatchEmissions_rule(m, g, t, f):
        if g not in m.CCS_EQUIPPED_GENS:
            return (
                m.GenFuelUseRate[g, t, f] *
                (m.f_co2_intensity[f] + m.f_upstream_co2_intensity[f]))
        else:
            ccs_emission_frac = 1 - m.gen_ccs_capture_efficiency[g]
            return (
                m.GenFuelUseRate[g, t, f] *
                (m.f_co2_intensity[f] * ccs_emission_frac +
                 m.f_upstream_co2_intensity[f]))
    mod.DispatchEmissions = Expression(
        mod.GEN_TP_FUELS,
        rule=DispatchEmissions_rule)
    mod.AnnualEmissions = Expression(mod.PERIODS,
        rule=lambda m, period: sum(
            m.DispatchEmissions[g, t, f] * m.tp_weight_in_year[t]
            for (g, t, f) in m.GEN_TP_FUELS
            if m.tp_period[t] == period),
        doc="The system's annual emissions, in metric tonnes of CO2 per year.")

    mod.GenVariableOMCostsInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.DispatchGen[g, t] * m.gen_variable_om[g]
            for g in m.GENS_IN_PERIOD[m.tp_period[t]]),
        doc="Summarize costs for the objective function")
    mod.Cost_Components_Per_TP.append('GenVariableOMCostsInTP')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import project-specific data from an input directory.

    variable_capacity_factors can be skipped if no variable
    renewable projects are considered in the optimization.

    variable_capacity_factors.tab
        GENERATION_PROJECT, timepoint, gen_max_capacity_factor

    """

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'variable_capacity_factors.tab'),
        autoselect=True,
        param=(mod.gen_max_capacity_factor))


def post_solve(instance, outdir):
    """
    Exported files:
    
    dispatch-wide.txt - Dispatch results timepoints in "wide" format with
    timepoints as rows, generation projects as columns, and dispatch level
    as values
    
    dispatch.csv - Dispatch results in normalized form where each row 
    describes the dispatch of a generation project in one timepoint.
    
    dispatch_annual_summary.csv - Similar to dispatch.csv, but summarized
    by generation technology and period.
    
    dispatch_zonal_annual_summary.csv - Similar to dispatch_annual_summary.csv
    but broken out by load zone. 
    
    dispatch_annual_summary.pdf - A figure of annual summary data. Only written
    if the ggplot python library is installed.
    """
    write_table(
        instance, instance.TIMEPOINTS,
        output_file=os.path.join(outdir, "dispatch-wide.txt"),
        headings=("timestamp",)+tuple(sorted(instance.GENERATION_PROJECTS)),
        values=lambda m, t: (m.tp_timestamp[t],) + tuple(
            m.DispatchGen[p, t] if (p, t) in m.GEN_TPS
            else 0.0
            for p in sorted(m.GENERATION_PROJECTS)
        )
    )


    dispatch_normalized_dat = [{
        "generation_project": g,
        "gen_dbid": instance.gen_dbid[g],
        "gen_tech": instance.gen_tech[g],
        "gen_load_zone": instance.gen_load_zone[g],
        "gen_energy_source": instance.gen_energy_source[g],
        "timestamp": instance.tp_timestamp[t], 
        "tp_weight_in_year_hrs": instance.tp_weight_in_year[t],
        "period": instance.tp_period[t],
        "DispatchGen_MW": value(instance.DispatchGen[g, t]),
        "Energy_GWh_typical_yr": value(
            instance.DispatchGen[g, t] * instance.tp_weight_in_year[t] / 1000),
        "VariableCost_per_yr": value(
            instance.DispatchGen[g, t] * instance.gen_variable_om[g] * 
            instance.tp_weight_in_year[t]),
        "DispatchEmissions_tCO2_per_typical_yr": value(sum(
            instance.DispatchEmissions[g, t, f] * instance.tp_weight_in_year[t]
              for f in instance.FUELS_FOR_GEN[g]
        )) if instance.gen_uses_fuel[g] else 0
    } for g, t in instance.GEN_TPS ]
    dispatch_full_df = pd.DataFrame(dispatch_normalized_dat)
    dispatch_full_df.set_index(["generation_project", "timestamp"], inplace=True)
    dispatch_full_df.to_csv(os.path.join(outdir, "dispatch.csv"))
        

    annual_summary = dispatch_full_df.groupby(['gen_tech', "gen_energy_source", "period"]).sum()
    annual_summary.to_csv(
        os.path.join(outdir, "dispatch_annual_summary.csv"),
        columns=["Energy_GWh_typical_yr", "VariableCost_per_yr", 
                 "DispatchEmissions_tCO2_per_typical_yr"])


    zonal_annual_summary = dispatch_full_df.groupby(
        ['gen_tech', "gen_load_zone", "gen_energy_source", "period"]
    ).sum()
    zonal_annual_summary.to_csv(
        os.path.join(outdir, "dispatch_zonal_annual_summary.csv"),
        columns=["Energy_GWh_typical_yr", "VariableCost_per_yr", 
                 "DispatchEmissions_tCO2_per_typical_yr"]
    )
    
    if can_plot:
        annual_summary_plot = ggplot(
                annual_summary.reset_index(), 
                aes(x='period', weight="Energy_GWh_typical_yr", fill="factor(gen_tech)")
            ) + \
            geom_bar(position="stack") + \
            scale_y_continuous(name='Energy (GWh/yr)') + theme_bw()
        annual_summary_plot.save(filename=os.path.join(outdir, "dispatch_annual_summary.pdf"))
