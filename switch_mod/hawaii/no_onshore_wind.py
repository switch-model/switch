from pyomo.environ import *

def define_components(m):
    """
    prevent construction of new onshore wind projects
    """
    def No_Onshore_Wind_rule(m, g, bld_yr):
        if m.gen_tech[g] == 'OnshoreWind':
            return m.BuildGen[g, bld_yr] == 0
        else:
            return Constraint.Skip
    m.No_Onshore_Wind = Constraint(m.NEW_GEN_BLD_YRS, rule=No_Onshore_Wind_rule)

