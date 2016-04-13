import bisect
from pprint import pprint
from pyomo.environ import *
import switch_mod.utilities as utilities


def define_components(m):
    """

    """
    ###################
    # prevent construction of any new renewable projects (useful for "business as usual" baseline)
    ##################
    
    # TODO: put these in a data file and share them between rps.py and no_renewables.py
    renewable_energy_sources = ['WND', 'SUN', 'Biocrude', 'Biodiesel', 'MLG']
    
    def No_Renewables_rule(m, proj, bld_yr):
        if m.g_energy_source[m.proj_gen_tech[proj]] in renewable_energy_sources:
            return m.BuildProj[proj, bld_yr] == 0
        else:
            return Constraint.Skip
    m.No_Renewables = Constraint(m.NEW_PROJ_BUILDYEARS, rule=No_Renewables_rule)

