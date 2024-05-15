SYNOPSIS
	switch solve --verbose --log-run --exclude-module switch_model.balancing.diagnose_infeasibility
	switch solve --verbose --log-run

This case is used to test the diagnose_infeasibility module and possibly to
ensure Switch reports infeasible models correctly with various solvers.

The diagnose_infeasibility module ignores financial costs and minimizes
constraint violations instead. This model has too little capacity available to
meet demand. To ensure it has a unique constraint-minimizing solution, we
include the transmission.local_td module, which creates losses between the
generation node and the load node. Consequently, constraint violations can be
minimized by violating the load-balancing constraint at the load node, rather
than over-producing upstream. (Various upstream overproduction options would
produce the same amount of violation of the construction-dispatch balance but
with different costs, so different solvers could report different total_cost
values, interfering with the test suite.)

This model is based on "new_builds_only", but with caps on construction
that make the model infeasible. Geothermal has also been made non-baseload so
it can be ramped down when needed. (In earlier versions, if geothermal was
forced on, it created equal-violation choices between oversupply in one hour vs
undersupply in the other, which have different costs.)

Expected warnings:

```
WARNING: Constraint Distributed_Energy_Balance['South', 1] violated by -5.944 units.

NOTE: Module switch_model.balancing.diagnose_infeasibility was used for this run.
This minimizes violations of constraints, ignoring financial costs. Results from
this run (other than constraint violations) should not be used for analysis.
```
