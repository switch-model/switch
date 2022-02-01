import os

from matplotlib import pyplot as plt

from switch_model.tools.graph.main import Scenario

rel_path_base = "../switch_runs/ldes_runs"


def get_scenario(rel_path, name=None):
    return Scenario(os.path.join(rel_path_base, rel_path), name=name)


def set_style():
    plt.interactive(True)  # Allows the plots to continually update in PyCharm's SciView
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["ytick.minor.visible"] = False
    plt.rcParams["xtick.minor.visible"] = False

def get_set_e_scenarios():
    return [
        get_scenario("1342", name=1.94),
        get_scenario("M7", name=2),
        get_scenario("M10", name=2.5),
        get_scenario("M9", name=3),
        get_scenario("M6", name=4),
        get_scenario("M5", name=8),
        get_scenario("M11", name=12),
        get_scenario("M4", name=16),
        get_scenario("M14", name=18),
        get_scenario("M13", name=20),
        get_scenario("M8", name=24),
        get_scenario("M3", name=32),
        get_scenario("M12", name=48),
        get_scenario("M2", name=64),
    ]