#!/usr/local/bin/python

""" 
Demo aspects of SWITCH-Pyomo. 
"""

from coopr.pyomo import *
from timescales import *
from financials import *

switch_model = AbstractModel()
define_timescales(switch_model)
define_financials(switch_model)

switch_data = DataPortal()
import_timescales(switch_model, switch_data)
import_financials(switch_model, switch_data)

switch_instance = switch_model.create(switch_data)

switch_instance.pprint()
