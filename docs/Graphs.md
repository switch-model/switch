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

Graphs can be defined in any module by adding the following function to the file.

```python
def graph(tools):
  # Your graphing code
  ...
```

In `graph()` you can use the `tools` object to create graphs. Here are some important methods.

- `tools.get_dataframe(filename)` will return a pandas dataframe for the file called `filename`. You can also
  specify `from_inputs=True` to load a csv from the inputs directory.
  
- `tools.get_axes(out, title, note)` or `tools.get_figure(out, title, note)` will return a matplotlib axes or figure
  that should be used while graphing. When possible, always use `get_axes` over `get_figure` since
  this allows plots from different scenarios to be displayed side-by-side.
  `out` is the name of the `.png` file that will be created with this graph. `title` and `note` are optional
  and will be the title and footnote for the graph.
  
- `tools.save_figure(filename, fig)`. Some libraries (e.g. plotnine) 
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

By default, `tools.get_dataframe(filename)` will return the data for only one scenario (the one you are graphing).

Sometimes, you may wish to create a graph that compares multiple scenarios. To do this create a function
called `compare`.

```python
def compare(tools):
  # Your graphing code
  ...
```

If you call `tools.get_dataframe(...)` from within `compare`, then
`tools.get_dataframe` will return a dataframe containing the data from *all*
the scenarios. The dataframe will contain a column called `scenario` to indicate which rows correspond to which
scenarios. You can then use this column to create a graph comparing the different scenarios (still
using `tools.get_axes`).

At this point, when you run `switch compare`, your `compare(tools)` function will be called and your comparison graph
will be generated.

## Example

In this example we create a graph that shows the power capacity during each period broken down by technology.

```python
def graph(tools):
  # Get a dataframe of gen_cap.csv
  df = tools.get_dataframe(csv="gen_cap")

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

  # Get a new pair of axis to plot onto
  ax = tools.get_axes(out="capacity_per_period")

  # Plot
  df.plot(
    kind='bar',
    ax=ax,  # Notice we pass in the axis
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

