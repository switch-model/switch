# Contributing Code

This document describes the best practices for contributing code.

## The process

Whenever you wish to make a change to the switch code, use the following
procedure.

1. Create a new git branch.

2. Make your changes on that branch.

3. Once your changes are final and ready to be added to the switch main
branch, create a pull request on Github.
   
4. Get someone to review and then merge your changes on Github.

For more information read [this excellent guide](https://guides.github.com/introduction/flow/) (5 min read).

## Testing your changes

Before contributing code, it's important to test your changes.

The most important is to run `switch compare` between the previous stable version and the new version
to ensure there's no unexpected change. Beyond that, switch doesn't have an 
excellent way to test its code so you mainly need to be careful and compare 
the results before and after your changes to see if your change is working 
as expected. 

Switch does however have a small test suite which you can run by calling
`python run_tests.py` in the switch root directory. This will ensure
that the results of the examples in `examples/` haven't changed. This is
useful if you're making a change to the switch code that you believe should 
not change the final results (e.g. a refactor). If your changes are
supposed to alter the results of the examples, you'll need
to follow the instructions that appear on screen to suppress the errors
produced by `python run_tests.py`.

## Contributing graphs

Read [`docs/Graphs.md`](./Graphs.md) to see learn to add graphs.

## Modifying the database

Read [`docs/Database.md`](./Database.md) to learn about the database.

## Outputting results

Once the model is solved, the `post_solve()` function in each module is called.
Within the `post_solve()` function you may 

- Call `write_table()` to create
a .csv file with data from the solution (see existing modules for examples).
  
- Call `add_info()` (from `utilities/result_info.py`) to add a line 
of information to the `outputs/info.txt` file. `add_info()` can also be added to `graph()`.

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
        instance.TIMEPOINTS, # Set that the values function will iterate over
        output_file=os.path.join(outdir, "my_table.csv"),
        headings=("timepoint", "some value"),
        values=lambda m, t: (t, m.some_value[t])
    )
```