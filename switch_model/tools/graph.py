import importlib, sys
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd
import os

from switch_model.solve import get_module_list


class GraphingUtil:
    def __init__(self, compare=False, graph_dir="graphs"):
        sns.set()
        self.compare = compare
        self.dfs = {}
        self.graph_dir = graph_dir
        if not os.path.isdir(graph_dir):
            os.makedirs(graph_dir)

    def get_new_axes(self):
        plt.close()
        return plt.gcf().gca()

    def save_plot(self, name):
        plt.gcf().savefig(os.path.join(self.graph_dir, name))

    def read_csv(self, name):
        if name not in self.dfs:
            self.dfs[name] = pd.read_csv(name)

        return self.dfs[name]


def main():
    print(f"Loading modules...")
    modules = load_modules()
    grapher = GraphingUtil()

    for name, module in iterate_modules(modules):
        if not hasattr(module, 'graph'):
            continue

        print(f"Graphing module {name}...")
        module.graph(grapher)


def load_modules():
    modules = get_module_list()
    for module in modules:
        importlib.import_module(module)
    return modules


def iterate_modules(modules):
    for module in modules:
        yield module, sys.modules[module]
