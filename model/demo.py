#!/usr/local/bin/python

"""
Demo aspects of SWITCH-Pyomo.
"""

from coopr.pyomo import *
import timescales
import financials
import load_zones

switch_model = AbstractModel()
timescales.define_components(switch_model)
financials.define_components(switch_model)
load_zones.define_components(switch_model)

switch_data = DataPortal(model=switch_model)
timescales.load_data(switch_model, switch_data, 'test_dat')
financials.load_data(switch_model, switch_data, 'test_dat')
load_zones.load_data(switch_model, switch_data, 'test_dat')

switch_instance = switch_model.create(switch_data)

switch_instance.pprint()
