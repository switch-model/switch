"""
Allow unlimited transfer of power between zones at no cost.
"""
from pyomo.environ import *

def define_components(m):
    m.TXPowerNet = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=Reals)
    # net imports into each zone from all other zones
    m.TX_Energy_Balance = Constraint(
        m.TIMEPOINTS,
        rule=lambda m, t: sum(m.TXPowerNet[z, t] for z in m.LOAD_ZONES) == 0.0
    )
    m.Zone_Power_Injections.append('TXPowerNet')
