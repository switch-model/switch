"""
Code used by 'switch compare' and 'switch graph' to running the graphing functions.
"""
# Standard packages
import importlib
import traceback
import os
import sys
import warnings
from typing import List, Dict, Tuple

# Third-party packages
import numpy as np
import pandas as pd
from PIL import Image
from matplotlib import pyplot as plt
import seaborn as sns
import matplotlib
import plotnine

# Local imports
from switch_model.utilities import StepTimer, get_module_list


class Scenario:
    """
    Stores the information related to a scenario such as the scenario name (used while graphing)
    and the scenario path.

    Also allows doing:

    with scenario:
        # some operation

    Here, some operation will be run as if the working directory were the directory of the scenario
    """

    root_path = os.getcwd()

    def __init__(self, rel_path, name):
        self.path = os.path.normpath(os.path.join(Scenario.root_path, rel_path))
        self.name = name

        if not os.path.isdir(self.path):
            raise Exception(f"Directory does not exist: {self.path}")

    def __enter__(self):
        os.chdir(self.path)

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.chdir(Scenario.root_path)


class TransformTools:
    """
    Provides helper functions that transform dataframes
    to add value. Can be accessed via tools.transform in graph() functions.
    """

    def __init__(self, graph_tools, time_zone="US/Pacific"):
        self.time_zone = time_zone
        self.tools = graph_tools

    def gen_type(
        self,
        df: pd.DataFrame,
        map_name="default",
        gen_tech_col="gen_tech",
        energy_source_col="gen_energy_source",
    ):
        """
        Returns a dataframe that contains a column 'gen_type'.

        By default 'gen_type' is the aggregation of 'gen_tech' + 'gen_energy_source'
        however this can be overidden in graph_tech_types.csv
        """
        # If there's no mapping, we simply make the mapping the sum of both columns
        # Read the tech_colors and tech_types csv files.
        try:
            tech_types = self.tools.get_dataframe(
                "graph_tech_types.csv", from_inputs=True
            )
        except FileNotFoundError:
            df = df.copy()
            df["gen_type"] = df[gen_tech_col] + "_" + df[energy_source_col]
            return df
        filtered_tech_types = tech_types[tech_types["map_name"] == map_name][
            ["gen_tech", "energy_source", "gen_type"]
        ]
        df = df.merge(
            filtered_tech_types,
            left_on=[gen_tech_col, energy_source_col],
            right_on=["gen_tech", "energy_source"],
            validate="many_to_one",
            how="left",
        )
        df["gen_type"] = df["gen_type"].fillna(
            "Other"
        )  # Fill with Other so the colors still work
        return df

    def build_year(self, df, build_year_col="build_year"):
        """
        Replaces all the build years that aren't a period with the value "Pre-existing".
        """
        # Get list of valid periods
        periods = self.tools.get_dataframe("periods", from_inputs=True)[
            "INVESTMENT_PERIOD"
        ].astype("str")
        df = df.copy()  # Make copy to not modify source
        df[build_year_col] = (
            df[build_year_col]
            .apply(lambda b: str(b) if str(b) in periods.values else "Pre-existing")
            .astype("category")
        )
        return df

    def timestamp(self, df, timestamp_col="timestamp"):
        """
        Adds the following columns to the dataframe:
        - time_row: by default the period but can be overridden by graph_timestamp_map.csv
        - time_column: by default the timeseries but can be overridden by graph_timestamp_map.csv
        - datetime: timestamp formatted as a US/Pacific Datetime object
        - hour: The hour of the timestamp (US/Pacific timezone)
        """
        timepoints = self.tools.get_dataframe("timepoints.csv", from_inputs=True)
        timeseries = self.tools.get_dataframe(csv="timeseries.csv", from_inputs=True)

        timepoints = timepoints.merge(
            timeseries,
            how="left",
            left_on="timeseries",
            right_on="TIMESERIES",
            validate="many_to_one",
        )
        timestamp_mapping = timepoints[["timestamp", "ts_period", "timeseries"]]
        timestamp_mapping = timestamp_mapping.rename({"ts_period": "period"}, axis=1)
        timestamp_mapping = timestamp_mapping.astype({"period": "category"})

        df = df.rename({timestamp_col: "timestamp"}, axis=1)
        df = df.merge(
            timestamp_mapping,
            how="left",
            on="timestamp",
        )

        try:
            df = df.merge(
                self.tools.get_dataframe("graph_timestamp_map.csv", from_inputs=True),
                how="left",
                on="timestamp",
            )
        except FileNotFoundError:
            timestamp_mapping["time_row"] = timestamp_mapping["period"]
            timestamp_mapping["time_column"] = timestamp_mapping["timeseries"]

        # Add datetime and hour column
        df["datetime"] = (
            pd.to_datetime(df["timestamp"], format="%Y%m%d%H")
            .dt.tz_localize("utc")
            .dt.tz_convert(self.time_zone)
        )
        df["hour"] = df["datetime"].dt.hour

        return df

    def load_zone(self, df, load_zone_col="load_zone"):
        """
        Adds a 'region' column that is usually load_zone's state.
        'region' is what comes before the first underscore. If no underscores are present
        defaults to just using the load_zone.
        """
        df = df.copy()  # Don't modify the source
        df["region"] = df[load_zone_col].apply(lambda z: z.partition("_")[0])
        return df


class GraphTools:
    """
    Object that is passed in graph().
    Provides utilities to make graphing easier and standardized.
    """

    ENABLE_DF_CACHING = True

    def __init__(self, scenarios: List[Scenario], graph_dir: str, skip_long: bool):
        """
        Create the GraphTools.

        @param scenarios list of scenarios that we should run graphing for
                graph_dir directory where graphs should be saved
        @param graph_dir folder where graphs should be outputed to
        """
        # Check that the scenario names are unique
        all_names = list(map(lambda s: s.name, scenarios))
        if len(all_names) > len(
            set(all_names)
        ):  # set() drops duplicates, so if not unique len() will be less
            raise Exception("Scenario names are not unique.")

        self._scenarios: List[Scenario] = scenarios
        self.graph_dir = graph_dir
        self.skip_long = skip_long

        # Here we store a mapping of csv file names to their dataframes.
        # Each dataframe has a column called 'scenario' that specifies which scenario
        # a given row belongs to.
        self._dfs: Dict[str, pd.DataFrame] = {}

        self.num_scenarios = len(scenarios)

        # When True we are running compare(), when False we are running graph()
        # compare() is to create graphs for multiple scenarios
        # graph() is to create a graph just for the data of the active scenario
        self._is_compare_mode = False

        # When in graph mode, we move between scenarios. This index specifies the current scenario
        self._active_scenario = None
        # Maps a file name to a tuple where the tuple holds (fig, axs), the matplotlib figure and axes
        self._module_figures: Dict[str, List[Tuple]] = {}

        # Provide link to useful libraries
        self.sns = sns
        self.pd = pd
        self.np = np
        self.mplt = matplotlib
        self.pn = plotnine

        # Set the style to Seaborn default style
        sns.set()

        # Disables pandas warnings that will occur since we are constantly returning only a slice of our master dataframe
        pd.options.mode.chained_assignment = None

        self.transform = TransformTools(self)

    def _load_dataframe(self, path, convert_dot_to_na):
        """
        Reads a csv file for every scenario and returns a single dataframe containing
        the rows from every scenario with a column for the scenario name and index.
        """
        df_all_scenarios: List[pd.DataFrame] = []
        for i, scenario in enumerate(self._scenarios):
            df = pd.read_csv(
                os.path.join(scenario.path, path),
                index_col=False,
                # We force the datatype to object for some columns to avoid warnings of mismatched types
                dtype={"generation_project": str, "gen_dbid": str},
                na_values="." if convert_dot_to_na else None,
            )
            df["scenario_name"] = scenario.name
            df["scenario_index"] = i
            df_all_scenarios.append(df)

        df_all_scenarios: pd.DataFrame = pd.concat(df_all_scenarios)
        return df_all_scenarios

    def _create_axes(self, out, size=(8, 5), **kwargs):
        """
        Create a set of matplotlib axes
        """
        num_subplot_columns = 1 if self._is_compare_mode else self.num_scenarios
        fig = GraphTools._create_figure(
            out, size=(size[0] * num_subplot_columns, size[1]), **kwargs
        )
        ax = fig.subplots(nrows=1, ncols=num_subplot_columns, sharey="row")

        # If num_subplot_columns is 1, ax is not a list but we want it to be a list
        # so we replace ax with [ax]
        if num_subplot_columns == 1:
            ax = [ax]

        # Set a title to each subplot
        if num_subplot_columns > 1:
            for i, a in enumerate(ax):
                a.set_title(f"Scenario: {self._scenarios[i].name}")

        return fig, ax

    @staticmethod
    def _create_figure(
        name, title=None, note=None, size=None, xlabel=None, ylabel=None, **kwargs
    ):
        fig = plt.figure(**kwargs)

        # Set a title for the figure
        if title is None:
            warnings.warn(
                f"No title set for graph {name}.csv. Specify 'title=' in get_new_axes() or get_new_figure()."
            )
        else:
            fig.suptitle(title)

        GraphTools._add_note(fig, note)

        # Set figure size based on numbers of subplots
        if size is not None:
            fig.set_size_inches(size[0], size[1])

        if xlabel is not None:
            fig.text(0.5, 0.01, xlabel, ha="center")
        if ylabel is not None:
            fig.text(0.01, 0.5, ylabel, va="center", rotation="vertical")

        return fig

    @staticmethod
    def _add_note(fig, note):
        if note is not None:
            fig.text(
                0.5, -0.1, note, wrap=True, horizontalalignment="center", fontsize=10
            )

    def get_axes(self, out, *args, **kwargs):
        """Returns a set of matplotlib axes that can be used to graph."""
        # If we're on the first scenario, we want to create the set of axes
        if self._is_compare_mode or self._active_scenario == 0:
            self._module_figures[out] = [self._create_axes(out, *args, **kwargs)]

        # Fetch the axes in the (fig, axs) tuple then select the axis for the active scenario
        return self._module_figures[out][0][1][
            0 if self._is_compare_mode else self._active_scenario
        ]

    def get_figure(self, out, *args, **kwargs):
        # Create the figure
        fig = GraphTools._create_figure(out, *args, **kwargs)
        # Save it to the outputs
        self.save_figure(out, fig)
        # Return the figure
        return fig

    def save_figure(self, out, fig):
        # If we have multiple scenarios, leave a note under each indicating the scenario
        if not self._is_compare_mode and self.num_scenarios > 1:
            self._add_note(
                fig, "Scenario: " + self._scenarios[self._active_scenario].name
            )
        if out not in self._module_figures:
            self._module_figures[out] = []
        # Add the figure to the list of figures for that scenario
        self._module_figures[out].append((fig, None))

    def get_dataframe(
        self,
        csv,
        folder=None,
        from_inputs=False,
        all_scenarios=False,
        convert_dot_to_na=False,
    ):
        """Returns the dataframe for the active scenario."""
        # Add file extension of missing
        if len(csv) < 5 or csv[-4:] != ".csv":
            csv += ".csv"
        # Select folder if not specified
        if folder is None:
            folder = "inputs" if from_inputs else "outputs"
        # Get dataframe path
        path = os.path.join(folder, csv)

        # If doesn't exist, create it
        if path not in self._dfs:
            df = self._load_dataframe(path, convert_dot_to_na=convert_dot_to_na)
            if GraphTools.ENABLE_DF_CACHING:
                self._dfs[path] = df
        else:
            df = self._dfs[path].copy()  # We return a copy so the source isn't modified

        # If they want all the scenarios verify that that is possible
        if all_scenarios:
            if not self._is_compare_mode:
                raise Exception("all_scenarios=True is only possible under compare().")
        # If they want only some scenarios return the rows corresponding to the active scenario (or scenario 0 if we're in compare mode)
        else:
            scenario = 0 if self._is_compare_mode else self._active_scenario
            df = df[df["scenario_index"] == scenario]
            df = df.drop(["scenario_index", "scenario_name"], axis=1)
        return df

    def graph_module(self, func_graph):
        """Runs the graphing function for each comparison run"""
        self._is_compare_mode = False
        # For each scenario
        for i, scenario in enumerate(self._scenarios):
            # Set the active scenario index so that other functions behave properly
            self._active_scenario = i
            # Call the graphing function
            try:
                func_graph(self)
            except Exception:
                print(
                    f"ERROR: Module threw an Exception while running graph(). "
                    f"Moving on to the next module.\n{traceback.format_exc()}"
                )
        self._active_scenario = None  # Reset to none to avoid accidentally selecting data when not graphing per scenario

        # Save the graphs
        self._save_plots()

    def compare_module(self, func_compare):
        self._is_compare_mode = True
        func_compare(self)
        self._save_plots()

    def _save_plots(self):
        for name, figures in self._module_figures.items():
            for i, (fig, _) in enumerate(figures):
                out = name
                # If we have multiple figures append an index to allow concat to work
                if len(figures) > 1:
                    out += "_" + str(i)
                fig.savefig(os.path.join(self.graph_dir, out), bbox_inches="tight")
            # If we have multiple figures, concat them into a single one
            if len(figures) > 1:
                GraphTools._concat_figures(
                    os.path.join(self.graph_dir, name), len(figures)
                )
        # Reset our module_figures dict
        self._module_figures = {}

    @staticmethod
    def _concat_figures(basepath, n):
        """
        This function merges n figures together side by side.
        The figures must have the same base path and only differ in their suffix
        (_0.png, _1.png, _2.png etc).
        """
        # Get the paths of each image
        image_paths = tuple(basepath + "_" + str(i) + ".png" for i in range(n))
        # Open each image
        images = tuple(Image.open(path) for path in image_paths)

        # Get the dimension of our final figure
        height = max(map(lambda x: x.size[1], images))
        width = sum(map(lambda x: x.size[0], images))

        # Create our final figure
        concated = Image.new("RGB", (width, height), "white")

        # For each image, paste it into
        x = 0
        for image in images:
            concated.paste(image, (x, 0))
            x += image.size[0]

        # Save the concated image
        concated.save(basepath + ".png", "PNG")

        # Delete the individual images
        for image_path in image_paths:
            os.remove(image_path)

    def get_colors(self, n=None, map_name="default"):
        """
        Returns an object that can be passed to color= when doing a bar plot.
        @param n should be specified when using a stacked bar chart as the number of bars
        @param map_name is the name of the technology mapping in use
        """
        try:
            tech_colors = self.get_dataframe(
                csv="graph_tech_colors.csv", from_inputs=True
            )
        except:
            return None
        filtered_tech_colors = tech_colors[tech_colors["map_name"] == map_name]
        if n is not None:
            return {
                r["gen_type"]: [r["color"]] * n
                for _, r in filtered_tech_colors.iterrows()
            }
        else:
            return {
                r["gen_type"]: r["color"] for _, r in filtered_tech_colors.iterrows()
            }

    def graph_time_matrix(self, df, value_column, out, title, ylabel):
        # Add the technology type column and filter out unneeded columns
        df = self.transform.gen_type(df)
        # Keep only important columns
        df = df[["gen_type", "timestamp", value_column]]
        # Sum the values for all technology types and timepoints
        df = df.groupby(["gen_type", "timestamp"], as_index=False).sum()
        # Add the columns time_row and time_column
        df = self.transform.timestamp(df)
        # Sum across all technologies that are in the same hour and quarter
        df = df.groupby(
            ["hour", "gen_type", "time_column", "time_row"], as_index=False
        ).mean()
        self.graph_matrix(
            df, value_column, out, title, ylabel, "time_row", "time_column"
        )

    def graph_scenario_matrix(self, df, value_column, out, title, ylabel):
        # Add the technology type column and filter out unneeded columns
        df = self.transform.gen_type(df)
        # Keep only important columns
        df = df[["gen_type", "timestamp", value_column, "scenario_name"]]
        # Sum the values for all technology types and timepoints
        df = df.groupby(
            ["gen_type", "timestamp", "scenario_name"], as_index=False
        ).sum()
        # Add the columns time_row and time_column
        df = self.transform.timestamp(df)
        # Sum across all technologies that are in the same hour and scenario
        df = df.groupby(["hour", "gen_type", "scenario_name"], as_index=False).mean()
        # Plot curtailment
        self.graph_matrix(
            df,
            value_column,
            out=out,
            title=title,
            ylabel=ylabel,
            col_specifier="scenario_name",
            row_specifier=None,
        )

    def graph_matrix(
        self, df, value_column, out, title, ylabel, row_specifier, col_specifier
    ):
        # Change None values to a column which is all the same
        df["empty_col"] = "-"
        if row_specifier is None:
            row_specifier = "empty_col"
        if col_specifier is None:
            col_specifier = "empty_col"
        # Get rows
        rows = df[row_specifier].drop_duplicates().sort_values()
        # Count number of rows and number of columns
        nrows = min(len(rows), 6)
        ncols = 0
        for row in rows:
            columns = df[df[row_specifier] == row][col_specifier].drop_duplicates()
            ncols = max(ncols, len(columns))
        ncols = min(ncols, 8)
        fig = self.get_figure(
            out=out,
            title=title,
            size=(10 * ncols / nrows, 8),
            ylabel=ylabel,
            xlabel="Time of day (PST)",
        )

        ax = fig.subplots(nrows, ncols, sharey="row", sharex=False, squeeze=False)

        # Sort the technologies by standard deviation to have the smoothest ones at the bottom of the stacked area plot
        df_all = df.pivot_table(
            index="hour", columns="gen_type", values=value_column, aggfunc=np.sum
        )
        ordered_columns = df_all.std().sort_values().index

        legend = {}

        # for each row...
        for ri in range(nrows):
            row = rows.iloc[ri]
            df_row = df[df[row_specifier] == row]
            columns = df_row[col_specifier].drop_duplicates().sort_values()
            for ci in range(min(ncols, len(columns))):
                column = columns.iloc[ci]
                current_ax = ax[ri][ci]
                # get the dispatch for that quarter
                sub_df = df_row.loc[df[col_specifier] == column]
                # Skip if no timepoints in quarter
                if len(sub_df) == 0:
                    continue
                # Make it into a proper dataframe
                sub_df = sub_df.pivot(
                    index="hour", columns="gen_type", values=value_column
                )
                sub_df = sub_df.reindex(columns=ordered_columns)
                # # Fill hours with no data with zero so x-axis doesn't skip hours
                # all_hours = tools.np.arange(0, 24, 1)
                # missing_hours = all_hours[~tools.np.isin(all_hours, sub_df.index)]
                # sub_df = sub_df.append(tools.pd.DataFrame(index=missing_hours)).sort_index().fillna(0)
                # Get axes

                # Rename to make legend proper
                sub_df = sub_df.rename_axis("Type", axis="columns")
                # Plot
                colors = self.get_colors()
                if colors is None:
                    sub_df.plot.area(
                        ax=current_ax,
                        stacked=True,
                        xlabel=column,
                        ylabel=row,
                        xticks=[],
                        legend=False,
                    )
                else:
                    sub_df.plot.area(
                        ax=current_ax,
                        stacked=True,
                        color=colors,
                        xlabel=column,
                        ylabel=row,
                        xticks=[],
                        legend=False,
                    )
                # Get all the legend labels and add them to legend dictionary.
                # Since it's a dictionary, duplicates are dropped
                handles, labels = current_ax.get_legend_handles_labels()
                for i in range(len(handles)):
                    legend[labels[i]] = handles[i]
        # Remove space between subplot columns
        fig.subplots_adjust(wspace=0)
        # Add the legend
        legend_pairs = legend.items()
        fig.legend([h for _, h in legend_pairs], [l for l, _ in legend_pairs])

    @staticmethod
    def sort_build_years(x):
        def val(v):
            r = v if v != "Pre-existing" else "000"
            return r

        xm = x.map(val)
        return xm


def graph_scenarios(
    scenarios: List[Scenario],
    graph_dir,
    skip_long=False,
    module_names=None,
    compare_only=False,
):
    # Start a timer
    timer = StepTimer()

    # If no module name specified we get them from modules.txt
    if module_names is None:
        module_names = read_modules(scenarios)

    if len(module_names) == 0:
        # We'd raise an exception however warnings are already generated by load_modules
        print("No modules found.")
        return

    # Import the modules
    for module_name in module_names:
        importlib.import_module(module_name)

    # Initialize the graphing tool
    graph_tools = GraphTools(
        scenarios=scenarios, graph_dir=graph_dir, skip_long=skip_long
    )

    # Loop through every graphing module
    print(f"Graphing modules:")
    if not compare_only:
        for name, func_graph in iterate_modules(module_names, "graph"):
            # Graph
            print(f"{name}.graph()...")
            graph_tools.graph_module(func_graph)

    for name, func_compare in iterate_modules(module_names, "compare"):
        print(f"{name}.compare()...")
        graph_tools.compare_module(func_compare)

    print(f"Took {timer.step_time_as_str()} to generate all graphs.")


def iterate_modules(module_names, func_name):
    """This function is an Iterable that returns only modules with function graph()"""
    for name in module_names:
        module = sys.modules[name]
        # If the module has graph(), yield the module
        if hasattr(module, func_name):
            yield name, getattr(module, func_name)


def read_modules(scenarios):
    """Reads all the modules found in modules.txt"""

    def read_modules_txt(scenario):
        """Returns a sorted list of all the modules in a run folder (by reading modules.txt)"""
        with scenario:
            module_list = get_module_list(include_solve_module=False)
        return np.sort(module_list)

    # Split compare_dirs into a base and a list of others
    scenario_base, other_scenarios = scenarios[0], scenarios[1:]
    module_names = read_modules_txt(scenario_base)

    # Check that all the compare_dirs have equivalent modules.txt
    for scenario in other_scenarios:
        if not np.array_equal(module_names, read_modules_txt(scenario)):
            warnings.warn(
                f"modules.txt is not equivalent between {scenario_base.name} and {scenario.name}. "
                f"We will use the modules.txt in {scenario_base.name} however this may result "
                f"in missing graphs and/or errors."
            )

    return module_names
