# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""Script to handle switch <cmd> calls from the command line."""
from __future__ import print_function

import argparse
import importlib
import sys
import switch_model
from switch_model.utilities import get_git_branch

def print_version():
    print("Switch model version " + switch_model.__version__)
    branch = get_git_branch()
    if branch is not None:
        print(f"Switch Git branch: {branch}")

def help_text():
    print(
        f"Must specify one of the following commands: {list(cmds.keys()) + ['--version']}.\nE.g. Run 'switch solve' or 'switch get_inputs'.")


def get_module_runner(module):
    def runner():
        importlib.import_module(module).main()
    return runner


cmds = {
    "solve": get_module_runner("switch_model.solve"),
    "solve-scenarios": get_module_runner("switch_model.solve_scenarios"),
    "test": get_module_runner("switch_model.test"),
    "upgrade": get_module_runner("switch_model.upgrade"),
    "get_inputs": get_module_runner("switch_model.wecc.get_inputs.cli"),
    "drop": get_module_runner("switch_model.tools.drop"),
    "new": get_module_runner("switch_model.tools.new"),
    "graph": get_module_runner("switch_model.tools.graph.cli_graph"),
    "compare": get_module_runner("switch_model.tools.graph.cli_compare"),
    "db": get_module_runner("switch_model.wecc.__main__"),
    "help": help_text
}


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--version", default=False, action="store_true", help="Get version info")
    parser.add_argument("subcommand", choices=cmds.keys(), help="The possible switch subcommands", nargs="?",
                        default="help")

    # If users run a script from the command line, the location of the script
    # gets added to the start of sys.path; if they call a module from the
    # command line then an empty entry gets added to the start of the path,
    # indicating the current working directory. This module is often called
    # from a command-line script, but we want the current working
    # directory in the path because users may try to load local modules via
    # the configuration files, so we make sure that's always in the path.
    sys.path[0] = ""

    args, remaining_args = parser.parse_known_args()

    if args.version:
        print_version()
        return 0

    # adjust the argument list to make it look like someone ran "python -m <module>" directly
    if len(sys.argv) > 1:
        sys.argv[0] += " " + sys.argv[1]
        del sys.argv[1]
    cmds[args.subcommand]()


if __name__ == "__main__":
    main()
