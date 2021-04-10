# A Guide on Numerical Solvers
by Martin Staadecker

## Content

Numerical solvers, such as Gurobi, are tools used to solve [linear programs](https://en.wikipedia.org/wiki/Linear_programming).

This document is a record of what I've learnt about using numerical solvers
while working with Switch, Pyomo and Gurobi. It includes conceptual explanations,
solutions to problems one might encounter, and techniques that I've found to be useful.

Currently, the topics covered are:

- Numerical issues while using solvers

## Numerical Issues while Using Solvers

### What are numerical issues and why do they occur?

All computers store numbers in binary, that is, all numbers are represented as a finite sequence of 0s and 1s.
Therefore, not all numbers can be perfectly stored. For example, the fraction
`1/3`, when stored on a computer, might actually be stored as `0.33333334...` since representing an infinite number of 3s
is not possible with only a finite number of 0s and 1s.

When solving linear programs, these small errors can accumulate and cause significant deviations from the
'true' result. When this occurs, we say that we've encountered *numerical issues*.

Numerical issues most often arise when our linear program contains numerical values of very small or very large
magnitudes (e.g. 10<sup>-10</sup> or 10<sup>10</sup>). This is because—due to how numbers are stored in binary—very large or
very small values are stored less accurately (and therefore with a greater error).

For more details on why numerical issues occur, the curious can read
about [floating-point arithmetic](https://en.wikipedia.org/wiki/Floating-point_arithmetic)
(how arithmetic is done on computers) and the [IEEE 754 standard](https://en.wikipedia.org/wiki/IEEE_754)
(the standard used by almost all computers today). For a deep dive into the topic,
read [What Every Computer Scientist Should Know About Floating-Point Arithmetic](https://www.itu.dk/~sestoft/bachelor/IEEE754_article.pdf).

### How to detect numerical issues in Gurobi?

Most solvers, including Gurobi, will have tests and thresholds to detect when the numerical errors become
significant. If the solver detects that we've exceeded its thresholds, it will display warnings or errors. Based
on [Gurobi's documentation](https://www.gurobi.com/documentation/9.1/refman/does_my_model_have_numeric.html), here are
some warnings or errors that Gurobi might display.

```
Warning: Model contains large matrix coefficient range
Consider reformulating model or setting NumericFocus parameter
to avoid numerical issues.
Warning: Markowitz tolerance tightened to 0.5
Warning: switch to quad precision
Numeric error
Numerical trouble encountered
Restart crossover...
Sub-optimal termination
Warning: ... variables dropped from basis
Warning: unscaled primal violation = ... and residual = ...
Warning: unscaled dual violation = ... and residual = ...
```

Many of these warnings indicate that Gurobi is trying to workaround the numerical issues. The following list gives
examples of what Gurobi does internally to workaround numerical issues.

- If Gurobi's normal barrier method fails due to numerical issues, Gurobi will switch to the slower but more reliable
  dual simplex method (often indicated by the message: `Numerical trouble encountered`).


- If Gurobi's dual simplex method encounters numerical issues, Gurobi might switch to quadruple precision
  (indicated by the warning: `Warning: switch to quad precision`). This is 20 to
  80 times slower (on my computer) but will represent numbers using 128-bits instead of the normal 64-bits, allowing
  much greater precision and avoiding numerical issues.

Sometimes Gurobi's internal mechanisms to avoid numerical issues are insufficient or not desirable
(e.g. too slow). In this case, we need to resolve the numerical issues ourselves. One way to do this is by scaling our
model.

### Scaling our model to resolve numerical issues

#### Introduction, an example of scaling

As mentioned, numerical issues occur when our linear program contains numerical values of very small or very large
magnitude (e.g. 10<sup>-10</sup> or 10<sup>10</sup>). We can get rid of these very large or small values by scaling our model. Consider
the following example of a linear program.

```
Maximize
3E17 * x + 2E10 * y
With constraints
500 * x + 1E-5 * y < 1E-5
```

This program contains many large and small coefficients that we wish to get rid of. If we multiply our objective
function by 10<sup>-10</sup>, and the constraint by 10<sup>5</sup> we get:

```
Maximize
3E7 * x + 2 * y
With constraints
5E7 * x + y < 0
```

Then if we define a new variable `x'` as 10<sup>7</sup> times the value of `x` we get:

```
Maximize
3 * x' + 2 * y
With constraints
5 * x' + y < 0
```

This last model can be solved without numerical issues since the coefficients are neither too
small or too large. Once we solve the model,
all that's left to do is dividing `x'` by 10<sup>7</sup> to get `x`.

This example, although not very realistic, gives an example
of what it means to scale a model. Scaling is often the best solution to resolving numerical issues
and can be easily done with Pyomo (see below). In some cases scaling is insufficient and other
changes need to be made, this is explained in the section *Other techniques to resolve numerical issues*.

#### Gurobi Guidelines for ranges of values

An obvious question is, what is considered too small or too large? 
Gurobi provides some guidelines on what is a reasonable range
for numerical values ([here](https://www.gurobi.com/documentation/9.1/refman/recommended_ranges_for_var.html) and [here](https://www.gurobi.com/documentation/9.1/refman/advanced_user_scaling.html)).
Here's a summary:

- Right-hand sides of inequalities and variable domains (i.e. variable bounds) should
  be on the order of 10<sup>4</sup> or less.

- The objective function's optimal value (i.e. the solution) should be between 1 and 10<sup>5</sup>.

- The matrix coefficients should span a range of six orders of magnitude
  or less and ideally between 10<sup>-3</sup> and 10<sup>6</sup>.




#### Scaling our model with Pyomo

Scaling an objective function or constraint is easy.
Simply multiply the expression by the scaling factor. For example,

```python
# Objective function without scaling
model.TotalCost = Objective(..., rule=lambda m, ...: some_expression)
# Objective function ith scaling
scaling_factor = 10 ** -7
model.TotalCost = Objective(..., rule=lambda m, ...: (some_expression) * scaling_factor)

# Constraint without scaling
model.SomeConstraint = Constraint(..., rule=lambda m, ...: left_hand_side < right_hand_side)
# Constraint with scaling
scaling_factor = 10 ** -2
model.SomeConstraint = Constraint(
  ..., 
  rule=lambda m, ...: (left_hand_side) * scaling_factor < (right_hand_side) * scaling_factor
)
```

Scaling a variable is more of a challenge since the variable
might be used in multiple places, and we don't want to need
to change our code in multiple places. The trick is to define an expression that equals our unscaled variable.
We can use this expression throughout our model, and Pyomo will still use the underlying
scaled variable when solving. Here's what I mean.

```python
from pyomo.environ import Var, Expression
...
scaling_factor = 10 ** 5
# Define the variable
model.ScaledVariable = Var(...)
# Define an expression that equals the variable but unscaled. This is what we use elsewhere in our model.
model.UnscaledExpression = Expression(..., rule=lambda m, *args: m.ScaledVariable[args] / scaling_factor)
...
```

Thankfully, I've written the `ScaledVariable` class that will do this for us.
When we add a `ScaledVariable` to our model, the actual scaled
variable is created behind the scenes and what's returned is the unscaled expression that
we can use elsewhere in our code. Here's how to use `ScaledVariable` in practice.


```python
# Without scaling
from pyomo.environ import Var
model.SomeVariable = Var(...)

# With scaling
from switch_model.utilities.scaling import ScaledVariable
model.SomeVariable = ScaledVariable(..., scaling_factor=5)
```

Here, we can use `SomeVariable` throughout our code just as before.
Internally, Pyomo (and the solver) will be using a scaled version of `SomeVariable`.
In this case the solver will use a variable that is 5 times greater
than the value we reference in our code. This means the
coefficients in front of `SomeVariable` will be 1/5th of the usual.

#### How much to scale by ?

Earlier we shared Gurobi's guidelines on the ideal range for our matrix coefficients,
right-hand side values, variable bounds and objective function. Yet how do
we know where our values currently lie to determine how much to scale them by?

For large models, determining which variables to scale and by how much can be a challenging task.

First, when solving with the flag `--stream-solver` and `-v`,
Gurobi will print to console helpful information for preliminary analysis.
Here's an example of what Gurobi's output might look like. It might also
include warnings about ranges that are too wide.

```
Coefficient statistics:
  Matrix range     [2e-05, 1e+06]
  Objective range  [2e-05, 6e+04]
  Bounds range     [3e-04, 4e+04]
  RHS range        [1e-16, 3e+05]
```

Second, if we solved our model with the flags `--keepfiles`, `--tempdir` and `--symbolic-solver-labels`, then 
we can read the `.lp` file in the temporary folder that contains the entire model including the coefficients.
This is the file Gurobi reads before solving and has all the information we might need.
However, this file is very hard to analyze manually due its size.

Third, I'm working on a tool to automatically analyze the `.lp` file and return information
useful that would help resolve numerical issues. The tool is available [here](https://github.com/staadecker/lp-analyzer).


### Other techniques to resolve numerical issues

In some cases, scaling might not be sufficient to resolve numerical issues.
For example, if variables within the same set have values that span too wide of a range,
scaling will not be able to reduce the range since scaling affects all variables
within a set equally.

Other than scaling, some techniques to resolve numerical issues are:

- Reformulating the model 
  
- Avoiding unnecessarily large penalty terms

- Changing the solver's method

- Loosening tolerances (at the risk of getting less accurate, or inaccurate results)

One can learn more about these methods 
by reading [Gurobi's guidelines on Numerical Issues](https://www.gurobi.com/documentation/9.1/refman/guidelines_for_numerical_i.html)
or a [shorter PDF](http://files.gurobi.com/Numerics.pdf) that Gurobi has released.



