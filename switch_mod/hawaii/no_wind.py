import bisect
from pprint import pprint
from pyomo.environ import *
import switch_mod.utilities as utilities


def define_components(m):
    """
    prevent construction of new wind projects
    """
    
    # TODO: put these in a data file and share them between rps.py and no_renewables.py
    renewable_energy_sources = ['WND']
    
    def No_Wind_rule(m, proj, bld_yr):
        if m.g_energy_source[m.proj_gen_tech[proj]] in renewable_energy_sources:
            return m.BuildProj[proj, bld_yr] == 0
        else:
            return Constraint.Skip
    m.No_Wind = Constraint(m.NEW_PROJ_BUILDYEARS, rule=No_Wind_rule)

