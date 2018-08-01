"""
Special modeling for Lake Wilson - relax daily energy balance by 10 MW to account
for net inflow.
"""
from pyomo.environ import *

def define_components(m):
    def rule(m):
        g = 'Oahu_Lake_Wilson'
        inflow = 10.0
        if g in m.GENERATION_PROJECTS:
            for t in m.TPS_FOR_GEN[g]:
                # assign new energy balance with extra inflow, and allow spilling
                m.Track_State_Of_Charge[g, t] = (
                    m.StateOfCharge[g, t]
                    <=
                    m.StateOfCharge[g, m.tp_previous[t]]
                    + (m.ChargeStorage[g, t] * m.gen_storage_efficiency[g]
                    - m.DispatchGen[g, t]) * m.tp_duration_hrs[t]
                    # allow inflow only if capacity is built
                    + inflow * m.tp_duration_hrs * m.GenCapacityInTP[g] / m.gen_unit_size[g]
                )
    m.Add_Lake_Wilson_Inflow = BuildAction(rule=rule)

# TODO: don't allow zero crossing when calculating reserves available
# see http://www.ucdenver.edu/faculty-staff/dmays/3414/Documents/Antal-MS-2014.pdf
