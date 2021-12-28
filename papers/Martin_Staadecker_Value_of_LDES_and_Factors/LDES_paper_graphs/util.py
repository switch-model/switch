import os

from matplotlib import pyplot as plt

from switch_model.tools.graph.main import Scenario

rel_path_base = "../switch_runs/ldes_runs"


def get_scenario(rel_path, name=None):
    return Scenario(os.path.join(rel_path_base, rel_path), name=name)


def set_style():
    plt.interactive(True)  # Allows the plots to continually update in SciView
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["ytick.minor.visible"] = False
    plt.rcParams["xtick.minor.visible"] = False

def create_bin_labels(bins):
    """Returns an array of labels representing te bins."""
    i = 1
    labels = []
    while i < len(bins):
        low = bins[i-1]
        high = bins[i]
        if low == float("-inf"):
            labels.append(f"<{high}")
        elif high == float("inf"):
            labels.append(f"{low}+")
        else:
            labels.append(f"{low}-{high}")
        i += 1
    return labels