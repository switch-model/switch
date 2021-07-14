"""
Tool to generate graphs that compare multiple scenario outputs.
Run 'switch compare -h' for details.
"""

import argparse, os
from switch_model.tools.graph.main import Scenario
from switch_model.tools.graph.cli import add_arguments, graph_scenarios_from_cli


def main():
    # Create the command line interface
    parser = argparse.ArgumentParser(
        description="Create graphs that compare multiple scenario outputs.",
        epilog="Example:\n\nswitch compare low-vs-high-demand .\low-demand .\high-demand --names 'Low Demand' 'High Demand'"
        "\n\nThis command will generate comparison graphs in a folder called 'low-vs-high-demand'. The graphs will be "
        " based on the scenarios in folders ./low-demand and ./high-demand. The graphs will use 'Low Demand' and 'High Demand'"
        "in the legends and where applicable.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "scenarios", nargs="+", help="Specify a list of runs to compare"
    )
    parser.add_argument(
        "--names", nargs="+", default=None, help="Names of the scenarios"
    )
    add_arguments(parser)
    # Parse the parameters
    args = parser.parse_args()

    # Verify we're comparing at least 2 scenarios
    if len(args.scenarios) < 2:
        raise Exception("Didn't pass in enough scenarios to compare")

    # If names is not set, make the names the scenario path
    if args.names is None:
        args.names = list(map(lambda p: os.path.normpath(p), args.scenarios))
        print(
            "NOTE: For better graphs, use the flag '--names' to specify descriptive scenario names (e.g. baseline)"
        )
    else:
        # If names was provided, verify the length matches the number of scenarios
        if len(args.names) != len(args.scenarios):
            raise Exception(
                f"Gave {len(args.names)} scenario names but there were {len(args.scenarios)} scenarios."
            )

    # If graph_dir is not set, make it 'compare_<name_1>_to_<name2>_to_<name3>...'
    if args.graph_dir is None:
        args.graph_dir = f"compare_{'_to_'.join(args.names)}"

    # Create a list of Scenario objects for each scenario
    scenarios = [
        Scenario(rel_path, args.names[i]) for i, rel_path in enumerate(args.scenarios)
    ]

    # Create the graphs!
    graph_scenarios_from_cli(scenarios, args)
