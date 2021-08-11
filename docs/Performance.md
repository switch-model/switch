# Performance

Memory use and solve time are two important factors that we try to keep to a minimum in our models. There are multiple
things one can do to improve performance.

## Solving methods

By far the biggest factor that impacts performance is the method used by Gurobi. The fastest method is barrier solve
without crossover (use `--recommended-fast`)
however this method often returns a suboptimal solution. The next fastest is barrier solve followed by crossover and
simplex (use `--recommended`) which almost always works. In some cases barrier solve encounters numerical issues (
see [`Numerical Issues.md`](./Numerical%20Issues.md))
in which case the slower Simplex method must be used (`--solver-options-string method=1`).

## Solver interface

Solver interfaces are how Pyomo communicates with Gurobi (or any solver).

There are two solver interfaces that you should know about: `gurobi` and `gurobi_direct`.

- When using `gurobi`, Pyomo will write the entire model to a temporary text file and then start a *separate Gurobi
  process* that will read the file, solve the model and write the results to another temporary text file. Once Gurobi
  finishes writing the results Pyomo will read the results text file and load the results back into the Python program
  before running post_solve (e.g. generate csv files, create graphs, etc). Note that these temporary text files are
  stored in `/tmp` but if you use `--recommended-debug` Pyomo and Gurobi will instead use a `temp` folder in your model.

- `gurobi_direct` uses Gurobi's Python library to create and solve the model directly in Python without the use of
  intermediate text files.

In theory `gurobi_direct` should be faster and more efficient however in practice we find that that's not the case. As
such we recommend using `gurobi` and all our defaults do so. If someone has the time they could profile `gurobi_direct`
to improve performance at which point we could make `gurobi_direct` the default (and enable `--save-warm-start` by default, see below).

The `gurobi` interface has the added advantage of separating Gurobi and Pyomo into separate threads. This means that
while Gurobi is solving and Pyomo is idle, the operating system can automatically move Pyomo's memory usage
to [virtual memory](https://serverfault.com/questions/48486/what-is-swap-memory)
which will free up more memory for Gurobi.

## Warm starting

Warm starting is the act of using a solution from a previous similar model to start the solver closer to your expected
solution. Theoretically this can help performance however in practice there are several limitations. For this section, *
previous solution* refers to the results from an already solved model that you are using to warm start the solver. *
Current solution* refers to the solution you are trying to find while using the warm start feature.

- To warm start a model use `switch solve --warm-start <path_to_previous_solution>`.

- Warm starting only works if the previous solution does not break any constraints of the current solution. This usually
  only happens if a) the model has the exact same set of variables b)
  the previous solution was "harder" (e.g. it had more constraints to satisfy).

- Warm starting always uses the slower Simplex method. This means unless you expect the previous solution and current
  solution to be very similar, it may be faster to solve without warm start using the barrier method.

- If your previous solution didn't use crossover (e.g. you used `--recommended-fast`) then warm starting will be even
  slower since the solver will need to first run crossover before warm starting.

- Our implementation of warm starting only works if your previous solution has an `outputs/warm_start.pickle`
  file. This file is only generated when you use `--save-warm-start`.

- `--save-warm-start` and `--warm-start` both use an extension of the `gurobi_direct` solver interface which is
  generally slower than the `gurobi` solver interface (see section above).
  
## Model formulation

The way the model is formulated often has an impact on performance. Here are some rules of thumb.

- For constraints, it is faster to use `<=` and `>=` rather than `==` when possible. If your constraint
should be an equality, try to think about whether it is already being pushed against one of the bounds
  by the objective function.

## Tools for improving performance

- [Memory profiler](https://pypi.org/project/memory-profiler/) for generating plots of the memory
use over time. Use `mprof run --interval 60 --multiprocess switch solve ...` and once solving is done
  run `mprof plot -o profile.png` to make the plot.
  
- [Fil Profiler](https://pypi.org/project/filprofiler/) is an amazing tool for seeing which parts of the code are
using up memory during peak memory usage.
  
- Using `switch_model.utilities.StepTimer` to measure how long certain code blocks take to run. See examples
throughout the code.