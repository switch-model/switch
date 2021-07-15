# Numerical Solvers
by Martin Staadecker

## Introduction

Numerical solvers, such as [Gurobi](https://gurobi.com), are tools used to solve [linear programs](https://en.wikipedia.org/wiki/Linear_programming).

This document is a record of what I've learnt about using numerical solvers
while working with Switch, Pyomo and Gurobi.

## Gurobi resources

The best resource when working with Gurobi is [Gurobi's reference manual](https://www.gurobi.com/documentation/9.1/refman/index.html).

A few especially useful pages are:

- Gurobi's [parameter guidelines for continuous models](https://www.gurobi.com/documentation/9.1/refman/continuous_models.html)

- Gurobi's [parameter list](https://www.gurobi.com/documentation/9.1/refman/parameters.html#sec:Parameters) especially the [`Method` parameter](https://www.gurobi.com/documentation/9.1/refman/method.html).

- Gurobi's [guidelines for numerical issues](https://www.gurobi.com/documentation/9.1/refman/guidelines_for_numerical_i.html) (see `docs/Numerical Issues.md`).

## Specifying parameters

To specify a Gurobi parameter use the following format:

`switch solve --solver gurobi --solver-options-string "Parameter1=Value Parameter2=Value"`.

We recommend always using `"method=2 BarHomogeneous=1 FeasibilityTol=1e-5 crossover=0"`
as your base parameters (this is what `switch solve --recommended` does).

## Solving Methods

There are two methods that exist when solving a linear program.
The first is the Simplex Method and the second is the Barrier
solve method also known as interior-point method (IPM).

- The Simplex Method is more robust than IPM (it can find
  an optimal solution even with numerically challenging problems).
  
- The Simplex Method uses only 1 thread while the Barrier method can
leverage multiple threads.
  
- The Barrier method is significantly faster for our model sizes.

- Running `switch solve --recommended` selects the Barrier method.

- By default, when the Barrier method finishes it converts its solution
to a simplex solution in what is called the crossover phase (see [details](https://www.gurobi.com/documentation/9.1/refman/barrier_logging.html)).
  This crossover phase takes the most time and is not necessary. Therefore is gets
  disabled by the `--recommended` flag.
  
- The crossover phase *is* important if the barrier method produces a sub-optimal solution.
  In this case use `--recommended-robust` to enable the crossover.
  
