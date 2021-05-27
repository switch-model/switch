# SWITCH for REAM

Welcome! This repository contains the SWITCH electricity planning model adapted for the
REAM research lab.

For **an overview** of what SWITCH is and how it works, read [`docs/Overview.md`](./docs/Overiew.md).

To **generate documentation**, run `pydoc -w switch_model` after having installed
SWITCH. This will build HTML documentation files from python doc strings which
will include descriptions of each module, their intentions, model
components they define, and what input files they expect.

To **see examples** of smaller SWITCH models, see the `/examples` folder. Examples
can be run with `switch solve --recommended`

To discover **how to install, run or debug** the different components of Switch, read [`docs/Usage.md`](./docs/Usage.md)

To discover **how to contribute to the model**, read [`docs/Contribute.md`](/docs/Contribute.md)

**To test** the entire codebase, run `python run_tests.py` in the root directory.

To learn about **numerical solvers** read [`docs/Numerical Solvers.md`](/docs/Numerical%20Solvers.md)