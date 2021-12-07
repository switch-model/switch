import os

from matplotlib import pyplot as plt

from switch_model.tools.graph.main import Scenario

rel_path_base = "../switch_runs/ldes_runs"


def get_scenario(rel_path, name=None):
    return Scenario(os.path.join(rel_path_base, rel_path), name=name)


def set_style():
    plt.interactive(True)
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["ytick.minor.visible"] = False
    plt.rcParams["xtick.minor.visible"] = False
