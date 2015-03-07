#!/usr/local/bin/python

"""
Demo aspects of SWITCH-Pyomo.
"""

from coopr.pyomo import *
from timescales import *
from financials import *
from load_zones import *

switch_model = AbstractModel()
define_timescales(switch_model)
define_financials(switch_model)
define_load_zones(switch_model)

switch_data = DataPortal(model=switch_model)
import_timescales(switch_model, switch_data, 'test_dat')
import_financials(switch_model, switch_data, 'test_dat')
import_load_zones(switch_model, switch_data, 'test_dat')

switch_instance = switch_model.create(switch_data)

switch_instance.pprint()
