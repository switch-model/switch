import bisect
from pprint import pprint
from pyomo.environ import *
import switch_model.utilities as utilities


def define_components(m):
    """
    prevent construction of new wind projects
    """
    
    # TODO: put these in a data file and share them between rps.py and no_renewables.py
    renewable_energy_sources = ['WND']
    
    def No_Wind_rule(m, g, bld_yr):
        if m.g_energy_source[m.gen_tech[g]] in renewable_energy_sources:
            return m.BuildGen[g, bld_yr] == 0
        else:
            return Constraint.Skip
    m.No_Wind = Constraint(m.NEW_GEN_BLD_YRS, rule=No_Wind_rule)

