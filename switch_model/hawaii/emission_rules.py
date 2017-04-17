from pyomo.environ import *

def define_components(m):
    """
    prevent non-cogen plants from burning pure LSFO after 2017 due to MATS emission restrictions
    """

    # TODO: move this set into a parameter list in fuels.tab, e.g, 'banned_after', which can be a year or NULL
    m.FUEL_BANS = Set(dimen=2, initialize=[('LSFO', 2017)])
    
    m.BANNED_FUEL_DISPATCH_POINTS = Set(dimen=3, initialize=lambda m: 
        [(g, tp, f) 
            for (f, y) in m.FUEL_BANS
                for g in m.GENERATION_PROJECTS_BY_FUEL[f] # if not m.gen_is_cogen[g]
                    for pe in m.PERIODS if m.period_end[pe] >= y
                        for tp in m.TPS_IN_PERIOD[pe] if (g, tp) in m.GEN_TPS
        ]
    )
    m.ENFORCE_FUEL_BANS = Constraint(m.BANNED_FUEL_DISPATCH_POINTS, rule = lambda m, g, tp, f:
        m.DispatchGenByFuel[g, tp, f] == 0
    )
