# Using Pandas

[Pandas](https://pandas.pydata.org/) is a Python library that is used for data analysis and manipulation.

In SWITCH, Pandas is mainly used to create graphs and also output files after solving.

This document gives a brief overview of key concepts and commands
to get started with Pandas. There are a lot better resources available
online teaching Pandas, including entire online courses.

Most importantly, the Pandas [documentation](https://pandas.pydata.org/docs/) 
and [API reference](https://pandas.pydata.org/docs/reference/index.html#api) should be your go-to
when trying to learn something new about Pandas.

## Key Concepts

### DataFrame

Dataframes is the main Pandas data structure and is responsible for
storing tabular data.
Dataframes have rows, columns and labelled axes (e.g. row or column names).
When manipulating data,
the common practice is to store your main dataframe in a variable called `df`.

### Series

A series can be thought of as a single column in a dataframe.
It's a 1-dimensional array of values.

### Indexes

Pandas has two ways of working with dataframes: with or without custom indexes.
Custom indexes are essentially labels for each row. For example, the following
dataframe has 4 columns (A, B, C, D) and a custom index (the date).

```
                   A         B         C         D
2000-01-01  0.815944 -2.093889  0.677462 -0.982934
2000-01-02 -1.688796 -0.771125 -0.119608 -0.308316
2000-01-03 -0.527520  0.314343  0.852414 -1.348821
2000-01-04  0.133422  3.016478 -0.443788 -1.514029
2000-01-05 -1.451578  0.455796  0.559009 -0.247087
```

The same dataframe can be expressed without the custom index as follows.
Here the date is a column just like the others and the index is the 
default index (just the row number).

```
        date         A         B         C         D
0 2000-01-01  0.815944 -2.093889  0.677462 -0.982934
1 2000-01-02 -1.688796 -0.771125 -0.119608 -0.308316
2 2000-01-03 -0.527520  0.314343  0.852414 -1.348821
3 2000-01-04  0.133422  3.016478 -0.443788 -1.514029
4 2000-01-05 -1.451578  0.455796  0.559009 -0.247087
```

Using custom indexes is quite powerful but more advanced. When starting
out it's best to avoid custom indexes.

### Chaining

Every command you apply on a dataframe *returns* a new dataframe.
That is commands *do not* modify the dataframe they're called on.

For example, the following has no effect.

`df.groupby("country")`

Instead, you should always update your variable with the returned result.
For example,

`df = df.groupby("country")`

This allows you to "chain" multiple operations together. E.g.

`df = df.groupby("country").rename(...).some_other_command(...)`

## Useful commands

- `df = pandas.read_csv(filepath, index_col=False)`. This command
reads a csv file from filepath and returns a dataframe that gets stored
  in `df`. `index_col=False` ensures that no custom index is automatically
  created.
  
- `df.to_csv(filepath, index=False)`.
This command will write a dataframe to `filepath`. `index=False` means
  that the index is not written to the file. This should
  be used if you're not using custom indexes since you probably don't
  want the default index (just the row numbers) to be outputted to your csv.
  
- `df["column_name"]`: Returns a *Series* containing the values for that column.

- `df[["column_1", "column_2"]]`: Returns a *DataFrame* containing only the specified columns.

- `df[df["column_name"] == "some_value"]`: Returns a dataframe with only the rows
where the condition in the square brackets is met. In this case we filter out
  all the rows where the value under `column_name` is not `"some_value"`.
  
- `df.merge(other_df, on=["key_1", "key_2"])`: Merges `df` with `other_df`
where the columns over which we are merging are `key_1` and `key_2`.
  
- `df.info()`: Prints the columns in the dataframe and some info about each column.

- `df.head()`: Prints the first few rows in the dataframe.

- `df.drop_duplicates()`: Drops duplicate rows from the dataframe

- `Series.unique()`: Returns a series where duplicate values are dropped.

## Example

This example shows how we can use Pandas to generate a more useful view
of our generation plants from the SWITCH input files.

```python
import pandas as pd

# READ
kwargs = dict(
  index_col=False,
  dtype={"GENERATION_PROJECT": str},  # This ensures that the project id column is read as a string not an int
)
gen_projects = pd.read_csv("generation_projects_info.csv", *kwargs)
costs = pd.read_csv("gen_build_costs.csv", *kwargs)
predetermined = pd.read_csv("gen_build_predetermined.csv", *kwargs)

# JOIN TABLES
gen_projects = gen_projects.merge(
  costs,
  on="GENERATION_PROJECT",
)

gen_projects = gen_projects.merge(
  predetermined,
  on=["GENERATION_PROJECT", "build_year"],
  how="left"  # Makes a left join
)

# FILTER
# When uncommented will filter out all the projects that aren't wind.
# gen_projects = gen_projects[gen_projects["gen_energy_source"] == "Wind"]

# WRITE
gen_projects.to_csv("projects.csv", index=False)
```

If you run the following code snippet in the `inputs folder` it will create a `projects.csv` file
containing the project data, cost data and prebuild data all in one file.
