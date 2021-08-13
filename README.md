# SWITCH for REAM

Welcome! This repository contains the SWITCH electricity planning model adapted for the
REAM research lab.

## Available documentation

In `docs/`:

- [`Overview.md`](./docs/Overiew.md): An overview of what SWITCH is and how it works, read

- [`Usage.md`](./docs/Usage.md): How to install, run or debug the different components of Switch

- [`Developing Modules.md`](./docs/Developing%20Modules.md): How to create SWITCH modules from scratch

- [`Contribute.md`](/docs/Contribute.md): How to contribute code to the project.

- [`Graphs`](/docs/Graphs.md): How to create new graphs to analyze your results.

- [`Database.md`](/docs/Database.md): All about the REAM database (e.g. how to connect to it and modify it)

- [`Numerical Solvers.md`](/docs/Numerical%20Solvers.md): Information about numerical solvers, specifically Gurobi.

- [`Numerical Issues.md`](/docs/Numerical%20Issues.md): Information about detecting and resolving numerical issues.

- [`Pandas.md`](/docs/Pandas.md): Crash course on the Pandas data manipulation library.

Finally, you can generate documentation for the SWITCH modules by running `pydoc -w switch_model` after having installed
SWITCH. This will build HTML documentation files from python doc strings which
will include descriptions of each module, their intentions, model
components they define, and what input files they expect.

## Key folders

- [`/database`](/database) Folder containing SQL scripts and files that keep track of updates to our PostgreSQL database.

- [`/examples`](/examples) Folder with numerous examples of SWITCH projects often used for testing.

- [`/switch_model`](/switch_model) Folder containing all the source code for the SWITCH modules.

- [`/switch_model/wecc`](/switch_model/wecc) Folder containing modules specific to the REAM team.

- [`/switch_model/wecc/get_inputs`](/switch_model/wecc/get_inputs) Scripts that fetch the input data from the PostgreSQL database.

- [`/tests`](/tests) Folder containing tests for SWITCH. Can be run via `python run_tests.py`.
