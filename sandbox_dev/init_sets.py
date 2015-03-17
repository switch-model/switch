#!/usr/local/bin/python

# Simple examples of initializing indexed sets.
# To run interactively, use execfile('init_sets.py') on the python command line.

from coopr.pyomo import *

model = AbstractModel()

model.INVEST_PERIODS = Set(ordered=True)

model.DISPATCH_SCENARIO = Set()
model.dispatch_scenario_period = Param(
    model.DISPATCH_SCENARIO, within=model.INVEST_PERIODS)


def init_DISPATCH_SCENARIOS_IN_PERIOD(model, period):
    return (s for s in model.DISPATCH_SCENARIO
            if model.dispatch_scenario_period[s] == period)
model.DISPATCH_SCENARIOS_IN_PERIOD = Set(
    model.INVEST_PERIODS, within=model.DISPATCH_SCENARIO,
    initialize=init_DISPATCH_SCENARIOS_IN_PERIOD)


def init_SET_FROM_PARAM(model):
    return set(
        model.dispatch_scenario_period[s] for s in model.DISPATCH_SCENARIO)
model.SET_FROM_PARAM = Set(initialize=init_SET_FROM_PARAM)

instance = model.create('init_sets.dat')
instance.pprint()
