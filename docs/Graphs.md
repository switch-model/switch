# Graphs

This document describes how to use `switch graph` and `switch compare` as well as 
how to make new graphs.

## Using `switch graph`

Run `switch graph` in your scenario folder, this will create a `graphs` folder containing
graphs. For more options, run `switch graph --help`.

## Using `switch compare`

Run `switch compare <path_to_scenario_1> <path_to_scenario_2> <path_to_scenario_3> ...`. This will create a folder with
comparison graphs. For example, if you run
`switch compare storage ca_policies` while in the `/examples` folder, a new folder
called `compare_storage_to_ca_policies` will be created with comparison graphs (this assumes both `storage`
and `ca_policies` have already been solved).

## Adding new graphs

New graphs can be added with the `@graph(...)` annotation.
```python
from switch_model.tools.graph import graph

@graph(
  name="my_custom_graph",
  title="An example plot",
  note="Some optional note to add below the graph",
  # Other options are possible see code documentation
)
def my_graphing_function(tools):
  # Your graphing code
  ...
```

In `my_graphing_function()` you can use the `tools` object to create graphs. Here are some important methods.

- `tools.get_dataframe(filename)` will return a pandas dataframe for the file called `filename`. You can also
  specify `from_inputs=True` to load a csv from the inputs directory.
  
- `tools.get_axes()` or `tools.get_figure()` will return a matplotlib axes or figure
  that should be used while graphing. When possible, always use `get_axes` instead of `get_figure` since
  this allows plots from different scenarios to share the same figure.
  
- `tools.save_figure(fig)`. Some libraries (e.g. plotnine) 
  always generate their own figures. In this case we can add the figure
  to our outputs with this function. When possible, use `tools.get_axes()` instead.

- `tools.pd`, `tools.sns`, `tools.np`, `tools.mplt`, `tools.pn` are references to the pandas, seaborn, numpy, matplotlib
  and plotnine graphing libraries. This is useful if your graphing code needs to access these libraries since it doesn't require adding an
  import to your file.

- `tools.transform` is a reference to a `TransformTools` object that provides
  useful helper methods for modyfing a dataframe for graphing. Full documentation
  can be found in the `TransformTools` class but some examples include.
  
  - `tools.transform.build_year(df)` which will convert build years that aren't
  a period to the string `Pre-existing`.
    
  - `tools.transform.gen_type(df)` which adds a column called `gen_type` to the dataframe. 
    `gen_type` is a user-friendly name for the technology (e.g. Nuclear instead of
  Uranium) and is determined using the mappings in `inputs/graph_tech_types.csv`.
    
  - `tools.transform.timestamp(df)`: which adds columns such as the hour, the timestamp in datetime format
  in the correct timezone, etc.
    
  - `tools.transform.load_zone(df)`: Adds a column called 'region' to the dataframe which
  normally corresponds to the load zone state.
    
- `tools.get_colors()` returns a mapping of `gen_type` to its color. This is useful for graphing and can normally be
  passed straight to `color=` in standard plotting libraries. The color mapping is based on `inputs/graph_tech_colors.csv`.

## Adding a comparison graph

Sometimes you may want to create graphs that compare data from multiple scenarios.
To do this, add `supports_multi_scenario=True` inside the `@graph()` decorator.

```python
from switch_model.tools.graph import graph

@graph(
  name="my_custom_comparison_graph",
  title="My Comparison plot",
  supports_multi_scenario=True,
  # Instead of supports_multi_scenario, you can use
  # requires_multi_scenario if you want the graphing function
  # to *only* be run when we have multiple scenarios.
  # requires_multi_scenario=True,
)
def my_graphing_comparison_function(tools):
    # Read data from all the scenarios
    df = tools.get_dataframe("some_file.csv")
    # Plot data
    ...
```

Now everytime you call `tools.get_dataframe(filename)`, data for *all* the scenarios
gets returned. The way this works is that the 
returned dataframe will contain a column called `scenario_name` 
to indicate which rows correspond to which scenarios. 
You can then use this column to create a graph comparing the different scenarios (still
using `tools.get_axes`).

At this point, when you run `switch compare`, your `my_graphing_comparison_function` function will be called and your comparison graph
will be generated.

## Example

In this example we create a graph that shows the power capacity during each period broken down by technology.

```python
from switch_model.tools.graph import graph

@graph(
  "capacity_per_period",
  title="Capacity per period"
)
def graph(tools):
    # Get a dataframe of gen_cap.csv
    df = tools.get_dataframe("gen_cap.csv")

    # Add a 'gen_type' column to your dataframe
    df = tools.transform.gen_type(df)

    # Aggregate the generation capacity by gen_type and PERIOD
    df = df.pivot_table(
        index='PERIOD',
        columns='gen_type',
        values='GenCapacity',
        aggfunc=tools.np.sum,
        fill_value=0  # Missing values become 0
    )

    # Plot
    df.plot(
        kind='bar',
        ax=tools.get_axes(),
        stacked=True,
        ylabel="Capacity Online (MW)",
        xlabel="Period",
        color=tools.get_colors(len(df.index))
    )
```

Running `switch graph` would run the `graph()` function above and create 
`capacity_per_period.png` containing your plot.

Running `switch compare` would create `capacity_per_period.png` containing
your plot side-by-side with the same plot but for the scenario you're comparing to.

### Testing your graphs

To test your graphs, you can run `switch graph` or `switch compare`. However,
this takes quite some time. If you want to test just one graphing function
you can run `switch graph/compare -f FIGURE`. This will run only the graphing function
you've defined. Here `FIGURE` should be the name of the graph (the first
argument in `@graph()`, so `capacity_per_period` in the example above).

### Creating graphs outside of SWITCH

Sometimes you may want to create graphs but don't want to permently add
them to the switch code. To do this create the following Python file anywhere
on your computer.

```python
from switch_model.tools.graph import graph
from switch_model.tools.graph.cli_graph import main as graph

@graph(
  ...
)
def my_first_graph(tools):
    ...

@graph(
  ...
)
def my_second_graph(tools):
  ...

if __name__=="__main__":
    graph(["--ignore-modules-txt"])
```

