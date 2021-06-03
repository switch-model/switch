# Graphs

This document describes how to use `switch graph` and `switch compare` as well as 
how to make new graphs.

## Using `switch graph`

Run `switch graph` in your scenario folder, this will create a `graphs` folder containing
graphs. For more options, run `switch graph --help`.

## Using `switch compare`

Run `switch compare <output_folder> <path_to_scenario_1> <path_to_scenario_2> <path_to_scenario_3> ...`.
This will create your `output_folder` and fill it with comparison graphs.

## Adding new graphs

Graphs can be defined in any module by adding the following function to the file.

```python
def graph(tools):
    # Your graphing code
```

In `graph()` you can use the `tools` object to create graphs. Here are some important methods.

- `tools.get_dataframe(csv=filename)` will return a pandas dataframe for the file called `filename`.
You can also specify `folder=tools.folders.INPUTS` to load a csv from the inputs directory.
  
- `tools.get_new_axes(out, title, note)` will return a matplotlib axes. This should
be the axes used while graphing. `out` is the name of the `.png` file that will be created
  with this graph. `title` and `note` are optional and will be the title and footnote for the graph.
  
- `tools.pd`, `tools.sns`, `tools.np`, `tools.mplt` are references to the pandas, seaborn, numpy and matplotlib libraries.
This is useful if your graphing code needs to access these libraries since it doesn't require adding an import to your file.
  
- `tools.add_gen_type_column(df)` add a column called `gen_type` to a dataframe with columns
`gen_tech` and `gen_energy_source`. `gen_type` is a user-friendly name for the technology (e.g. Nuclear instead of Uranium).
  The mapping of `gen_energy_source` and `gen_tech` to `gen_type` is defined in a `.csv` file in
  `switch_model.tools.graphing`. You can add more mappings with a different `map_name` and then
  use those mappings by specifying `map_name=` when calling `add_gen_type_colum()`.
  
- `tools.get_colors()` returns a mapping of `gen_type` to its color. This is useful for graphing
and can normally be passed straight to `color=` in standard plotting libraries. You can also
  specify a different color mapping using a similar process to above (`map_name=`)
  
