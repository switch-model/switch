import os
import seaborn as sns
from matplotlib import pyplot as plt

from switch_model.tools.graph.main import Scenario

rel_path_base = "../switch_runs/ldes_runs"
output_path_base = "../ldes_paper_plots"

def save_figure(filename):
    plt.savefig(os.path.join(output_path_base, filename))

def get_scenario(rel_path, name=None):
    return Scenario(os.path.join(rel_path_base, rel_path), name=name)


def set_style(interactive=True):
    plt.interactive(interactive)  # Allows the plots to continually update in PyCharm's SciView
    sns.set_theme(font_scale=0.6)  # Scale the font down to around 7pt to match guidelines
    plt.rcParams.update({
        "font.sans-serif": "Arial",
        "patch.edgecolor": "none",
        "figure.dpi": 100,
        "savefig.dpi": 1000,
        "figure.figsize": (6.850394, 6.850394 / 2),
        # Width according to Joule guidelines https://www.cell.com/figureguidelines
        "lines.linewidth": 1,
        "xtick.minor.visible": False,
        "ytick.minor.visible": False,
        "xtick.major.width": 0.8,
        "xtick.major.size": 3,
        "ytick.major.width": 0.8,
        "ytick.major.size": 3,
        "xtick.minor.width": 0.8,
        "xtick.minor.size": 2,
        "ytick.minor.width": 0.8,
        "ytick.minor.size": 2,
        "legend.labelspacing": 0.25,
        "legend.columnspacing": 1
    })


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
