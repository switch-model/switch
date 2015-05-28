# Try to make a constraint that will sum over a list of model compoents.
# This can allow different modules to independently add compoenents to
# this list. My use case is making energy balance constraints more
# modular so that aspects like transmission, storage or demand response
# can optionally be included.

# The results of this investigation indicate that I could implement a
# dynamic list for an energy balance constraint by defining the list in
# load_zones.define_components(), and load_zones is called before most
# other modules. Other modules' define_components() methods will be
# called and some, such as project_dispatch, will register their
# contributions to the bus by adding component names to the list. As a
# final step, a new method define_components_final() will be called on each
# module, and load_zones.define_components_final() will define a satisfy_load()
# constraint that uses the list for the summation.


from pyomo.environ import *
from pyomo.opt import SolverFactory

opt = SolverFactory("glpk")
mod = AbstractModel()

mod.s = Set(initialize=[1, 2, 3])
mod.p = Param(mod.s, initialize=lambda m, i: i*2)
mod.v = Var(mod.s)
mod.o = Objective(rule=lambda m: summation(m.v), sense=maximize)
mod.sum_items = ['p', 'v']


def c_rule(m, s):
    return sum(getattr(m, i)[s] for i in m.sum_items) == 0

mod.c = Constraint(mod.s, rule=c_rule)
# The equivalent hard-coded constraint is:
# mod.c = Constraint(mod.s, rule=lambda m, i: m.p[i] + m.v[i] == 0)

instance = mod.create()
results = opt.solve(instance, keepfiles=False, tee=False)
results.write()


mod.v2 = Var(mod.s, bounds=(-1, 1))
mod.sum_items.append('v2')

try:
    instance = mod.create()
except ValueError as e:
    print "Adding a summation term after the constraint was defined "
    print "caused a failure during model instantiation because the "
    print "constraint that needs the summation term is instantiated "
    print "before the summation term that it depends on.\n"
else:
    results = opt.solve(instance, keepfiles=False, tee=False)
    results.write()
