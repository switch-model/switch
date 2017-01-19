# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

This module describes fuel use with considerations of unit commitment
and incremental heat rates using piecewise linear expressions. If you
want to use this module directly in a list of switch modules (instead of
including the package project.unitcommit), you will also need to include
the module operations.unitcommit.commit

If you haven't worked with incremental heat rates before, you may want
to start by reading a background document on incremental heat rates such
as: http://www.energy.ca.gov/papers/98-04-07_HEATRATE.PDF

Incremental heat rates are a way of approximating an "input-output
curve" (heat input vs electricity output) with a series of line
segments. These curves are typically drawn with electricity output on
the x-axis (Power, MW) and fuel use rates on the y-axis (MMBTU/h). These
curves are drawn from the minimum to maximum power output levels for a
given generator, and most generators cannot run at 0 output. The slope
of each line segment is the incremental heat rate at that point in units
of MMBTU/MWh.

Data for incremental heat rates is typically formatted in a heterogenous
manner. The first data point is the first point on the curve - the
minimum loading level (MW) and its corresponding fuel use rate
(MMBTU/h). Subsequent data points provide subseqent loading levels in MW
and slopes, or incremental heat rates in MMBTU/MWh. This format was
designed to make certain economic calculations easy, not to draw input-
output curves, but you can calculate subsequent points on the curve from
this information.

Fuel requirements for most generators can be approximated very well with
simple models of a single line segment, but the gold standard is to use
several line segments that have increasing slopes. In the future, we may
include a simpler model that uses a single line segment, but we are just
implementing the complex piecewise linear form initially to satisfy key
stakeholders.

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

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel(
...     'timescales', 'financials', 'load_zones', 'fuels', 'gen_tech',
...     'investment.proj_build', 'operations.proj_dispatch', 
...     'operations.unitcommit')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

import os
from pyomo.environ import *
import csv
from switch_mod.utilities import approx_equal


def define_components(mod):
    """

    This function adds components to a Pyomo abstract model object to
    describe fuel consumption in the context of unit commitment. Unless
    otherwise stated, all power capacity is specified in units of MW and
    all sets and parameters are mandatory.

    Typically incremental heat rates tables specify "blocks" where each
    block includes power output in MW and heat requirements in MMBTU/hr
    to move from the prior block to the current block. If you plot these
    points and connect the dots, you have a piecewise linear function
    that goes from at least minimum loading level to maximum loading
    level. Data is read in in that format, then processed to describe
    the individual line segments.

    GEN_FUEL_USE_SEGMENTS[g in GEN_TECH_WITH_FUEL] is a set of line segments
    that collectively describe fuel requirements for a given generation
    technology. Each element of this set is a tuple of (y-intercept,
    slope) where the y-intercept is in units of MMBTU/(hr * MW-capacity)
    and slope is incremental heat rate in units of MMBTU / MWh-energy.
    We normalize the y-intercept by capacity so that we can scale it to
    arbitrary sizes of generation, or stacks of individual generation
    units. This code can be used in conjunction with discrete unit sizes
    but it not dependent on that. This set is optional.

    PROJ_FUEL_USE_SEGMENTS[proj in FUEL_BASED_PROJECTS] is the same as
    GEN_FUEL_USE_SEGMENTS but scoped to projects. This set is optional
    and will default to GEN_FUEL_USE_SEGMENTS if that is available;
    otherwise it will default to an intercept of 0 and a slope of its
    full load heat rate.

    """

    # Pyomo doesn't allow default for sets, so I need to specify default
    # data in the data load function.
    mod.GEN_FUEL_USE_SEGMENTS = Set(
        mod.GEN_TECH_WITH_FUEL,
        dimen=2)
    mod.PROJ_FUEL_USE_SEGMENTS = Set(
        mod.FUEL_BASED_PROJECTS,
        dimen=2)

    # Use BuildAction to populate a set's default values.
    def PROJ_FUEL_USE_SEGMENTS_default_rule(m, pr):
        if pr not in m.PROJ_FUEL_USE_SEGMENTS:
            g = m.proj_gen_tech[pr]
            if g in m.GEN_FUEL_USE_SEGMENTS:
                m.PROJ_FUEL_USE_SEGMENTS[pr] = m.GEN_FUEL_USE_SEGMENTS[g]
            else:
                heat_rate = m.proj_full_load_heat_rate[pr]
                m.PROJ_FUEL_USE_SEGMENTS[pr] = [(0, heat_rate)]
    mod.PROJ_FUEL_USE_SEGMENTS_default = BuildAction(
        mod.FUEL_BASED_PROJECTS,
        rule=PROJ_FUEL_USE_SEGMENTS_default_rule)

    mod.PROJ_DISP_FUEL_PIECEWISE_CONS_SET = Set(
        dimen=4,
        initialize=lambda m: [
            (proj, t, intercept, slope)
            for (proj, t) in m.PROJ_WITH_FUEL_DISPATCH_POINTS
            for (intercept, slope) in m.PROJ_FUEL_USE_SEGMENTS[proj]
        ]
    )
    mod.ProjFuelUseRate_Calculate = Constraint(
        mod.PROJ_DISP_FUEL_PIECEWISE_CONS_SET,
        rule=lambda m, pr, t, intercept, incremental_heat_rate: (
            sum(m.ProjFuelUseRate[pr, t, f] for f in m.G_FUELS[m.proj_gen_tech[pr]]) >=
            # Do the startup
            m.Startup[pr, t] * m.proj_startup_fuel[pr] / m.tp_duration_hrs[t] +
            intercept * m.CommitProject[pr, t] +
            incremental_heat_rate * m.DispatchProj[pr, t]))

# TODO: switch to defining heat rates as a collection of (output_mw, fuel_mmbtu_per_h) points;
# read those directly as normal sets, then derive the project heat rate curves from those
# within define_components.
# This will simplify data preparation (the current format is hard to produce from any
# normalized database) and the import code and help the readability of this file.

def load_inputs(mod, switch_data, inputs_dir):
    """

    Import data to support modeling fuel use under partial loading
    conditions with piecewise linear incremental heat rates.

    These files are formatted differently than most to match the
    standard format of incremental heat rates. This format is peculiar
    because it formats data records that describes a fuel use curve in
    two disticnt ways. The first record is the first point on the curve,
    but all subsequent records are slopes and x-domain for each line
    segment. For a given generation technology or project, the relevant
    data should be formatted like so:

    power_start_mw  power_end_mw   ihr   fuel_use_rate
    min_load             .          .       value
    min_load          mid_load1   value       .
    mid_load1         max_load    value       .

    The first row provides the first point on the input/output curve.
    Literal dots should be included to indicate blanks.
    The column fuel_use_rate is in units of MMBTU/h.
    Subsequent rows provide the domain and slope of each line segement.
    The column ihr indicates incremental heat rate in MMBTU/MWh.
    Any number of line segments will be accepted.
    All text should be replaced with actual numerical values.

    I chose this format to a) be relatively consistent with standard
    data that is easiest to find, b) make it difficult to misinterpret
    the meaning of the data, and c) allow all of the standard data to be
    included in a single file.

    The following files are optional. If no representative data is
    provided for a generation technology, it will default to a single
    line segment with an intercept of 0 and a slope equal to the full
    load heat rate. If no specific data is provided for a project, it
    will default to its generation technology.

    gen_inc_heat_rates.tab
        generation_technology, power_start_mw, power_end_mw,
        incremental_heat_rate_mbtu_per_mwhr, fuel_use_rate_mmbtu_per_h

    proj_inc_heat_rates.tab
        project, power_start_mw, power_end_mw,
        incremental_heat_rate_mbtu_per_mwhr, fuel_use_rate_mmbtu_per_h

    """
    path = os.path.join(inputs_dir, 'gen_inc_heat_rates.tab')
    if os.path.isfile(path):
        (fuel_rate_segments, min_load, full_hr) = _parse_inc_heat_rate_file(
            path, id_column="generation_technology")
        # Check implied minimum loading level for consistency with
        # g_min_load_fraction if g_min_load_fraction was provided. If
        # g_min_load_fraction wasn't provided, set it to implied minimum
        # loading level.
        for g in min_load:
            if 'g_min_load_fraction' not in switch_data.data():
                switch_data.data()['g_min_load_fraction'] = {}
            if g in switch_data.data(name='g_min_load_fraction'):
                min_load_dat = switch_data.data(name='g_min_load_fraction')[g]
                if not approx_equal(min_load[g], min_load_dat):
                    raise ValueError((
                        "g_min_load_fraction is inconsistant with " +
                        "incremental heat rate data for generation " +
                        "technology {}.").format(g))
            else:
                switch_data.data(name='g_min_load_fraction')[g] = min_load[g]
        # Same thing, but for full load heat rate.
        for g in full_hr:
            if 'g_full_load_heat_rate' not in switch_data.data():
                switch_data.data()['g_full_load_heat_rate'] = {}
            if g in switch_data.data(name='g_full_load_heat_rate'):
                full_hr_dat = switch_data.data(name='g_full_load_heat_rate')[g]
                if abs((full_hr[g] - full_hr_dat) / full_hr_dat) > 0.01:
                    raise ValueError((
                        "g_full_load_heat_rate is inconsistent with " +
                        "incremental heat rate data for generation " +
                        "technology {}.").format(g))
            else:
                switch_data.data(name='g_full_load_heat_rate')[g] = full_hr[g]
        # Copy parsed data into the data portal.
        switch_data.data()['GEN_FUEL_USE_SEGMENTS'] = fuel_rate_segments

    path = os.path.join(inputs_dir, 'proj_inc_heat_rates.tab')
    if os.path.isfile(path):
        (fuel_rate_segments, min_load, full_hr) = _parse_inc_heat_rate_file(
            path, id_column="project")
        # Check implied minimum loading level for consistency with
        # proj_min_load_fraction if proj_min_load_fraction was provided. If
        # proj_min_load_fraction wasn't provided, set it to implied minimum
        # loading level.
        for pr in min_load:
            if 'proj_min_load_fraction' not in switch_data.data():
                switch_data.data()['proj_min_load_fraction'] = {}
            dp_dict = switch_data.data(name='proj_min_load_fraction')
            if pr in dp_dict:
                min_load_dat = dp_dict[pr]
                if abs((min_load[pr] - min_load_dat) / min_load_dat) > 0.01:
                    raise ValueError((
                        "proj_min_load_fraction is inconsistant with " +
                        "incremental heat rate data for project " +
                        "{}.").format(pr))
            else:
                dp_dict[pr] = min_load[pr]
        # Same thing, but for full load heat rate.
        for pr in full_hr:
            if 'proj_full_load_heat_rate' not in switch_data.data():
                switch_data.data()['proj_full_load_heat_rate'] = {}
            dp_dict = switch_data.data(name='proj_full_load_heat_rate')
            if pr in dp_dict:
                full_hr_dat = dp_dict[pr]
                if abs((full_hr[pr] - full_hr_dat) / full_hr_dat) > 0.01:
                    raise ValueError((
                        "proj_full_load_heat_rate is inconsistant with " +
                        "incremental heat rate data for project " +
                        "{}.").format(pr))
            else:
                dp_dict[pr] = full_hr[pr]
        # Copy parsed data into the data portal.
        switch_data.data()['PROJ_FUEL_USE_SEGMENTS'] = fuel_rate_segments


def _parse_inc_heat_rate_file(path, id_column):
    """
    Parse tabular incremental heat rate data, calculate a series of
    lines that describe each segment, and perform various error checks.

    SYNOPSIS:
    >>> import switch_mod.operations.unitcommit.fuel_use as f
    >>> (fuel_rate_segments, min_load, full_hr) = f._parse_inc_heat_rate_file(
    ...     'test_dat/inc_heat_rates.tab', 'project')
    >>> fuel_rate_segments
    {'H8': [(0.6083951310861414, 10.579), (0.5587921348314604, 10.667), (0.4963352059925083, 10.755), (0.4211891385767775, 10.843)], 'foo': [(0.0, 5.0), (-6.666666666666667, 15.0)], 'AES': [(1.220351351351352, 15.805), (1.0633432432432417, 16.106), (0.8583378378378379, 16.407), (0.605335135135138, 16.708)]}
    >>> min_load
    {'H8': 0.41760299625468167, 'foo': 0.3333333333333333, 'AES': 0.3621621621621622}
    >>> full_hr
    {'H8': 11.264189138576777, 'foo': 8.333333333333334, 'AES': 17.313335135135137}


    """
    # fuel_rate_points[unit] = {min_power: fuel_use_rate}
    fuel_rate_points = {}
    # fuel_rate_segments[unit] = [(intercept1, slope1), (int2, slope2)...]
    # Stores the description of each linear segment of a fuel rate curve.
    fuel_rate_segments = {}
    # ihr_dat stores incremental heat rate records as a list for each unit
    ihr_dat = {}
    # min_cap_factor[unit] and full_load_hr[unit] are for error checking.
    min_cap_factor = {}
    full_load_hr = {}
    # Scan the file and stuff the data into dictionaries for easy access.
    # Parse the file and stuff data into dictionaries indexed by units.
    with open(path, 'rb') as hr_file:
        dat = list(csv.DictReader(hr_file, delimiter='	'))
        for row in dat:
            u = row[id_column]
            p1 = float(row['power_start_mw'])
            p2 = row['power_end_mw']
            ihr = row['incremental_heat_rate_mbtu_per_mwhr']
            fr = row['fuel_use_rate_mmbtu_per_h']
            # Does this row give the first point?
            if(p2 == '.' and ihr == '.'):
                fr = float(fr)
                if(u in fuel_rate_points):
                    raise ValueError(
                        "Error processing incremental heat rates for " +
                        u + " in " + path + ". More than one row has " +
                        "a fuel use rate specified.")
                fuel_rate_points[u] = {p1: fr}
            # Does this row give a line segment?
            elif(fr == '.'):
                p2 = float(p2)
                ihr = float(ihr)
                if(u not in ihr_dat):
                    ihr_dat[u] = []
                ihr_dat[u].append((p1, p2, ihr))
            # Throw an error if the row's format is not recognized.
            else:
                raise ValueError(
                    "Error processing incremental heat rates for row " +
                    u + " in " + path + ". Row format not recognized for " +
                    "row " + str(row) + ". See documentation for acceptable " +
                    "formats.")

    # Make sure that each project that has incremental heat rates defined
    # also has a starting point defined.
    missing_starts = [k for k in ihr_dat if k not in fuel_rate_points]
    if missing_starts:
        raise ValueError(
            'No starting point(s) are defined for incremental heat rate curves '
            'for the following technologies: {}'.format(','.join(missing_starts)))

    # Construct a convex combination of lines describing a fuel use
    # curve for each representative unit "u".
    for u, fr_points in fuel_rate_points.items():
        if u not in ihr_dat:
            # no heat rate segments specified; plant can only be off or on at full power
            # create a dummy curve at full heat rate
            output, fuel = fr_points.items()[0]
            fuel_rate_segments[u] = [(0.0, fuel / output)]
            min_cap_factor[u] = 1.0
            full_load_hr[u] = fuel / output
            continue

        fuel_rate_segments[u] = []
        # Sort the line segments by their domains.
        ihr_dat[u].sort()
        # Assume that the maximum power output is the rated capacity.
        (junk, capacity, junk) = ihr_dat[u][len(ihr_dat[u])-1]
        # Retrieve the first incremental heat rate for error checking.
        (min_power, junk, ihr_prev) = ihr_dat[u][0]
        min_cap_factor[u] = min_power / capacity
        # Process each line segment.
        for (p_start, p_end, ihr) in ihr_dat[u]:
            # Error check: This incremental heat rate cannot be less than
            # the previous one.
            if ihr_prev > ihr:
                raise ValueError((
                    "Error processing incremental heat rates for " +
                    "{} in file {}. The incremental heat rate " +
                    "between power output levels {}-{} is less than " +
                    "that of the prior line segment.").format(
                        u, path, p_start, p_end))
            # Error check: This segment needs to start at an existing point.
            if p_start not in fr_points:
                raise ValueError((
                    "Error processing incremental heat rates for " +
                    "{} in file {}. The incremental heat rate " +
                    "between power output levels {}-{} does not start at a " +
                    "previously defined point or line segment.").format(
                        u, path, p_start, p_end))
            # Calculate the y-intercept then normalize it by the capacity.
            intercept_norm = (fr_points[p_start] - ihr * p_start) / capacity
            # Save the line segment's definition.
            fuel_rate_segments[u].append((intercept_norm, ihr))
            # Add a point for the end of the segment for the next iteration.
            fr_points[p_end] = fr_points[p_start] + (p_end - p_start) * ihr
            ihr_prev = ihr
        # Calculate the max load heat rate for error checking
        full_load_hr[u] = fr_points[capacity] / capacity
    return (fuel_rate_segments, min_cap_factor, full_load_hr)
