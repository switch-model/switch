from pyomo.environ import *
import switch_mod.utilities as utilities
from util import get

# patch Pyomo if needed
import pyomo.version
if pyomo.version.version_info >= (4, 2, 0, '', 0):
    # Pyomo 4.2 mistakenly discards the original expression or rule during 
    # Expression.construct. This makes it impossible to reconstruct expressions
    # (e.g., for iterated models). So we patch it.
    # test whether patch is still needed:
    m = ConcreteModel()
    m.e = Expression(rule=lambda m: 0)
    if hasattr(m.e, "_init_rule") and m.e._init_rule is None:
        print "Patching incompatible version of Pyomo."
        old_construct = pyomo.environ.Expression.construct
        def new_construct(self, *args, **kwargs):
            # save rule and expression, call the function, then restore them
            _init_rule = self._init_rule
            _init_expr = self._init_expr
            old_construct(self, *args, **kwargs)
            self._init_rule = _init_rule
            self._init_expr = _init_expr
        pyomo.environ.Expression.construct = new_construct
    else:
        print "NOTE: Pyomo no longer removes _init_rule during Expression.construct()."
        print "      The Pyomo patch in switch_patch.py is probably obsolete."
    del m

def define_components(m):
    """Make various changes to the model to facilitate reporting and avoid unwanted behavior"""
    
    # define an indexed set of all periods before or including the current one.
    # this is useful for calculations that must index over previous and current periods
    # e.g., amount of capacity of some resource that has been built
    m.CURRENT_AND_PRIOR_PERIODS = Set(m.PERIODS, ordered=True, initialize=lambda m, p:
        # note: this is a fast way to refer to all previous periods, which also respects 
        # the built-in ordering of the set, but you have to be careful because 
        # (a) pyomo sets are indexed from 1, not 0, and
        # (b) python's range() function is not inclusive on the top end.
        [m.PERIODS[i] for i in range(1, m.PERIODS.ord(p)+1)]
    )
    
    # create lists of projects by energy source
    # we sort these to help with display, but that may not actually have any effect
    m.PROJECTS_BY_FUEL = Set(m.FUELS, initialize=lambda m, f:
        sorted([p for p in m.FUEL_BASED_PROJECTS if f in m.G_FUELS[m.proj_gen_tech[p]]])
    )
    m.PROJECTS_BY_NON_FUEL_ENERGY_SOURCE = Set(m.NON_FUEL_ENERGY_SOURCES, initialize=lambda m, s:
        sorted([p for p in m.NON_FUEL_BASED_PROJECTS if m.g_energy_source[m.proj_gen_tech[p]] == s])
    )

    # constrain DumpPower to zero, so we can track curtailment better
    # It's not clear why Dump_Power is in the model, since its effect can be achieved
    # more precisely via the dispatch decision variables. If it's a stand-in for a 
    # dump load, then that should be modified as a model-selectable demand,
    # with a limited capacity and a certain capital cost per MW of capacity (pretty
    # much like a standard project but with a negative production and no variable cost).
    m.No_Dump_Power = Constraint(m.LOAD_ZONES, m.TIMEPOINTS,
        rule=lambda m, z, t: m.DumpPower[z, t] == 0.0
    )

