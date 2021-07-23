## Developing modules

Modules are the core elements of SWITCH. Each module defines a specific functionality for the model. For example,
the `switch_model.generators.core.build` defines how generators are allowed to be built while `switch_model.timescales`
defines how time is handled in SWITCH.

There are 3 important parts to any module.

1. `define_components(model)`: This function specifies the Pyomo Sets, Parameters, Variables and Expressions for the module
   as well as the input files that should be used. It's the first thing that gets called when you run `switch solve` as
   it creates the Pyomo model.

2. `post_solve()`: This function gets run after the solver has found the optimal solution. This is where you can output
   results to e.g. a csv file.

3. Functions with the `@graph(...)` decorator. These functions get called last and are responsible for creating graphs
   for analysis using the data from the csv files you created in `post_solve()`.

There are also a few other components that you may encounter:

- `load_inputs()`: This function is the old way of loading inputs from .csv files into the model. It gets called right
  after `define_components()`. Now the prefered way of loading inputs is by using `input_file=`
  (see next section for details).
  
- `define_dynamic_lists(model)` and `define_dynamic_components(model)`: 
Some modules need to define objects to be shared across multiple modules. 
  The best example of this is `switch_model.balancing.load_zones` which
  allows different modules to add elements to a dynamic list that is defined
  in `define_dynamic_lists`. Then in `define_dynamic_components` it defines
  the energy balance constraint using the dynamic list. See the module for details.

## Writing `define_components()`

`define_components(mod)` takes in the model as an argument and is responsible
for adding constraints, expressions, variables, sets or parameters to the model.

Sometimes Sets or Parameters should be initialized from an input csv file.
If this is the case, add the following arguments to the component definition: 
`input_file`, `input_optional` (optional), `input_column` (optional).

For example the following code snippet defines a set and a parameter
indexed over that set. Both the set and parameter are initialized from
the input.csv file.

```python
from switch_model.utilities.pyo import *

def define_components(mod):
    mod.SetA = Set(
        dimen=2,
        input_file="input.csv",
        input_optional=True, # the default is False
    )

    mod.some_indexed_param = Param(
        mod.SetA,
        input_file="input.csv",
        input_column="param1" # default is the name of the component, in this case 'some_indexed_param'
    )
```

## Writing `post_solve()`

Once the model is solved, the `post_solve()` function in each module is called. Within the `post_solve()` function you
may

- Call `write_table()` to create a .csv file with data from the solution (see existing modules for examples).

- Call `add_info()` (from `utilities/result_info.py`) to add a line of information to the `outputs/info.txt`
  file. `add_info()` can also be added to `graph()`.

### Example

```python
from switch_model.utilities.results_info import add_info
from switch_model.reporting import write_table
import os

...


def post_solve(instance, outdir):
    ...
    # This will add the a line to info.txt in the outputs folder
    add_info("Some important value", instance.important_value)
    ...
    # This will create my_table.csv
    write_table(
        instance,
        instance.TIMEPOINTS,  # Set that the values function will iterate over
        output_file=os.path.join(outdir, "my_table.csv"),
        headings=("timepoint", "some value"),
        values=lambda m, t: (t, m.some_value[t])
    )
```