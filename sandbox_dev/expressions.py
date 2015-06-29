#!/usr/local/bin/python
# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.


"""
Test the behavior of Pyomo Expression objects. Can they directly replace
a derived variable in the model, or are they evaluated to a numeric value
during compilation?

Answer: Yes, their algebraic formulation is preserved through compilation
and they can replace derived variables.

"""

from pyomo.environ import *
from pyomo.opt import SolverFactory

opt = SolverFactory("glpk")
mod = ConcreteModel()
mod.PERIODS = Set(initialize=[1, 2])
mod.Build = Var(mod.PERIODS, within=PositiveReals, bounds=(0, 7))
mod.max_total_build = Param(initialize=10)

# I could store the cumulative builds in a variable, but this could
# increase the number of variables in the optimization.
mod.CumulativeBuild = Var()
mod.Cumulative_Build_def = Constraint(
    rule=lambda m: m.CumulativeBuild == sum(m.Build[p] for p in mod.PERIODS))
mod.Max_CumulativeBuild = Constraint(
    rule=lambda m: m.CumulativeBuild <= m.max_total_build)
mod.Obj = Objective(rule=lambda m: sum(m.Build[p] for p in m.PERIODS),
                    sense=maximize)

instance = mod.create()
results = opt.solve(instance, keepfiles=False, tee=False)
results.write()

# I could alternately define an Expression to store the sum of the
# builds, which should simplify out of the model before optimization.
mod.del_component('CumulativeBuild')
mod.del_component('Cumulative_Build_def')
mod.del_component('Max_CumulativeBuild')

mod.CumulativeBuild = Expression(
    initialize=lambda m: sum(m.Build[p] for p in mod.PERIODS))
mod.Max_CumulativeBuild = Constraint(
    rule=lambda m: m.CumulativeBuild <= m.max_total_build)

instance = mod.create()
results = opt.solve(instance, keepfiles=False, tee=False)
results.write()

# Yup, you can see the same results, and that the compiled problem had
# one fewer variable than the original formulation. Expressions can replace
# derived variables!
