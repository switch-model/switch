# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""Script to handle switch <cmd> calls from the command line."""
from __future__ import print_function

import argparse
import importlib
import sys
import switch_model


def version():
    print("Switch model version " + switch_model.__version__)
    try:
        from switch_model.utilities import get_git_branch
        print(f"Switch git branch {get_git_branch()}")
    except:
        pass
    return 0

def get_module_runner(module):
    def runner():
        importlib.import_module(module).main()
    return runner


cmds = {
    "solve": get_module_runner("switch_model.solve"),
    "solve-scenarios": get_module_runner("switch_model.solve_scenarios"),
    "test": get_module_runner("switch_model.test"),
    "upgrade": get_module_runner("switch_model.upgrade"),
    "get_inputs": get_module_runner("switch_model.wecc.get_inputs"),
    "--version": get_module_runner("version"),
    "drop": get_module_runner("switch_model.tools.drop"),
    "new": get_module_runner("switch_model.tools.new"),
    "graph": get_module_runner("switch_model.tools.graphing.graph"),
    "compare": get_module_runner("switch_model.tools.graphing.compare"),
    "db": get_module_runner("switch_model.wecc.__main__"),
}


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("subcommand", choices=cmds.keys(), help="The possible switch subcommands")

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
