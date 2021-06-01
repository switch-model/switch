# Usage

## Prerequisites

1. Install [Python](https://www.python.org/downloads/) (at least version 3.8). You need
   Python since the entire model is written in Python and is run through Python.

2. Install [Gurobi](https://www.gurobi.com/downloads/gurobi-optimizer-eula/) or another
   solver (e.g. GPLK). Gurobi requires applying for a free academic license on their website.

3. Install [Anaconda](https://www.anaconda.com/products/individual) (or [miniconda](https://docs.conda.io/en/latest/miniconda.html)
   for a lightweight version that works just the same). Anaconda allows you to work
   in multiple virtual environments which is often helpful. You can also use Python's built-in
   `venv` package.

4. Install [Git](https://git-scm.com/) (you can learn more about Git [here](https://www.git-scm.com/doc)).

## Install

1. Clone this repository to your computer:`git clone https://github.com/REAM-lab/switch`

2. Navigate to the repository: `cd switch`.

3. Create a Python virtual environment from where you'll run Switch: `conda create --name switch`.

4. Activate the newly created environment: `conda activate switch`.

5. Install the `switch_model` library using: `pip install --editable .[dev]`. Note
   the `--editable` flag indicating that the `switch` command will always use your latest local
   copy. That is, you don't need to reinstall the package after making a change to it.

6. Run `switch --help` to make sure your package installed properly.

## Preparing a scenario

1. Run `switch new` in an empty folder. This will create a `config.yaml` file.

2. In the `config.yaml` file, specify which scenario you wish to run by specifying
the `scenario_id`. Note that if your scenario doesn't already exist in the database,
   you'll need to create it.
   
3. Run `switch get_inputs` to download the scenario input data.

## Running a scenario

1. Run `switch solve --recommended` to solve the scenario. For more options,
run `switch solve --help`
   
## Analyzing results

1. Run `switch graph` to generate graphs for the scenario.

2. Optionally, to compare your results to another scenario's results (e.g. a baseline),
run `switch compare`.
   
## Debugging a model

There are a few techniques to debug a model depending on the issue encountered.

- All your usual Python debugging techniques are valid. For example, inspecting
the error message and stacktrace then looking at the source code to try to figure out what
  went wrong.
  
- You can add [`breakpoint()`](https://docs.python.org/3/library/functions.html#breakpoint) anywhere in the Python code to pause execution and inspect what is happening. You can also
run `switch solve --enable-breakpoints` to automatically pause at key points.

- When in a breakpoint, you can inspect a specific model expression or variable
  with `pprint()`. For example you can run, `model.BuildGen.pprint()` to see the values
  for the `BuildGen` variable.
  
- Although this is rarely necessary, if you wish to see what is being passed
to Gurobi, you can run `switch solve --recommended-debug`. This will create
  a `temp` folder that will contain many files including a `.pyomo.lp` file with
  all the linear programming equations and a `.gurobi.txt` with the raw results
  from solving the linear program. This is sometimes useful if you wish to debug
  directly in Gurobi since gurobi's console [can directly read](https://www.gurobi.com/documentation/9.1/refman/py_read.html) and load the `.pyomo.lp`
  file.
  
- If a model is infeasible you can use `--gurobi-find-iis` with `--recommended-debug`
to automatically generate a `.iis` file which will describe the minimal set of equations
  that make the model infeasible.