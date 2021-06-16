# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""Script to handle switch <cmd> calls from the command line."""
from __future__ import print_function

import argparse
import sys
import switch_model
import switch_model.solve as solve
import switch_model.solve_scenarios as solve_scenarios
import switch_model.test as test
import switch_model.upgrade as upgrade
import switch_model.wecc.get_inputs as get_inputs
import switch_model.tools.drop as drop
import switch_model.tools.graphing.graph as graph
import switch_model.tools.graphing.compare as compare
import switch_model.wecc.__main__ as db
import switch_model.tools.new as new


def version():
    print("Switch model version " + switch_model.__version__)
    try:
        from switch_model.utilities import get_git_branch

        print(f"Switch git branch {get_git_branch()}")
    except:
        pass
    return 0


cmds = {
    "solve": solve.main,
    "solve-scenarios": solve_scenarios.main,
    "test": test.main,
    "upgrade": upgrade.main,
    "get_inputs": get_inputs.main,
    "--version": version,
    "drop": drop.main,
    "new": new.main,
    "graph": graph.main,
    "compare": compare.main,
    "db": db.main,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "subcommand", choices=cmds.keys(), help="The possible switch subcommands"
    )

    # If users run a script from the command line, the location of the script
    # gets added to the start of sys.path; if they call a module from the
    # command line then an empty entry gets added to the start of the path,
    # indicating the current working directory. This module is often called
    # from a command-line script, but we want the current working
    # directory in the path because users may try to load local modules via
    # the configuration files, so we make sure that's always in the path.
    sys.path[0] = ""

    args, remaining_args = parser.parse_known_args()

    # adjust the argument list to make it look like someone ran "python -m <module>" directly
    sys.argv[0] += " " + sys.argv[1]
    del sys.argv[1]

    cmds[args.subcommand]()


if __name__ == "__main__":
    main()
