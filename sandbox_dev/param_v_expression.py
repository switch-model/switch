"""

I wrote this script to explore the usage and limitations of parameters
and expression objects in Pyomo. I thought they were interchangable, but
when I converted a parameter to an expression I got an error where it
was being used later in an if statement as part of a test for data
validity.

The punchline is that expressions are not a drop-in replacement for
parameters and don't offer any clear and obvious benefits. If I were to
use expressions to replace derived parameters and I don't want to keep
track of which component is which object, then I should wrap all if
statements in value() expressions to force the expressions to resolve.

The best use of expressions is probably as a substitute for derived
variables. Expressions and derived variables can enable more readable
and easier-to-maintain models by replacing repeated portions of
equations with a single term. Derived variables increase the size of the
optimization problem, and effective preprocessing is required to remove
them. Expressions will not increase the size of the optimization problem
and will be resolved during compilation.

"""

from coopr.pyomo import *
mod = AbstractModel()
mod.set = Set(initialize=[1, 2])
mod.param = Param(mod.set, initialize=lambda m, i: i+10)
# This expression should always be greater than param
mod.expression = Expression(mod.set, initialize=lambda m, i: m.param[i]+1)
# exp_as_param should have a value identical to expression
mod.exp_as_param = Param(mod.set, initialize=lambda m, i: m.param[i]+1)

# This simple syntax that treats model components as normal variables
# works if both components are parameters. m.param[i] > m.exp_as_param[i]
try:
    print "A test treating both components as normal variables works " +\
          "if both components are parameters."
    mod.build_check = BuildCheck(
        mod.set, rule=lambda m, i: m.param[i] > m.exp_as_param[i])
    instance = mod.create()
    print "The test passed. This wasn't supposed to happen.\n"
except ValueError as e:
    print "The test failed as expected!\n"

# This failed check illustrates that expressions cannot be used in the
# same way as parameters. Attempting to access them in the same manner
# will return an expression object that is not evaluated into a value.
try:
    print "This method doesn't work when one component is an expression."
    mod.del_component('build_check')
    mod.build_check = BuildCheck(
        mod.set, rule=lambda m, i: m.param[i] > m.expression[i])
    instance = mod.create()
    print "The test passed. This wasn't supposed to happen.\n"
except ValueError as e:
    print "The test failed as expected!\n"

# Wrapping the overall expression in a value() statement will give the
# expected behavior, whether the components are params or expressions.
try:
    print "It will work if you wrap the whole test in a value() function."
    mod.del_component('build_check')
    mod.working_check = BuildCheck(
        mod.set, rule=lambda m, i: value(m.param[i] > m.expression[i]))
    instance = mod.create()
    print "The test passed. This wasn't supposed to happen.\n"
except ValueError as e:
    print "The test failed as expected!\n"


# If you keep track of which compoenents are expressions, you can wrap
# them in a value() function to access their value, but keeping track of
# expressions vs parameters could be cumbersomw. An alternative method
# of accessing the value is m.expression[i](), but that syntax will
# generate an error if you try to use it on a parameter. Calling
# m.expression[i].value will return the expression object, which isn't
# useful in this sort of mathematical statement, and the .value
# attribute is not defined for parameters.
try:
    print "It also works if you wrap one or both components in a value() function."
    mod.del_component('build_check')
    mod.working_check3 = BuildCheck(
        mod.set,
        rule=lambda m, i: m.param[i] > value(m.expression[i]))
    # Treating both components the same and wrapping them in value()
    # functions works but it is too verbose :/
    # rule=lambda m, i: value(m.param[i]) > value(m.expression[i]))
    instance = mod.create()
    print "The test passed. This wasn't supposed to happen.\n"
except ValueError as e:
    print "The test failed as expected!\n"
