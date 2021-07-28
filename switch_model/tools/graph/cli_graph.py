"""
Tool to generate graphs for a scenario.

Run "switch graph -h" for details.
"""

import argparse

from switch_model.tools.graph.main import Scenario
from switch_model.tools.graph.cli import add_arguments, graph_scenarios_from_cli


def main(args=None):
    # Create the command line interface
    parser = argparse.ArgumentParser(
        description="Create graphs for a single set of SWITCH results."
    )
    add_arguments(parser)
    args = parser.parse_args(args)

    if args.graph_dir is None:
        args.graph_dir = "graphs"

    # Create the graphs (with a single scenario)
    graph_scenarios_from_cli(scenarios=[Scenario(rel_path=".", name="")], args=args)
