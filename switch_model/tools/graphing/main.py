import importlib, traceback
import os
import sys
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
import seaborn as sns
import matplotlib

from switch_model.utilities import StepTimer, get_module_list

original_working_dir = os.getcwd()


class GraphDataFolder:
    OUTPUTS = "outputs"
    INPUTS = "inputs"


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
        self.path = os.path.join(Scenario.root_path, rel_path)
        self.name = name

        if not os.path.isdir(self.path):
            raise Exception(f"Directory does not exist: {self.path}")

    def __enter__(self):
        os.chdir(self.path)

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.chdir(Scenario.root_path)


class GraphData:
    """
    Object that stores and handles loading csv into dataframes data for different scenarios.
    """

    def __init__(self, scenarios: List[Scenario]):
        self.scenarios: List[Scenario] = scenarios

        # Here we store a mapping of csv file names to their dataframes.
        # Each dataframe has a column called 'scenario' that specifies which scenario
        # a given row belongs to
        self.dfs: Dict[str, pd.DataFrame] = {}

        # Check that the scenario names are unique
        all_names = list(map(lambda s: s.name, scenarios))
        if len(all_names) > len(
            set(all_names)
        ):  # set() drops duplicates, so if not unique len() will be less
            raise Exception("Scenario names are not unique.")

        # Disables warnings that will occur since we are constantly returning only a slice of our master dataframe
        pd.options.mode.chained_assignment = None

    def _load_dataframe(self, csv, folder):
        """Loads the dataframe into self.dfs[csv]"""
        df_all_scenarios: List[pd.DataFrame] = []
        for i, scenario in enumerate(self.scenarios):
            df = pd.read_csv(os.path.join(scenario.path, folder, csv + ".csv"))
            df["scenario_name"] = scenario.name
            df["scenario_index"] = i
            df_all_scenarios.append(df)

        self.dfs[csv] = pd.concat(df_all_scenarios)

    def get_dataframe(self, scenario_index, csv, folder=GraphDataFolder.OUTPUTS):
        """Return a dataframe filtered by the scenario_name"""
        if csv not in self.dfs:
            self._load_dataframe(csv, folder)

        df = self.dfs[csv]
        return df[df["scenario_index"] == scenario_index]

    def get_dataframe_all_scenarios(self, csv, folder=GraphDataFolder.OUTPUTS):
        """Fetch the dataframe containing all the scenarios"""
        if csv not in self.dfs:
            self._load_dataframe(csv, folder)

        return self.dfs[csv].copy()  # We return a copy so the source isn't modified


class GraphTools:
    """
    Object that is passed in graph().
    Provides utilities to make graphing easier and standardized.
    """

    def __init__(self, scenarios, graph_dir):
        """
        Create the GraphTools.

        @param scenarios list of scenarios that we should run graphing for
                graph_dir directory where graphs should be saved
        """
        self.scenarios: List[Scenario] = scenarios
        self.graph_dir = graph_dir

        # Number of graphs to display side by side
        self.num_scenarios = len(scenarios)
        # Create an instance of GraphData which stores the csv dataframes
        self.graph_data = GraphData(self.scenarios)
        # When True we are running compare(), when False we are running graph()
        # compare() is to create graphs for multiple scenarios
        # graph() is to create a graph just for the data of the active scenario
        self.is_compare_mode = False
        # When in graph mode, we move between scenarios. This index specifies the current scenario
        self.active_scenario = None
        # Maps a file name to a tuple where the tuple holds (fig, axs), the matplotlib figure and axes
        self.module_figures: Dict[str, Tuple] = {}

        # Provide link to useful libraries
        self.sns = sns
        self.pd = pd
        self.np = np
        self.mplt = matplotlib
        self.folders = GraphDataFolder

        # Set the style to Seaborn default style
        sns.set()

        # Read the tech_colors and tech_types csv files.
        folder = os.path.dirname(__file__)
        self._tech_types = pd.read_csv(os.path.join(folder, "tech_types.csv"))
        self._tech_colors = pd.read_csv(os.path.join(folder, "tech_colors.csv"))

    def _create_axes(self, out, title=None, size=(8, 5), note=None):
        """Create a set of axes"""
        num_subplot_columns = 1 if self.is_compare_mode else self.num_scenarios
        fig, ax = plt.subplots(nrows=1, ncols=num_subplot_columns, sharey="row")

        # If num_subplot_columns is 1, ax is not a list but we want it to be a list
        # so we replace ax with [ax]
        if num_subplot_columns == 1:
            ax = [ax]

        # Set a title to each subplot
        if num_subplot_columns > 1:
            for i, a in enumerate(ax):
                a.set_title(f"Scenario: {self.scenarios[i].name}")

        # Set a title for the figure
        if title is None:
            print(
                f"Warning: no title set for graph {out}.csv. Specify 'title=' in get_new_axes()"
            )
        else:
            fig.suptitle(title)

        if note is not None:
            fig.text(
                0.5, -0.1, note, wrap=True, horizontalalignment="center", fontsize=10
            )

        # Set figure size based on numbers of subplots
        fig.set_size_inches(size[0] * num_subplot_columns, size[1])

        # Save the axes to module_figures
        self.module_figures[out] = (fig, ax)

    def get_new_axes(self, out, *args, **kwargs):
        """Returns a set of matplotlib axes that can be used to graph."""
        # If we're on the first scenario, we want to create the set of axes
        if self.is_compare_mode or self.active_scenario == 0:
            self._create_axes(out, *args, **kwargs)

        # Fetch the axes in the (fig, axs) tuple then select the axis for the active scenario
        return self.module_figures[out][1][
            0 if self.is_compare_mode else self.active_scenario
        ]

    def get_dataframe(self, *args, **kwargs):
        """Returns the dataframe for the active scenario"""
        if self.is_compare_mode:
            return self.graph_data.get_dataframe_all_scenarios(*args, **kwargs)
        else:
            return self.graph_data.get_dataframe(self.active_scenario, *args, **kwargs)

    def graph_module(self, func_graph):
        """Runs the graphing function for each comparison run"""
        self.is_compare_mode = False
        # For each scenario
        for i, scenario in enumerate(self.scenarios):
            # Set the active scenario index so that other functions behave properly
            self.active_scenario = i
            # Call the graphing function
            try:
                func_graph(self)
            except Exception:
                print(
                    f"ERROR: Module threw an Exception while running graph(). "
                    f"Moving on to the next module.\n{traceback.format_exc()}"
                )
        self.active_scenario = None  # Reset to none to avoid accidentally selecting data when not graphing per scenario

        # Save the graphs
        self._save_plots()

    def compare_module(self, func_compare):
        self.is_compare_mode = True
        func_compare(self)
        self._save_plots()

    def _save_plots(self):
        for name, (fig, axs) in self.module_figures.items():
            fig.savefig(os.path.join(self.graph_dir, name), bbox_inches="tight")
        # Reset our module_figures dict
        self.module_figures = {}

    def get_active_scenario_path(self):
        return self.scenarios[self.active_scenario].path

    def add_gen_type_column(
        self,
        df: pd.DataFrame,
        map_name="default",
        gen_tech_col="gen_tech",
        energy_source_col="gen_energy_source",
    ):
        """
        Returns a dataframe that contains a column called gen_type which
        is essentially a group of the gen_tech and gen_energy_source columns.
        """
        filtered_tech_types = self._tech_types[
            self._tech_types["map_name"] == map_name
        ][["gen_tech", "energy_source", "gen_type"]]
        return df.merge(
            filtered_tech_types,
            left_on=[gen_tech_col, energy_source_col],
            right_on=["gen_tech", "energy_source"],
            validate="many_to_one",
        )

    def get_colors(self, n=None, map_name="default"):
        """
        Returns an object that can be passed to color= when doing a bar plot.
        @param n should be specified when using a stacked bar chart as the number of bars
        @param map_name is the name of the technology mapping in use
        """
        filtered_tech_colors = self._tech_colors[
            self._tech_colors["map_name"] == map_name
        ]
        if n is not None:
            return {
                r["gen_type"]: [r["color"]] * n
                for _, r in filtered_tech_colors.iterrows()
            }
        else:
            return {
                r["gen_type"]: r["color"] for _, r in filtered_tech_colors.iterrows()
            }


def graph_scenarios(scenarios: List[Scenario], graph_dir):
    # Start a timer
    timer = StepTimer()

    # Load the SWITCH modules
    module_names = load_modules(scenarios)
    if len(module_names) == 0:
        # We'd raise an exception however warnings are already generated by load_modules
        print("No modules found.")
        return

    # Initialize the graphing tool
    graph_tools = GraphTools(scenarios=scenarios, graph_dir=graph_dir)

    # Loop through every graphing module
    print(f"Graphing modules:")
    for name, func_graph in iterate_modules(module_names, "graph"):
        # Graph
        print(f"{name}.graph()...")
        graph_tools.graph_module(func_graph)

    if len(scenarios) > 1:
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


def load_modules(scenarios):
    """Loads all the modules found in modules.txt"""

    def read_modules_txt(scenario_dir):
        """Returns a sorted list of all the modules in a run folder (by reading modules.txt)"""
        with scenario_dir:
            module_list = get_module_list(include_solve_module=False)
        return np.sort(module_list)

    print(f"Loading modules...")
    # Split compare_dirs into a base and a list of others
    scenario_base, other_scenarios = scenarios[0], scenarios[1:]
    module_names = read_modules_txt(scenario_base)

    # Check that all the compare_dirs have equivalent modules.txt
    for scenario in other_scenarios:
        if not np.array_equal(module_names, read_modules_txt(scenario)):
            print(
                f"WARNING: modules.txt is not equivalent between {scenario_base.name} and {scenario.name}. "
                f"We will use the modules.txt in {scenario_base.name} however this may result in missing graphs and/or errors."
            )

    # Import the modules
    for module_name in module_names:
        importlib.import_module(module_name)

    return module_names
