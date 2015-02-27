#!/usr/local/bin/python

""" 
Demo aspects of SWITCH-Pyomo. 
"""

from coopr.pyomo import *
from timescales import *
switch_model = AbstractModel()
define_timescales(switch_model)
switch_instance = switch_model.create('test_dat/timescale_test_valid.dat')
switch_instance.pprint()
#switch_instance.scenario_total_weight.pprint()

