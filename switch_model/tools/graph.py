import importlib, sys, argparse, os, shutil, enum
from typing import List, Dict
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

import switch_model.solve
from switch_model.utilities import query_yes_no, StepTimer

root_working_dir = os.getcwd()


class GraphDataFolder(enum.Enum):
    OUTPUTS = 0
    INPUTS = 1


class GraphData:
    """Object that stores pandas DataFrames to avoid reloading data that was already loaded."""

    def __init__(self):
        self.dfs = {}
        self.dir_mapping = {GraphDataFolder.OUTPUTS: "outputs", GraphDataFolder.INPUTS: "inputs"}

    def get_dataframe(self, csv, folder=GraphDataFolder.OUTPUTS):
        if csv not in self.dfs:
            self.dfs[csv] = pd.read_csv(os.path.join(self.dir_mapping[folder], csv + ".csv"))

        return self.dfs[csv]


class GraphTools:
    """Object that is passed in graph( ). Provides utilities to make graphing easier"""

    def __init__(self, compare_dirs, graph_dir):
        """
        Create the GraphTools.

        @param compare_dirs list of directories that we should run graphing for
                graph_dir directory where graphs should be saved
        """
        self.compare_dirs: List[CompareDir]  = compare_dirs
        self.graph_dir = graph_dir

        # Number of graphs to display side by side
        self.num_compares = len(compare_dirs)
        # Data for each compare directory
        self.loaded_data = [GraphData() for _ in range(self.num_compares)]
        self.active_compare_dir = 0
        self.module_figures = {}

        # Provide link to useful libraries
        self.sns = sns
        self.pd = pd
        self.np = np

        self.set_style()

    def set_style(self):
        sns.set()

    def get_new_axes(self, out):
        """Returns a set of matplotlib axes that can be used to graph."""
        # If we're on the first compare_dir, we want to create the set of axes
        if self.active_compare_dir == 0:
            fig, ax = plt.subplots(nrows=1, ncols=self.num_compares)
            # If num_compares is 1, ax is not a list but we want it to be a list
            if self.num_compares == 1:
                ax = [ax]

            # Set a title to each subplot
            for i, a in enumerate(ax):
                a.set_title(self.compare_dirs[i].rel_path)

            # Save the axes to module_figures
            self.module_figures[out] = (fig, ax)
        return self.module_figures[out][1][self.active_compare_dir]

    def get_dataframe(self, *args, **kwargs):
        return self.loaded_data[self.active_compare_dir].get_dataframe(*args, **kwargs)

    def graph_module(self, func_graph):
        """Runs the graphing function for each comparison run"""
        # For each comparison run
        for i, compare_dir in enumerate(self.compare_dirs):
            # Set the active compare dir so that other functions behave properly
            self.active_compare_dir = i

            # Change to the directory of that compare run to ensure we load data from the proper spot
            with compare_dir:
                func_graph(self)

        for name, (fig, ax) in self.module_figures.items():
            fig.savefig(os.path.join(self.graph_dir, name))
        self.module_figures = {}

class CompareDir:
    root_path = os.getcwd()

    def __init__(self, rel_path):
        self.path = os.path.join(CompareDir.root_path, rel_path)
        self.rel_path = rel_path

        if not os.path.isdir(self.path):
            raise Exception(f"Directory does not exist: {self.path}")

    def __enter__(self):
        os.chdir(self.path)

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.chdir(CompareDir.root_path)

def main():
    # Start a timer
    timer = StepTimer()

    # Read the cli arguments
    args = parse_args()

    # Get the folder where we should save the graphs
    graph_dir = get_graphing_folder(args)

    # Load the SWITCH modules
    module_names = load_modules(args.compare)

    # Initialize the graphing tool
    graph_tools = GraphTools(compare_dirs=args.compare, graph_dir=graph_dir)

    # Loop through every graphing module
    print(f"Graphing modules:")
    for name, func_graph in iterate_graphing_modules(module_names):
        # Graph
        print(f"{name}...")
        graph_tools.graph_module(func_graph)

    print(f"Took {timer.step_time_as_str()} to generate all graphs.")


def iterate_graphing_modules(module_names):
    """This function is an Iterable that returns only modules with function graph()"""
    for name in module_names:
        module = sys.modules[name]
        # If the module has graph(), yield the module
        if hasattr(module, "graph"):
            yield name, module.graph


def load_modules(compare_dirs):
    """Loads all the modules found in modules.txt"""

    def read_modules_txt(compare_dir):
        """Returns a sorted list of all the modules in a run folder (by reading modules.txt)"""
        with compare_dir:
            module_list = switch_model.solve.get_module_list()
        return np.sort(module_list)

    print(f"Loading modules...")
    # Split compare_dirs into a base and a list of others
    compare_dir_base, compare_dir_others = compare_dirs[0], compare_dirs[1:]
    module_names = read_modules_txt(compare_dir_base)

    # Check that all the compare_dirs have equivalent modules.txt
    for compare_dir_other in compare_dir_others:
        if not np.array_equal(module_names, read_modules_txt(compare_dir_other)):
            print(f"WARNING: modules.txt is not equivalent between {compare_dir_base} and {compare_dir_other}."
                  f"We will use the modules.txt in {compare_dir_base} however this may result in missing graphs and/or errors.")

    # Import the modules
    for module_name in module_names:
        importlib.import_module(module_name)

    return module_names


def parse_args():
    parser = argparse.ArgumentParser(description="Graph the outputs and inputs of SWITCH")
    parser.add_argument("--compare", nargs="+", default=["."],
                        help="Specify a list of runs to compare")
    parser.add_argument("--graphs-dir", default="graphs", type=str,
                        help="Name of the folder where the graphs should be saved")

    args = parser.parse_args()
    args.compare = list(map(CompareDir, args.compare))
    return args


def get_graphing_folder(args):
    graphs_dir = args.graphs_dir

    # If we are comparing, then we want to force the user to pick a more descriptive name than "graphs
    if len(args.compare) > 1 and graphs_dir == "graphs":
        raise Exception(
            "Please specify a descriptive folder name for where the graphs should be saved using --graphs-dir.")

    # Remove the directory if it already exists
    if os.path.exists(graphs_dir):
        if not query_yes_no(f"Folder '{graphs_dir}' already exists. Are you sure you want to delete all its contents?"):
            raise Exception("User aborted operation.")
        shutil.rmtree(graphs_dir)

    # Then recreate it so that its empty to the reader.
    os.makedirs(graphs_dir)

    return graphs_dir
