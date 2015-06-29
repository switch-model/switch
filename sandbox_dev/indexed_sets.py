#!/usr/local/bin/python
# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
My explorations with indexed sets.
To run interactively, use `execfile('indexed_sets.py')` on the python
command line, or `from indexed_set import *`
"""
from coopr.pyomo import *
model = AbstractModel()

model.PERIODS = Set(ordered=True)

# I thought making indexed sets would allow more succinct syntax, but it
# looks like I can't continue using these sets to index further..
model.DISPATCH_SCENARIO_INDEXED_SET = Set(model.PERIODS, dimen=2, ordered=True)
# This line throws an error:  Cannot index a component with an indexed
# set
# model.DISPATCH_TIMEBLOCKS = Set(
#     model.DISPATCH_SCENARIO, dimen=3, ordered=True)


# This validate syntax is more verbose but more extensible
def DISPATCH_SCENARIO_2D_validate(model, period, dispatch_scenario):
    return period in model.PERIODS
model.DISPATCH_SCENARIO_2D = Set(
    dimen=2, validate=DISPATCH_SCENARIO_2D_validate)

model.DISPATCH_SCENARIO = Set()
model.dispatch_scenario_period = Param(
    model.DISPATCH_SCENARIO, within=model.PERIODS)
"""
Making DISPATCH_TIMEPOINTS indexed by scenario won't work because I
can't use it to subsequently index a parameter. I get an error of:
TypeError: Cannot index a component with an indexed set

model.DISPATCH_TIMEPOINTS = Set(model.DISPATCH_SCENARIO, ordered=True)
model.timepoint_weight_hours = Param(
    model.DISPATCH_TIMEPOINTS, within=NonNegativeReals)

Pyomo indexed sets are basically an associative array of sets. Each
member of the array is a set that shares the same structure. The array
indexes can be multi-dimensional and are specified at the beginning of
the Set command. The indexes are completely independent of the
dimensionality of the set. Indexed sets cannot be used to index other
parameters or other sets. An individual set contained within an
indexed set could be used for that in theory, but in practice this may
prove difficult to do in the context of an abstract model.
Example:

Set foo is indexed by a one-dimensional value 1-n and contains two
dimensional elements:
  {1: {(a b), (c d), (e f)}, 2: {(z y), (a b), (x w)}
foo[1] shares the same structure as foo[2] but is a completely distinct set.

This works, but doesn't yet capture the membership of timepoints
within a dispatch scenario.
"""
model.DISPATCH_TIMEPOINTS = Set()
model.timepoint_weight_hours = Param(
    model.DISPATCH_TIMEPOINTS, within=NonNegativeReals)

instance = model.create('indexed_sets.dat')
instance.pprint()
