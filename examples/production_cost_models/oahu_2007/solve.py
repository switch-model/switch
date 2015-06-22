#!/usr/local/bin/python

import sys, os
sys.path.append("/Users/matthias/Dropbox/Research/shared/Switch-Hawaii/pyomo/switch_py/")
import util

from pyomo.environ import *
from pyomo.opt import SolverFactory
import switch_mod.utilities as utilities

switch_modules = (
    'switch_mod', 'project.unitcommit', 'project.unitcommit.discrete', 'fuel_cost'
)
utilities.load_modules(switch_modules)
switch_model = utilities.define_AbstractModel(switch_modules)
inputs_dir = 'inputs'
switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
switch_instance = switch_model.create(switch_data)

opt = SolverFactory("cplex")

results = opt.solve(switch_instance, keepfiles=False, tee=True, symbolic_solver_labels=True)
# results.write()
if switch_instance.load(results):
    # switch_instance.pprint()
    # now you have to write the results out -- 
    # dispatch from each project or class of project, new build, total cost, etc.
    # e.g., switch_instance.BuildProj[PROJECT_BUILDYEARS], switch_instance.DispatchProj[PROJ_DISPATCH_POINTS]
    if util.interactive_session:
        print "Model solved successfully."
    try:
        util.write_table(switch_instance, switch_instance.TIMEPOINTS,
            output_file=os.path.join("outputs", "dispatch.txt"), 
            headings=("timepoint_label",)+tuple(switch_instance.PROJECTS),
            values=lambda m, t: (m.tp_label[t],) + tuple(
                m.DispatchProj[p, t] if (p, t) in m.PROJ_DISPATCH_POINTS else 0.0 
                for p in m.PROJECTS
            )
        )
        util.write_table(switch_instance, switch_instance.TIMEPOINTS, 
            output_file=os.path.join("outputs", "load_balance.txt"), 
            headings=("timepoint_label",)+tuple(switch_instance.LZ_Energy_Balance_components),
            values=lambda m, t: (m.tp_label[t],) + tuple(
                sum(getattr(m, component)[lz, t] for lz in m.LOAD_ZONES)
                for component in m.LZ_Energy_Balance_components
            )
        )
    except Exception, e:
        print "An error occurred while writing results:"
        print "ERROR:", e
    if util.interactive_session:
        print "Solved model is available as switch_instance."
else:
    print "ERROR: unable to load solver results. Problem may be infeasible."
