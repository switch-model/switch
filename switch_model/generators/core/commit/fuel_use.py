# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
This module models fuel use with part load heat rate curves (AKA Input/Output
curves, AKA Incremental Heat Rate), and provides best-effort defaults when
detailed heat rate data is unavailable. It has a prerequisite of
switch_model.generators.core.commit.operate

This module can accept data in two formats: 
1) Part load heat rates that are a series of points: capacity_factor, heat_rate
2) Incremental heat rate tables as described in "THE USE OF HEAT RATES IN
PRODUCTION COST MODELING AND MARKET MODELING" (1998, California Energy
Commission staff report)
https://listserver.energy.ca.gov/papers/98-04-07_HEATRATE.PDF

However it comes in, the data is converted into one or more line segments per
generator, and fuel use is constrained to be above all of the lines. This
works well since heat rate curves for thermal power plants tend to either be
linear (single line segment) or concave up. If you need to model heat rate 
curves that are concave down or non-convex, you will need to write a 
new module to constrain the fuel use, likely using integer variables or
non-linear programming.

If you haven't worked with incremental heat rates before, you may want
to start by reading a background document on incremental heat rates such
as: https://listserver.energy.ca.gov/papers/98-04-07_HEATRATE.PDF

Incremental heat rates are a way of approximating an "input-output
curve" (heat input vs electricity output) with a series of line
segments. These curves are typically drawn with electricity output on
the x-axis (Power, MW) and fuel use rates on the y-axis (MMBTU/h). These
curves are drawn from the minimum to maximum power output levels for a
given generator, and most thermal generators cannot run at 0 output. The slope
of each line segment is the incremental heat rate at that point in units of
MMBTU/MWh.

There are two basic ways to model a piecewise linear relationship like
this in linear programming. The first approach (which we don't use in
this module) is to divide the energy production variable into several
subvariables (one for each line segment), and put an upper bound on each
subvariable so that it can't exceed the width of the segment. The total
energy production is the sum of the sub-variables, and the total fuel
consumption is: Fuel = line0_intercept + E0*incremental_heat_rate0 +
E1*incremental_heat_rate1 + ... As long as each incremental_heat_rate is
larger than the one before it, then the optimization will ensure that E1
remains at 0 until E0 is at its upper limit, which ensures consistent
results. This tiered decision method is used in the fuel_markets module,
but is not used here.

This module uses the second approach which is to make FuelUse into a
decision variable that must be greater than or equal to each of the
lines. As long as fuel has a cost associated with it, a cost minimizing
optimization will push the fuel use down till it touchs a line segments.
This method also requires that incremental heat rates increase with
energy production so that the lines collectively form a convex boundary
for fuel use.

"""
from __future__ import division

import csv
import os

import pandas
from pyomo.environ import *

from switch_model.utilities import approx_equal

dependencies = (
    'switch_model.timescales',
    'switch_model.balancing.load_zones',
    'switch_model.financials',
    'switch_model.energy_sources.properties.properties',
    'switch_model.generators.core.build',
    'switch_model.generators.core.dispatch',
    'switch_model.generators.core.commit.operate',
)

def define_components(mod):
    """
    This function ties fuel consumption to unit commitment. Unless otherwise
    stated, all power capacity is specified in units of MW and all sets and
    parameters are mandatory.

    FUEL_USE_SEGMENTS_FOR_GEN[g in FUEL_BASED_GENS] is a set of line
    segments that collectively describe fuel requirements for a given
    project. Each element of this set is a tuple of (y-intercept, slope)
    where the y-intercept is in units of MMBTU/(hr * MW-capacity) and
    slope is incremental heat rate in units of MMBTU / MWh-energy. We
    normalize the y-intercept by capacity so that we can scale it to
    arbitrary sizes of generation, or stacks of individual generation
    units. This code can be used in conjunction with discrete unit sizes
    but it not dependent on that. This set is optional, and will default to
    an intercept of 0 and a slope equal to its full load heat rate.
    
    GEN_TPS_FUEL_PIECEWISE_CONS_SET is a set of (g, t, intercept, slope) that
    describes the fuel use constraints for every thermal generator in every
    timepoint.
    
    GenFuelUseRate_Calculate[GEN_TPS_FUEL_PIECEWISE_CONS_SET] constrains fuel
    use to be above each line segment, relative to the unit commitment and
    dispatch decision variables. Any fuel required for starting up a generator
    is also taken into account.
    
    For multi-fuel generators, we make the simplifying assumption that the
    heat rate curve is constant with regards to differing types of fuel
    input.. basically assuming that heat (MBTU) matters more than the source
    of heat
    """

    mod.FUEL_USE_SEGMENTS_FOR_GEN = Set(
        mod.FUEL_BASED_GENS,
        dimen=2)

    # Sets don't support defaults, so use BuildAction to build defaults.
    def FUEL_USE_SEGMENTS_FOR_GEN_default_rule(m, g):
        if g not in m.FUEL_USE_SEGMENTS_FOR_GEN:
            heat_rate = m.gen_full_load_heat_rate[g]
            m.FUEL_USE_SEGMENTS_FOR_GEN[g] = [(0, heat_rate)]
    mod.FUEL_USE_SEGMENTS_FOR_GEN_default = BuildAction(
        mod.FUEL_BASED_GENS,
        rule=FUEL_USE_SEGMENTS_FOR_GEN_default_rule)

    mod.GEN_TPS_FUEL_PIECEWISE_CONS_SET = Set(
        dimen=4,
        initialize=lambda m: [
            (g, t, intercept, slope)
            for (g, t) in m.FUEL_BASED_GEN_TPS
            for (intercept, slope) in m.FUEL_USE_SEGMENTS_FOR_GEN[g]
        ]
    )
    mod.GenFuelUseRate_Calculate = Constraint(
        mod.GEN_TPS_FUEL_PIECEWISE_CONS_SET,
        rule=lambda m, g, t, intercept, incremental_heat_rate: (
            sum(m.GenFuelUseRate[g, t, f] for f in m.FUELS_FOR_GEN[g]) >=
            # Startup fuel is a one-shot fuel expenditure, but the rest of
            # this expression has a units of heat/hr, so convert startup fuel
            # requirements into an average over this timepoint.
            m.StartupGenCapacity[g, t] * m.gen_startup_fuel[g] / m.tp_duration_hrs[t] +
            intercept * m.CommitGen[g, t] +
            incremental_heat_rate * m.DispatchGen[g, t]))


def load_inputs(mod, switch_data, inputs_dir):
    """
    Import a fuel use curve to describe fuel use under partial loading
    conditions.

    Plants that lack detailed data will default to a single line segment with
    a y-intercept of 0 and a slope equal to the full load head rate. This
    default tends to underestimate fuel use steam turbines or combined cycle
    plants under partial loading conditions, which generally have y-intercepts
    above 0.

    We support two ways of specifying a fuel use curve as a series of line
    segments. Both files are optional; you may specify either one, but not
    both. In both cases, data is converted into FUEL_USE_SEGMENTS_FOR_GEN
    whose format is described above.

    1) gen_part_load_heat_rates.csv is normalized and includes a series of
       points: gen_loading_level, gen_heat_rate_at_loading_level.
    2) gen_inc_heat_rates.csv is non-normalized and includes an initial point
       plus subsequent slopes for a prototypical plant. Supposedly this format
       was common at one point, but I don't know how widespread it is today.

    gen_part_load_heat_rates.csv
        GENERATION_PROJECT, gen_loading_level, gen_heat_rate_at_loading_level
    
    gen_loading_level describes the fractional loading level (0 to 1).
    gen_heat_rate_at_loading_level describes the heat rate at the given
    loading level in units of MMBTU/MWh.
    Minimally, each plant should specify two points to describe a single line
    from minimum to maximum loading conditions.

    gen_inc_heat_rates.csv
        GENERATION_PROJECT, power_start_mw, power_end_mw,
        incremental_heat_rate_mbtu_per_mwhr, fuel_use_rate_mmbtu_per_h

    In gen_inc_heat_rates.csv, the first record is the first point on the
    curve, but all subsequent records are slopes and x-domain for each line
    segment. For a given generation technology or project, the relevant data
    should be formatted like so:

    power_start_mw  power_end_mw   ihr   fuel_use_rate
    min_load             .          .       y-value
    min_load          mid_load1   slope       .
    mid_load1         max_load    slope       .

    The first row provides the first point on the input/output curve.
    Literal dots should be included to indicate blanks.
    The column fuel_use_rate is in units of MMBTU/h.
    Subsequent rows provide the domain and slope of each line segement.
    The column ihr indicates incremental heat rate in MMBTU/MWh.
    Any number of line segments will be accepted.
    All text should be replaced with actual numerical values.
    """
    path1 = os.path.join(inputs_dir, 'gen_part_load_heat_rates.csv')
    path2 = os.path.join(inputs_dir, 'gen_inc_heat_rates.csv')
    if os.path.isfile(path1):
        fuel_rate_segments, min_loading_levels, full_hr = \
            _parse_part_load_hr_file(path1)
    elif os.path.isfile(path2):
        fuel_rate_segments, min_loading_levels, full_hr = \
            _parse_inc_hr_file(path2)
    else:
        return

    switch_data.data()['FUEL_USE_SEGMENTS_FOR_GEN'] = fuel_rate_segments
    
    # Check implied minimum loading level for consistency with
    # gen_min_load_fraction if gen_min_load_fraction was provided. If
    # gen_min_load_fraction wasn't provided, set it to implied minimum
    # loading level.
    if 'gen_min_load_fraction' not in switch_data.data():
        switch_data.data()['gen_min_load_fraction'] = {}
    data_portal_dat = switch_data.data(name='gen_min_load_fraction')
    for g, min_load in min_loading_levels.items():
        if g in data_portal_dat:
            assert approx_equal(min_load, data_portal_dat[g]), (
                "gen_min_load_fraction is inconsistant with "
                "incremental heat rate data for project "
                "{}.".format(g)
            )
        else:
            data_portal_dat[g] = min_load

    # Same thing, but for full load heat rate.
    if 'gen_full_load_heat_rate' not in switch_data.data():
        switch_data.data()['gen_full_load_heat_rate'] = {}
    data_portal_dat = switch_data.data(name='gen_full_load_heat_rate')
    for g, hr in full_hr.items():
        if g in data_portal_dat:
            assert approx_equal(hr, data_portal_dat[g]), (
                "gen_full_load_heat_rate is inconsistant with partial "
                "loading heat rate data for generation project "
                "{}.".format(g)
            )
        else:
            data_portal_dat[g] = hr


def _parse_part_load_hr_file(path):
    df = pandas.read_csv(path)
    df.sort_values(by=['GENERATION_PROJECT', 'gen_loading_level'], inplace=True)
    fuel_rate_segments = {}
    full_load_hr = {}
    min_cap_factor = {}
    for g, df_g in df.groupby('GENERATION_PROJECT'):
        cap_factor0, heat_rate0, slope0 = None, None, None
        fuel_rate_segments[g] = []
        for idx, row in df_g.iterrows():
            if cap_factor0 is None:
                _, cap_factor0, heat_rate0 = row
                min_cap_factor[g] = cap_factor0
                continue
            _, cap_factor, heat_rate = row
            slope = (heat_rate - heat_rate0) / (cap_factor-cap_factor0)
            intercept = heat_rate0 - cap_factor0 * slope
            fuel_rate_segments[g].append((intercept, slope))
            if slope0:
                assert slope >= slope0, (
                    "The incremental heat rate for {}, loading level {}-{} in "
                    "file {} is smaller than the last segment, which violates "
                    "this module's concave-up assumptions."
                    "".format(g, cap_factor0, cap_factor, path)
                )
            cap_factor0, heat_rate0, slope0 = cap_factor, heat_rate, slope
        full_load_hr[g] = heat_rate
    return (fuel_rate_segments, min_cap_factor, full_load_hr)

def _parse_inc_hr_file(path):
    """
    Parse tabular incremental heat rate data, calculate a series of
    lines that describe each segment, and perform various error checks.
    """
    # All dictionaries are indexed by generation project.
    # fuel_rate_points[g] = {power: fuel_use_rate}
    fuel_rate_points = {}
    # ihr_dat stores incremental heat rate records as a list for each gen
    ihr_dat = {}
    # fuel_rate_segments[g] = [(intercept1, slope1), (int2, slope2)...]
    # Stores the description of each linear segment of a fuel rate curve.
    fuel_rate_segments = {}
    # min_cap_factor[g] and full_load_hr[g] are used for default values and/or
    # error checking.
    min_cap_factor = {}
    full_load_hr = {}
    # Parse the file and stuff data into dictionaries indexed by units.
    with open(path, 'r') as hr_file:
        dat = list(csv.DictReader(hr_file, delimiter=','))
        for row in dat:
            g = row['GENERATION_PROJECT']
            p1 = float(row['power_start_mw'])
            p2 = row['power_end_mw']
            ihr = row['incremental_heat_rate_mbtu_per_mwhr']
            fr = row['fuel_use_rate_mmbtu_per_h']
            # Row looks like the first point.
            if(p2 == '.' and ihr == '.'):
                fr = float(fr)
                assert g not in fuel_rate_points, (
                    "Error processing incremental heat rates for gen {} in {}."
                    "More than one row has a fuel use rate specified."
                    "".format(g, path)
                )
                fuel_rate_points[g] = {p1: fr}
            # Row looks like a line segment.
            elif(fr == '.'):
                p2 = float(p2)
                ihr = float(ihr)
                if(g not in ihr_dat):
                    ihr_dat[g] = []
                ihr_dat[g].append((p1, p2, ihr))
            else:
                raise ValueError(
                    "Error processing incremental heat rates for gen {} in {}."
                    "Row format not recognized for row {}. See documentation "
                    "for acceptable formats.".format(g, path, str(row))
                )

    # Ensure that each project that has incremental heat rates defined
    # also has a starting point defined.
    missing_starts = [k for k in ihr_dat if k not in fuel_rate_points]
    assert not missing_starts, (
        'No starting point(s) are defined for incremental heat rate curves '
        'for the following generators: {}'.format(','.join(missing_starts))
    )

    # Construct a convex combination of lines describing a fuel use
    # curve for each representative unit "g".
    for g, fr_points in fuel_rate_points.items():
        if g not in ihr_dat:
            # No heat rate segments specified; plant can only be off or on at
            # full power. Create a dummy curve at full heat rate
            output, fuel = next(iter(fr_points.items()))
            fuel_rate_segments[g] = [(0.0, fuel / output)]
            min_cap_factor[g] = 1.0
            full_load_hr[g] = fuel / output
            continue

        fuel_rate_segments[g] = []
        # Sort the line segments by their domains.
        ihr_dat[g].sort()
        # Assume that the maximum power output is the rated capacity.
        (junk, capacity, junk) = ihr_dat[g][len(ihr_dat[g])-1]
        # Retrieve the first incremental heat rate for error checking.
        (min_power, junk, ihr_prev) = ihr_dat[g][0]
        min_cap_factor[g] = min_power / capacity
        # Process each line segment.
        for (p_start, p_end, ihr) in ihr_dat[g]:
            # Error check: This incremental heat rate cannot be less than
            # the previous one.
            assert ihr_prev <= ihr, (
                "Error processing incremental heat rates for {} in file {}. "
                "The incremental heat rate between power output levels {}-{} "
                "is less than that of the prior line segment."
                "".format(g, path, p_start, p_end)
            )
            # Error check: This segment needs to start at an existing point.
            assert p_start in fr_points, (
                "Error processing incremental heat rates for {} in file {}. "
                "The incremental heat rate between power output levels {}-{} "
                "does not start at a previously defined point or line segment."
                "".format(g, path, p_start, p_end)
            )
            # Calculate the y-intercept then normalize it by the capacity.
            intercept_norm = (fr_points[p_start] - ihr * p_start) / capacity
            # Save the line segment's definition.
            fuel_rate_segments[g].append((intercept_norm, ihr))
            # Add a point for the end of the segment for the next iteration.
            fr_points[p_end] = fr_points[p_start] + (p_end - p_start) * ihr
            ihr_prev = ihr
        # Calculate the max load heat rate for error checking
        full_load_hr[g] = fr_points[capacity] / capacity
    return (fuel_rate_segments, min_cap_factor, full_load_hr)
