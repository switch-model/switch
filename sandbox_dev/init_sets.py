#!/usr/local/bin/python
# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Simple examples of initializing indexed sets.
To run interactively, use execfile('init_sets.py') on the python command line.
"""

from coopr.pyomo import *

model = AbstractModel()

model.PERIODS = Set(ordered=True)

model.DISPATCH_SCENARIO = Set()
model.dispatch_scenario_period = Param(
    model.DISPATCH_SCENARIO, within=model.PERIODS)


def init_DISPATCH_SCENARIOS_IN_PERIOD(model, period):
    return (s for s in model.DISPATCH_SCENARIO
            if model.dispatch_scenario_period[s] == period)
model.DISPATCH_SCENARIOS_IN_PERIOD = Set(
    model.PERIODS, within=model.DISPATCH_SCENARIO,
    initialize=init_DISPATCH_SCENARIOS_IN_PERIOD)


def init_SET_FROM_PARAM(model):
    return set(
        model.dispatch_scenario_period[s] for s in model.DISPATCH_SCENARIO)
model.SET_FROM_PARAM = Set(initialize=init_SET_FROM_PARAM)

instance = model.create('init_sets.dat')
instance.pprint()
