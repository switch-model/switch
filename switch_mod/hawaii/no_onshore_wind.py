from pyomo.environ import *

def define_components(m):
    """
    prevent construction of new onshore wind projects
    """
    def No_Onshore_Wind_rule(m, proj, bld_yr):
        if m.proj_gen_tech[proj] == 'OnshoreWind':
            return m.BuildProj[proj, bld_yr] == 0
        else:
            return Constraint.Skip
    m.No_Onshore_Wind = Constraint(m.NEW_PROJ_BUILDYEARS, rule=No_Onshore_Wind_rule)

