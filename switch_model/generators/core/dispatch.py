# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to describe generation projects build-outs for
the Switch model. This module requires either generators.core.unitcommit or
generators.core.no_commit to constrain project dispatch to either committed or
installed capacity.

"""
from __future__ import division

import os, collections

from pyomo.environ import *
import pandas as pd

from switch_model.reporting import write_table
from switch_model.tools.graph import graph

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.financials",
    "switch_model.energy_sources.properties",
    "switch_model.generators.core.build",
)
optional_dependencies = "switch_model.transmission.local_td"


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

    DispatchGenByFuel[(g, t, f) in GEN_TP_FUELS] is the power
    production in MW by each fuel-based project from each fuel during each timepoint.
    This is constrained such that the sum over all fuels gives
    DispatchGen.

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

    FUEL_BASED_GEN_TPS is a subset of GEN_TPS
    showing all times when fuel-consuming projects could be dispatched
    (used to identify timepoints when fuel use must match power production).

    GEN_TP_FUELS is a subset of GEN_TPS * FUELS,
    showing all the valid combinations of project, timepoint and fuel,
    i.e., all the times when each project could consume a fuel that is
    limited, costly or produces emissions.

    GenFuelUseRate[(g, t, f) in GEN_TP_FUELS] is a
    variable that describes fuel consumption rate in MMBTU/h. This
    should be constrained to the fuel consumed by a project in each
    timepoint and can be calculated as DispatchGenByFuel [MW] *
    effective_heat_rate [MMBTU/MWh] -> [MMBTU/h]. The choice of how to
    constrain it depends on the treatment of unit commitment. Currently
    the project.no_commit module implements a simple treatment that
    ignores unit commitment and assumes a full load heat rate, while the
    project.unitcommit module implements unit commitment decisions with
    startup fuel requirements and a marginal heat rate.

    DispatchEmissions[(g, t, f) in GEN_TP_FUELS] is the CO2
    emissions produced by dispatching a fuel-based project in units of
    metric tonnes CO2 per hour. This is derived from the fuel
    consumption GenFuelUseRate, the fuel's direct carbon intensity, the
    fuel's upstream emissions, as well as Carbon Capture efficiency for
    generators that implement Carbon Capture and Sequestration. This does
    not yet support multi-fuel generators.

    DispatchEmissionsNOx[(g, t, f) in GEN_TP_FUELS],
    DispatchEmissionsSO2[(g, t, f) in GEN_TP_FUELS], and
    DispatchEmissionsCH4[(g, t, f) in GEN_TP_FUELS] are the nitrogen
    oxides, sulfur dioxide and methane emissions produced by dispatching
    a fuel-based project in units of metric tonnes per hour. These are
    derived using DispatchGenByFuel. Unlike DispatchEmissions, Carbon Capture
    and Sequestration does not impact these expressions.

    AnnualEmissions[p in PERIODS]:The system's annual CO2 emissions, in metric
    tonnes of CO2 per year.

    AnnualEmissionsNOx[p in PERIODS], AnnualEmissionsSO2[p in PERIODS] and
    AnnualEmissionsCH4[p in PERIODS] are the system's annual nitrogen oxides,
    sulfur dioxide and methane emissions, in metric tonnes per year.

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
        if not hasattr(m, "period_active_gen_dict"):
            m.period_active_gen_dict = collections.defaultdict(set)
            for (_g, _period) in m.GEN_PERIODS:
                m.period_active_gen_dict[_period].add(_g)
        result = m.period_active_gen_dict.pop(period)
        if len(m.period_active_gen_dict) == 0:
            delattr(m, "period_active_gen_dict")
        return result

    mod.GENS_IN_PERIOD = Set(
        mod.PERIODS,
        ordered=False,
        initialize=period_active_gen_rule,
        doc="The set of projects active in a given period.",
    )

    mod.TPS_FOR_GEN = Set(
        mod.GENERATION_PROJECTS,
        within=mod.TIMEPOINTS,
        initialize=lambda m, g: (
            tp for p in m.PERIODS_FOR_GEN[g] for tp in m.TPS_IN_PERIOD[p]
        ),
    )

    def init(m, gen, period):
        try:
            d = m._TPS_FOR_GEN_IN_PERIOD_dict
        except AttributeError:
            d = m._TPS_FOR_GEN_IN_PERIOD_dict = dict()
            for _gen in m.GENERATION_PROJECTS:
                for t in m.TPS_FOR_GEN[_gen]:
                    d.setdefault((_gen, m.tp_period[t]), set()).add(t)
        result = d.pop((gen, period), set())
        if not d:  # all gone, delete the attribute
            del m._TPS_FOR_GEN_IN_PERIOD_dict
        return result

    mod.TPS_FOR_GEN_IN_PERIOD = Set(
        mod.GENERATION_PROJECTS,
        mod.PERIODS,
        ordered=False,
        within=mod.TIMEPOINTS,
        initialize=init,
    )

    mod.GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.GENERATION_PROJECTS for tp in m.TPS_FOR_GEN[g]
        ),
    )
    mod.VARIABLE_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.VARIABLE_GENS for tp in m.TPS_FOR_GEN[g]
        ),
    )
    mod.FUEL_BASED_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.FUEL_BASED_GENS for tp in m.TPS_FOR_GEN[g]
        ),
    )
    mod.GEN_TP_FUELS = Set(
        dimen=3,
        initialize=lambda m: (
            (g, t, f) for (g, t) in m.FUEL_BASED_GEN_TPS for f in m.FUELS_FOR_GEN[g]
        ),
    )

    mod.GenCapacityInTP = Expression(
        mod.GEN_TPS, rule=lambda m, g, t: m.GenCapacity[g, m.tp_period[t]]
    )
    mod.DispatchGen = Var(mod.GEN_TPS, within=NonNegativeReals)
    mod.DispatchGenByFuel = Var(mod.GEN_TP_FUELS, within=NonNegativeReals)
    mod.DispatchGenByFuel_Constraint = Constraint(
        mod.FUEL_BASED_GEN_TPS,
        rule=lambda m, g, t: sum(
            m.DispatchGenByFuel[g, t, f] for f in m.FUELS_FOR_GEN[g]
        )
        == m.DispatchGen[g, t],
    )

    # Only used to improve the performance of calculating ZoneTotalCentralDispatch and ZoneTotalDistributedDispatch
    mod.GENS_FOR_ZONE_TPS = Set(
        mod.LOAD_ZONES,
        mod.TIMEPOINTS,
        ordered=False,
        initialize=lambda m, z, t: set(
            g for g in m.GENS_IN_ZONE[z] if (g, t) in m.GEN_TPS
        ),
    )

    # If we use the local_td module, divide distributed generation into a separate expression so that we can
    # put it in the distributed node's power balance equations
    using_local_td = hasattr(mod, "Distributed_Power_Injections")

    mod.ZoneTotalCentralDispatch = Expression(
        mod.LOAD_ZONES,
        mod.TIMEPOINTS,
        rule=lambda m, z, t: sum(
            m.DispatchGen[g, t]
            for g in m.GENS_FOR_ZONE_TPS[z, t]
            if not using_local_td or not m.gen_is_distributed[g]
        )
        - sum(
            m.DispatchGen[g, t] * m.gen_ccs_energy_load[g]
            for g in m.CCS_EQUIPPED_GENS
            if g in m.GENS_FOR_ZONE_TPS[z, t]
        ),
        doc="Net power from grid-tied generation projects.",
    )
    mod.Zone_Power_Injections.append("ZoneTotalCentralDispatch")

    if using_local_td:
        mod.ZoneTotalDistributedDispatch = Expression(
            mod.LOAD_ZONES,
            mod.TIMEPOINTS,
            rule=lambda m, z, t: sum(
                m.DispatchGen[g, t]
                for g in m.GENS_FOR_ZONE_TPS[z, t]
                if m.gen_is_distributed[g]
            ),
            doc="Total power from distributed generation projects.",
        )
        mod.Distributed_Power_Injections.append("ZoneTotalDistributedDispatch")

    def init_gen_availability(m, g):
        if m.gen_is_baseload[g]:
            return (1 - m.gen_forced_outage_rate[g]) * (
                1 - m.gen_scheduled_outage_rate[g]
            )
        else:
            return 1 - m.gen_forced_outage_rate[g]

    mod.gen_availability = Param(
        mod.GENERATION_PROJECTS,
        within=NonNegativeReals,
        initialize=init_gen_availability,
    )

    mod.VARIABLE_GEN_TPS_RAW = Set(
        dimen=2,
        within=mod.VARIABLE_GENS * mod.TIMEPOINTS,
    )
    mod.gen_max_capacity_factor = Param(
        mod.VARIABLE_GEN_TPS_RAW,
        within=Reals,
        validate=lambda m, val, g, t: -1 < val < 2,
    )
    # Validate that a gen_max_capacity_factor has been defined for every
    # variable gen / timepoint that we need. Extra cap factors (like beyond an
    # existing plant's lifetime) shouldn't cause any problems.
    # This replaces: mod.min_data_check('gen_max_capacity_factor') from when
    # gen_max_capacity_factor was indexed by VARIABLE_GEN_TPS.
    mod.have_minimal_gen_max_capacity_factors = BuildCheck(
        mod.VARIABLE_GEN_TPS, rule=lambda m, g, t: (g, t) in m.VARIABLE_GEN_TPS_RAW
    )

    mod.GenFuelUseRate = Var(
        mod.GEN_TP_FUELS,
        within=NonNegativeReals,
        doc=(
            "Other modules constraint this variable based on DispatchGenByFuel and "
            "module-specific formulations of unit commitment and heat rates."
        ),
    )

    def DispatchEmissions_rule(m, g, t, f):
        if g not in m.CCS_EQUIPPED_GENS:
            return m.GenFuelUseRate[g, t, f] * (
                m.f_co2_intensity[f] + m.f_upstream_co2_intensity[f]
            )
        else:
            ccs_emission_frac = 1 - m.gen_ccs_capture_efficiency[g]
            return m.GenFuelUseRate[g, t, f] * (
                m.f_co2_intensity[f] * ccs_emission_frac + m.f_upstream_co2_intensity[f]
            )

    mod.DispatchEmissions = Expression(mod.GEN_TP_FUELS, rule=DispatchEmissions_rule)

    mod.DispatchEmissionsNOx = Expression(
        mod.GEN_TP_FUELS,
        rule=(lambda m, g, t, f: m.DispatchGenByFuel[g, t, f] * m.f_nox_intensity[f]),
    )

    mod.DispatchEmissionsSO2 = Expression(
        mod.GEN_TP_FUELS,
        rule=(lambda m, g, t, f: m.DispatchGenByFuel[g, t, f] * m.f_so2_intensity[f]),
    )

    mod.DispatchEmissionsCH4 = Expression(
        mod.GEN_TP_FUELS,
        rule=(lambda m, g, t, f: m.DispatchGenByFuel[g, t, f] * m.f_ch4_intensity[f]),
    )

    mod.AnnualEmissions = Expression(
        mod.PERIODS,
        rule=lambda m, period: sum(
            m.DispatchEmissions[g, t, f] * m.tp_weight_in_year[t]
            for (g, t, f) in m.GEN_TP_FUELS
            if m.tp_period[t] == period
        ),
        doc="The system's annual CO2 emissions, in metric tonnes of CO2 per year.",
    )

    mod.AnnualEmissionsNOx = Expression(
        mod.PERIODS,
        rule=lambda m, period: sum(
            m.DispatchEmissionsNOx[g, t, f] * m.tp_weight_in_year[t]
            for (g, t, f) in m.GEN_TP_FUELS
            if m.tp_period[t] == period
        ),
        doc="The system's annual NOx emissions, in metric tonnes of NOx per year.",
    )

    mod.AnnualEmissionsSO2 = Expression(
        mod.PERIODS,
        rule=lambda m, period: sum(
            m.DispatchEmissionsSO2[g, t, f] * m.tp_weight_in_year[t]
            for (g, t, f) in m.GEN_TP_FUELS
            if m.tp_period[t] == period
        ),
        doc="The system's annual SO2 emissions, in metric tonnes of SO2 per year.",
    )

    mod.AnnualEmissionsCH4 = Expression(
        mod.PERIODS,
        rule=lambda m, period: sum(
            m.DispatchEmissionsCH4[g, t, f] * m.tp_weight_in_year[t]
            for (g, t, f) in m.GEN_TP_FUELS
            if m.tp_period[t] == period
        ),
        doc="The system's annual CH4 emissions, in metric tonnes of CH4 per year.",
    )

    mod.GenVariableOMCostsInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.DispatchGen[g, t] * m.gen_variable_om[g]
            for g in m.GENS_IN_PERIOD[m.tp_period[t]]
        ),
        doc="Summarize costs for the objective function",
    )
    mod.Cost_Components_Per_TP.append("GenVariableOMCostsInTP")


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import project-specific data from an input directory.

    variable_capacity_factors can be skipped if no variable
    renewable projects are considered in the optimization.

    variable_capacity_factors.csv
        GENERATION_PROJECT, timepoint, gen_max_capacity_factor

    """

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "variable_capacity_factors.csv"),
        autoselect=True,
        index=mod.VARIABLE_GEN_TPS_RAW,
        param=(mod.gen_max_capacity_factor,),
    )


def post_solve(instance, outdir):
    """
    Exported files:

    dispatch-wide.csv - Dispatch results timepoints in "wide" format with
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
        instance,
        instance.TIMEPOINTS,
        output_file=os.path.join(outdir, "dispatch-wide.csv"),
        headings=("timestamp",) + tuple(sorted(instance.GENERATION_PROJECTS)),
        values=lambda m, t: (m.tp_timestamp[t],)
        + tuple(
            m.DispatchGen[p, t] if (p, t) in m.GEN_TPS else 0.0
            for p in sorted(m.GENERATION_PROJECTS)
        ),
    )

    def c(func):
        return (value(func(g, t)) for g, t in instance.GEN_TPS)

    # Note we've refactored to create the Dataframe in one
    # line to reduce the overall memory consumption during
    # the most intensive part of post-solve (this function)
    dispatch_full_df = pd.DataFrame(
        {
            "generation_project": c(lambda g, t: g),
            "gen_dbid": c(lambda g, t: instance.gen_dbid[g]),
            "gen_tech": c(lambda g, t: instance.gen_tech[g]),
            "gen_load_zone": c(lambda g, t: instance.gen_load_zone[g]),
            "gen_energy_source": c(lambda g, t: instance.gen_energy_source[g]),
            "timestamp": c(lambda g, t: instance.tp_timestamp[t]),
            "tp_weight_in_year_hrs": c(lambda g, t: instance.tp_weight_in_year[t]),
            "period": c(lambda g, t: instance.tp_period[t]),
            "is_renewable": c(lambda g, t: g in instance.VARIABLE_GENS),
            "DispatchGen_MW": c(lambda g, t: instance.DispatchGen[g, t]),
            "Curtailment_MW": c(
                lambda g, t: value(instance.DispatchUpperLimit[g, t])
                - value(instance.DispatchGen[g, t])
            ),
            "Energy_GWh_typical_yr": c(
                lambda g, t: instance.DispatchGen[g, t]
                * instance.tp_weight_in_year[t]
                / 1000
            ),
            "VariableOMCost_per_yr": c(
                lambda g, t: instance.DispatchGen[g, t]
                * instance.gen_variable_om[g]
                * instance.tp_weight_in_year[t]
            ),
            "DispatchEmissions_tCO2_per_typical_yr": c(
                lambda g, t: sum(
                    instance.DispatchEmissions[g, t, f] * instance.tp_weight_in_year[t]
                    for f in instance.FUELS_FOR_GEN[g]
                )
                if instance.gen_uses_fuel[g]
                else 0
            ),
            "DispatchEmissions_tNOx_per_typical_yr": c(
                lambda g, t: sum(
                    instance.DispatchEmissionsNOx[g, t, f]
                    * instance.tp_weight_in_year[t]
                    for f in instance.FUELS_FOR_GEN[g]
                )
                if instance.gen_uses_fuel[g]
                else 0
            ),
            "DispatchEmissions_tSO2_per_typical_yr": c(
                lambda g, t: sum(
                    instance.DispatchEmissionsSO2[g, t, f]
                    * instance.tp_weight_in_year[t]
                    for f in instance.FUELS_FOR_GEN[g]
                )
                if instance.gen_uses_fuel[g]
                else 0
            ),
            "DispatchEmissions_tCH4_per_typical_yr": c(
                lambda g, t: sum(
                    instance.DispatchEmissionsCH4[g, t, f]
                    * instance.tp_weight_in_year[t]
                    for f in instance.FUELS_FOR_GEN[g]
                )
                if instance.gen_uses_fuel[g]
                else 0
            ),
        }
    )
    dispatch_full_df.set_index(["generation_project", "timestamp"], inplace=True)
    write_table(
        instance, output_file=os.path.join(outdir, "dispatch.csv"), df=dispatch_full_df
    )

    annual_summary = dispatch_full_df.groupby(
        ["gen_tech", "gen_energy_source", "period"]
    ).sum()
    write_table(
        instance,
        output_file=os.path.join(outdir, "dispatch_annual_summary.csv"),
        df=annual_summary,
        columns=[
            "Energy_GWh_typical_yr",
            "VariableOMCost_per_yr",
            "DispatchEmissions_tCO2_per_typical_yr",
            "DispatchEmissions_tNOx_per_typical_yr",
            "DispatchEmissions_tSO2_per_typical_yr",
            "DispatchEmissions_tCH4_per_typical_yr",
        ],
    )

    zonal_annual_summary = dispatch_full_df.groupby(
        ["gen_tech", "gen_load_zone", "gen_energy_source", "period"]
    ).sum()
    write_table(
        instance,
        output_file=os.path.join(outdir, "dispatch_zonal_annual_summary.csv"),
        df=zonal_annual_summary,
        columns=[
            "Energy_GWh_typical_yr",
            "VariableOMCost_per_yr",
            "DispatchEmissions_tCO2_per_typical_yr",
            "DispatchEmissions_tNOx_per_typical_yr",
            "DispatchEmissions_tSO2_per_typical_yr",
            "DispatchEmissions_tCH4_per_typical_yr",
        ],
    )


@graph("dispatch", title="Average daily dispatch", is_long=True)
def graph_hourly_dispatch(tools):
    """
    Generates a matrix of hourly dispatch plots for each time region
    """
    # Read dispatch.csv
    df = tools.get_dataframe("dispatch.csv")
    # Convert to GW
    df["DispatchGen_MW"] /= 1e3
    # Plot Dispatch
    tools.graph_time_matrix(
        df,
        value_column="DispatchGen_MW",
        ylabel="Average daily dispatch (GW)",
    )


@graph("curtailment", title="Average daily curtailment", is_long=True)
def graph_hourly_curtailment(tools):
    # Read dispatch.csv
    df = tools.get_dataframe("dispatch.csv")
    # Keep only renewable
    df = df[df["is_renewable"]]
    df["Curtailment_MW"] /= 1e3  # Convert to GW
    # Plot curtailment
    tools.graph_time_matrix(
        df, value_column="Curtailment_MW", ylabel="Average daily curtailment (GW)"
    )


@graph(
    "dispatch_per_scenario",
    title="Average daily dispatch",
    requires_multi_scenario=True,
    is_long=True,
)
def graph_hourly_dispatch(tools):
    """
    Generates a matrix of hourly dispatch plots for each time region
    """
    # Read dispatch.csv
    df = tools.get_dataframe("dispatch.csv")
    # Convert to GW
    df["DispatchGen_MW"] /= 1e3
    # Plot Dispatch
    tools.graph_scenario_matrix(
        df, value_column="DispatchGen_MW", ylabel="Average daily dispatch (GW)"
    )


@graph(
    "curtailment_compare_scenarios",
    title="Average daily curtailment by scenario",
    requires_multi_scenario=True,
    is_long=True,
)
def graph_hourly_curtailment(tools):
    # Read dispatch.csv
    df = tools.get_dataframe("dispatch.csv")
    # Keep only renewable
    df = df[df["is_renewable"]]
    df["Curtailment_MW"] /= 1e3  # Convert to GW
    tools.graph_scenario_matrix(
        df, value_column="Curtailment_MW", ylabel="Average daily curtailment (GW)"
    )


@graph(
    "total_dispatch",
    title="Total dispatched electricity",
)
def graph_total_dispatch(tools):
    # ---------------------------------- #
    # total_dispatch.png                 #
    # ---------------------------------- #
    # read dispatch_annual_summary.csv
    total_dispatch = tools.get_dataframe("dispatch_annual_summary.csv")
    # add type column
    total_dispatch = tools.transform.gen_type(total_dispatch)
    # aggregate and pivot
    total_dispatch = total_dispatch.pivot_table(
        columns="gen_type",
        index="period",
        values="Energy_GWh_typical_yr",
        aggfunc=tools.np.sum,
    )
    # Convert values to TWh
    total_dispatch *= 1e-3

    # For generation types that make less than 2% in every period, group them under "Other"
    # ---------
    # sum the generation across the energy_sources for each period, 2% of that is the cutoff for that period
    cutoff_per_period = total_dispatch.sum(axis=1) * 0.02
    # Check for each technology if it's below the cutoff for every period
    is_below_cutoff = total_dispatch.lt(cutoff_per_period, axis=0).all()
    # groupby if the technology is below the cutoff
    total_dispatch = total_dispatch.groupby(
        axis=1, by=lambda c: "Other" if is_below_cutoff[c] else c
    ).sum()

    # Sort columns by the last period
    total_dispatch = total_dispatch.sort_values(by=total_dispatch.index[-1], axis=1)
    # Give proper name for legend
    total_dispatch = total_dispatch.rename_axis("Type", axis=1)
    # Get axis
    # Plot
    total_dispatch.plot(
        kind="bar",
        stacked=True,
        ax=tools.get_axes(),
        color=tools.get_colors(len(total_dispatch)),
        xlabel="Period",
        ylabel="Total dispatched electricity (TWh)",
    )

    tools.bar_label()


@graph(
    "energy_balance",
    title="Energy Balance For Every Month",
    supports_multi_scenario=True,
    is_long=True,
)
def energy_balance(tools):
    # Get dispatch dataframe
    cols = [
        "timestamp",
        "gen_tech",
        "gen_energy_source",
        "DispatchGen_MW",
        "scenario_name",
        "scenario_index",
    ]
    df = tools.get_dataframe("dispatch.csv", drop_scenario_info=False)[cols]
    df = tools.transform.gen_type(df)
    # Sum dispatch across all the projects of the same type and timepoint
    df = df.groupby(
        ["timestamp", "gen_type", "scenario_name", "scenario_index"], as_index=False
    ).sum()
    df = df.rename({"gen_type": "Type", "DispatchGen_MW": "value"}, axis=1)

    discharge = (
        df[df["Type"] == "Storage"]
        .drop("Type", axis=1)
        .rename({"value": "discharge"}, axis=1)
    )

    # Get load dataframe
    load = tools.get_dataframe("load_balance.csv", drop_scenario_info=False)
    load = load.drop("normalized_energy_balance_duals_dollar_per_mwh", axis=1)

    # Sum load across all the load zones
    key_columns = ["timestamp", "scenario_name", "scenario_index"]
    load = load.groupby(key_columns, as_index=False).sum()

    # Subtract storage dispatch from generation and add it to the storage charge to get net flow
    load = load.merge(discharge, how="left", on=key_columns, validate="one_to_one")
    load["ZoneTotalCentralDispatch"] -= load["discharge"]
    load["StorageNetCharge"] += load["discharge"]
    load = load.drop("discharge", axis=1)

    # Rename and convert from wide to long format
    load = load.rename(
        {
            "ZoneTotalCentralDispatch": "Total Generation (excl. storage discharge)",
            "TXPowerNet": "Transmission Losses",
            "StorageNetCharge": "Storage Net Flow",
            "zone_demand_mw": "Demand",
        },
        axis=1,
    ).sort_index(axis=1)
    load = load.melt(id_vars=key_columns, var_name="Type")

    # Merge dispatch contributions with load contributions
    df = pd.concat([load, df])

    # Add the timestamp information and make period string to ensure it doesn't mess up the graphing
    df = tools.transform.timestamp(df).astype({"period": str})

    # Convert to TWh (incl. multiply by timepoint duration)
    df["value"] *= df["tp_duration"] / 1e6

    FREQUENCY = "1W"

    def groupby_time(df):
        return df.groupby(
            [
                "scenario_name",
                "period",
                "Type",
                tools.pd.Grouper(key="datetime", freq=FREQUENCY, origin="start"),
            ]
        )["value"]

    df = groupby_time(df).sum().reset_index()

    # Get the state of charge data
    soc = tools.get_dataframe(
        "StateOfCharge.csv", dtype={"STORAGE_GEN_TPS_1": str}, drop_scenario_info=False
    )
    soc = soc.rename(
        {"STORAGE_GEN_TPS_2": "timepoint", "StateOfCharge": "value"}, axis=1
    )
    # Sum over all the projects that are in the same scenario with the same timepoint
    soc = soc.groupby(["timepoint", "scenario_name"], as_index=False).sum()
    soc["Type"] = "State Of Charge"
    soc["value"] /= 1e6  # Convert to TWh

    # Group by time
    soc = tools.transform.timestamp(
        soc, use_timepoint=True, key_col="timepoint"
    ).astype({"period": str})
    soc = groupby_time(soc).mean().reset_index()

    # Add state of charge to dataframe
    df = pd.concat([df, soc])
    # Add column for day since that's what we really care about
    df["day"] = df["datetime"].dt.dayofyear

    # Plot
    # Get the colors for the lines
    colors = tools.get_colors()
    colors.update(
        {
            "Transmission Losses": "brown",
            "Storage Net Flow": "cadetblue",
            "Demand": "black",
            "Total Generation (excl. storage discharge)": "black",
            "State Of Charge": "green",
        }
    )

    # plot
    num_periods = df["period"].nunique()
    pn = tools.pn
    plot = (
        pn.ggplot(df)
        + pn.geom_line(pn.aes(x="day", y="value", color="Type"))
        + pn.facet_grid("period ~ scenario_name")
        + pn.labs(y="Contribution to Energy Balance (TWh)")
        + pn.scales.scale_color_manual(
            values=colors, aesthetics="color", na_value=colors["Other"]
        )
        + pn.scales.scale_x_continuous(
            name="Month",
            labels=["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"],
            breaks=(15, 46, 76, 106, 137, 167, 198, 228, 259, 289, 319, 350),
            limits=(0, 366),
        )
        + pn.theme(
            figure_size=(
                pn.options.figure_size[0] * tools.num_scenarios,
                pn.options.figure_size[1] * num_periods,
            )
        )
    )

    tools.save_figure(plot.draw())


@graph(
    "curtailment_per_period",
    title="Percent of total dispatchable capacity curtailed",
    is_long=True,
)
def graph_curtailment_per_tech(tools):
    # Load dispatch.csv
    df = tools.get_dataframe("dispatch.csv")
    df = tools.transform.gen_type(df)
    df["Total"] = df["DispatchGen_MW"] + df["Curtailment_MW"]
    df = df[df["is_renewable"]]
    # Make PERIOD a category to ensure x-axis labels don't fill in years between period
    # TODO we should order this by period here to ensure they're in increasing order
    df["period"] = df["period"].astype("category")
    df = df.groupby(["period", "gen_type"], as_index=False).sum()
    df["Percent Curtailed"] = df["Curtailment_MW"] / (
        df["DispatchGen_MW"] + df["Curtailment_MW"]
    )
    df = df.pivot(
        index="period", columns="gen_type", values="Percent Curtailed"
    ).fillna(0)
    if len(df) == 0:  # No dispatch from renewable technologies
        return
    # Set the name of the legend.
    df = df.rename_axis("Type", axis="columns")
    # Get axes to graph on
    ax = tools.get_axes()
    # Plot
    color = tools.get_colors()
    kwargs = dict() if color is None else dict(color=color)
    df.plot(ax=ax, kind="line", xlabel="Period", marker="x", **kwargs)

    # Set the y-axis to use percent
    ax.yaxis.set_major_formatter(tools.mplt.ticker.PercentFormatter(1.0))
    # Horizontal line at 100%
    # ax.axhline(y=1, linestyle="--", color='b')
