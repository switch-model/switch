from coopr.pyomo import *
import timescales
import financials
import load_zones
import fuels
import gen_tech
import project_build
switch_model = AbstractModel()
timescales.define_components(switch_model)
financials.define_components(switch_model)
load_zones.define_components(switch_model)
fuels.define_components(switch_model)
gen_tech.define_components(switch_model)
project_build.define_components(switch_model)
switch_data = DataPortal(model=switch_model)
inputs_dir = 'test_dat'
timescales.load_data(switch_model, switch_data, inputs_dir)
financials.load_data(switch_model, switch_data, inputs_dir)
load_zones.load_data(switch_model, switch_data, inputs_dir)
fuels.load_data(switch_model, switch_data, inputs_dir)
gen_tech.load_data(switch_model, switch_data, inputs_dir)
project_build.load_data(switch_model, switch_data, inputs_dir)
switch_instance = switch_model.create(switch_data)
