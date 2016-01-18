# The following are development notes and a first-draft of exporting input 
# data to standard formats. I saved this in the copperplate0 example directory.
#
# I started by using DataPortal's store() function and saving to every 
# possible format, but none of them worked for me and they were minimally
# documented. 
# 
# Next, I wrote some code to dump the dictionary returned by DataPortal's
# data() method to a .dat file, and to load the data back in for comparison.
# 
# This functionality (minus my notes) has been merged into switch_mod.utilities
# and to tests/utilities_test.py: test_save_inputs_as_dat()
# I committed the code on January 14 and 15.

from pyomo.environ import *
from switch_mod.utilities import define_AbstractModel
import switch_mod.utilities
switch_model = define_AbstractModel('switch_mod', 'project.no_commit', 'fuel_cost')
switch_instance = switch_model.load_inputs(inputs_dir="inputs", attachDataPortal=True)

# I tried exporting with built-in commands, but that didn't work.
# switch_instance.DataPortal.store(filename='foo.dat')
# DataPortal will not export to .dat file, but will not throw an error. See /usr/local/lib/python2.7/site-packages/pyomo/core/plugins/data/datacommands.py

# Using other extensions for the filename will call other plugins. 
# csv and tab failed in the same way.
# switch_instance.DataPortal.store(filename='foo.csv') # or 'foo.tab'
# IOError: Unspecified model component

# json raises a different error
# switch_instance.DataPortal.store(filename='foo.json')
# TypeError: key ('NG_CC', 2020) is not a string

# excel needs an extra library, and may generate errors after I handle the pre-requisite.
# switch_instance.DataPortal.store(filename='foo.xls')
# pyutilib.component.core.core.PluginError: Cannot process data in xls files.  The following python packages need to be installed: pyodbc or pypyodbc

# I really just need a dump to a .dat file, so I'll roll my own, then possibly
# offer it as a push request to /usr/local/lib/python2.7/site-packages/pyomo/core/plugins/data/datacommands.py

# Export the data in DataPortal to a .dat file
outpath = "foo.dat"
with open(outpath, "w") as f:
	for component_name in switch_instance.DataPortal.data():
		component = getattr(switch_model, component_name)
		comp_class = type(component).__name__
		component_data = switch_instance.DataPortal.data(name=component_name)
		if comp_class == 'SimpleSet' or comp_class == 'OrderedSimpleSet':
			f.write("set " + component_name + " := ")
			f.write(' '.join(map(str, component_data))) # space-separated list
			f.write(";\n")
		elif comp_class == 'IndexedParam':
			f.write("param " + component_name + " := ")
			if component.index_set().dimen == 1:
				f.write(' '.join(str(key) + " " + str(value)
						for key,value in component_data.iteritems()))
			else:
				f.write("\n")
				for key,value in component_data.iteritems():
					f.write(" " + 
					        ' '.join(map(str, key)) + " " +
					        str(value) + "\n")
			f.write(";\n")
		elif comp_class == 'SimpleParam':
			f.write("param " + component_name + " := " + str(component_data) + ";\n")
		elif comp_class == 'IndexedSet':
			raise Error(
				"Error with IndexedSet {}. Support for .dat export is not tested.".
				format(component_name))			
# 			for key in component_data:
# 				f.write("set " + component_name + "[" + key + "] := ")
# 				f.write(' '.join(map(str, component_data[key]))) # space-separated list
# 				f.write(";\n")
		else:
			raise ValueError(
				"Error! Component type {} not recognized for model element '{}'.".
				format(comp_class, component_name))

dat = DataPortal(model=switch_model)
dat.load(filename='foo.dat')
switch_instance2 = model.create_instance(dat)
