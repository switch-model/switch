import importlib, sys, argparse, os
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from switch_model.solve import get_module_list


class GraphingUtil:
    def __init__(self, run_dirs, graph_dir="graphs"):
        self.run_dirs = run_dirs
        self.data = [{} for run_dir in run_dirs]
        self.graph_dir = graph_dir
        self.current_run = 0
        self.active_figures = {}
        if not os.path.isdir(graph_dir):
            os.makedirs(graph_dir)

        self.set_style()

    def set_style(self):
        sns.set()

    def save_and_reset(self):
        for name, (fig, ax) in self.active_figures.items():
            fig.savefig(os.path.join(self.graph_dir, name))
        self.current_run = 0
        self.active_figures = {}

    def get_new_axes(self, name):
        if self.current_run == 0:
            self.active_figures[name] = plt.subplots(nrows=1, ncols=len(self.run_dirs))
        return self.active_figures[name][1][self.current_run]

    def read_csv(self, name):
        run_data = self.data[self.current_run]
        if name not in run_data:
            run_data[name] = pd.read_csv(name)

        return run_data[name]

    def next_run(self):
        self.current_run += 1


def main():
    root_work_dir = os.getcwd()
    args = parse_args()
    run_dirs = args.compare

    print(f"Loading modules...")
    modules = load_modules(run_dirs)
    grapher = GraphingUtil(run_dirs=run_dirs)

    for name in modules:
        module = sys.modules[name]
        if not hasattr(module, "graph"):
            continue

        print(f"Graphing module {name}...")
        for run_dir in run_dirs:
            os.chdir(run_dir)
            module.graph(grapher)
            os.chdir(root_work_dir)
            grapher.next_run()
        grapher.save_and_reset()


def load_modules(run_dirs):
    breakpoint()
    base_run_dir = run_dirs[0]
    base_modules = read_modules_txt(base_run_dir)

    for run_dir in run_dirs[1:]:
        if not check_modules_equal(base_run_dir, read_modules_txt(run_dir)):
            print(
                f"WARNING: modules.txt is not equivalent between {base_run_dir} and {run_dir}."
                f"We will use the modules.txt in {base_run_dir} however this may throw errors."
            )

    for module in base_modules:
        importlib.import_module(module)

    return base_modules


def read_modules_txt(run_dir):
    root_dir = os.getcwd()
    os.chdir(run_dir)
    module_list = get_module_list()
    os.chdir(root_dir)
    return module_list


def check_modules_equal(modules_a, modules_b):
    if len(modules_a) != len(modules_b):
        return False
    modules_a = np.array(sorted(modules_a))
    modules_b = np.array(sorted(modules_b))
    return all(modules_a == modules_b)


def iterate_modules(modules):
    for module in modules:
        yield module, sys.modules[module]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Graph the outputs and inputs of SWITCH"
    )
    parser.add_argument(
        "--compare", nargs="+", default=["."], help="Specify a list of runs to compare"
    )

    return parser.parse_args()
