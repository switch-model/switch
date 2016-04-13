from pyomo.environ import *

def define_components(m):
    """
    prevent construction of any new central PV projects
    """
    
    # TODO: put these in a data file and share them between rps.py and no_renewables.py
    renewable_energy_technologies = ['CentralPV', 'CentralTrackingPV']
    
    def No_CentralPV_rule(m, proj, bld_yr):
        if m.proj_gen_tech[proj] in renewable_energy_technologies:
            return m.BuildProj[proj, bld_yr] == 0
        else:
            return Constraint.Skip
    m.No_CentralPV = Constraint(m.NEW_PROJ_BUILDYEARS, rule=No_CentralPV_rule)

