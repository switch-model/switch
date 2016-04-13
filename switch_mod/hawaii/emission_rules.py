from pyomo.environ import *

def define_components(m):
    """
    prevent non-cogen plants from burning pure LSFO after 2017 due to MATS emission restrictions
    """

    # TODO: move this set into a parameter list in fuels.tab, e.g, 'banned_after', which can be a year or NULL
    m.FUEL_BANS = Set(dimen=2, initialize=[('LSFO', 2017)])
    
    m.BANNED_FUEL_DISPATCH_POINTS = Set(dimen=3, initialize=lambda m: 
        [(pr, tp, f) 
            for (f, y) in m.FUEL_BANS
                for pr in m.PROJECTS_BY_FUEL[f] # if not m.g_is_cogen[m.proj_gen_tech[pr]]
                    for pe in m.PERIODS if m.period_end[pe] >= y
                        for tp in m.PERIOD_TPS[pe] if (pr, tp) in m.PROJ_DISPATCH_POINTS
        ]
    )
    m.ENFORCE_FUEL_BANS = Constraint(m.BANNED_FUEL_DISPATCH_POINTS, rule = lambda m, pr, tp, f:
        m.DispatchProjByFuel[pr, tp, f] == 0
    )
