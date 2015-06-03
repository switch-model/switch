# I'm extending the dynamic_constraint.py test to include an expression
# in the objective function. It seems to work here..

from pyomo.environ import *
from pyomo.opt import SolverFactory

opt = SolverFactory("glpk")
mod = AbstractModel()

mod.s = Set(initialize=[1, 2, 3])
mod.p1 = Param(mod.s, initialize=lambda m, i: i)
mod.p2 = Param(mod.s, initialize=lambda m, i: i)
mod.v = Var(mod.s)
mod.e = Expression(mod.s, initialize=lambda m, i: m.p1[i] + m.v[i])
mod.o = Objective(rule=lambda m: summation(m.v), sense=maximize)
mod.sum_items = ['e', 'p2']


def c_rule(m, s):
    return sum(getattr(m, i)[s] for i in m.sum_items) == 0

mod.c = Constraint(mod.s, rule=c_rule)
# The equivalent hard-coded constraint is:
# mod.c = Constraint(mod.s, rule=lambda m, i: m.e[i] + m.p2[i] == 0)

instance = mod.create()
results = opt.solve(instance, keepfiles=False, tee=False)
results.write()
