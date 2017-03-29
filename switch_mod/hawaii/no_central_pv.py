from pyomo.environ import *

def define_components(m):
    """
    prevent construction of any new central PV projects
    """
    
    # TODO: put these in a data file and share them between rps.py and no_renewables.py
    renewable_energy_technologies = ['CentralPV', 'CentralTrackingPV']
    
    def No_CentralPV_rule(m, g, bld_yr):
        if m.gen_tech[g] in renewable_energy_technologies:
            return m.BuildGen[g, bld_yr] == 0
        else:
            return Constraint.Skip
    m.No_CentralPV = Constraint(m.NEW_GEN_BLD_YRS, rule=No_CentralPV_rule)

