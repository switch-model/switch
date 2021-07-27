# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""Script to handle switch <cmd> calls from the command line."""
from __future__ import print_function

import sys, os
import switch_model


def main():
    # TODO make a proper command line tool with help information for each option
    cmds = [
        "solve",
        "solve-scenarios",
        "test",
        "upgrade",
        "get_inputs",
        "--version",
        "drop",
        "new",
        "graph",
        "compare",
        "sampling",
    ]
    if len(sys.argv) >= 2 and sys.argv[1] in cmds:
        # If users run a script from the command line, the location of the script
        # gets added to the start of sys.path; if they call a module from the
        # command line then an empty entry gets added to the start of the path,
        # indicating the current working directory. This module is often called
        # from a command-line script, but we want the current working
        # directory in the path because users may try to load local modules via
        # the configuration files, so we make sure that's always in the path.
        sys.path[0] = ""

        # adjust the argument list to make it look like someone ran "python -m <module>" directly
        cmd = sys.argv[1]
        sys.argv[0] += " " + cmd
        del sys.argv[1]
        if cmd == "--version":
            print("Switch model version " + switch_model.__version__)
            from switch_model.utilities import get_git_branch
            branch = get_git_branch()
            if branch is not None:
                print(f"Switch Git branch: {branch}")
            return 0
        if cmd == "solve":
            from switch_model.solve import main
        elif cmd == "solve-scenarios":
            from switch_model.solve_scenarios import main
        elif cmd == "test":
            from switch_model.test import main
        elif cmd == "upgrade":
            from switch_model.upgrade import main
        elif cmd == "get_inputs":
            from switch_model.wecc.get_inputs import main
        elif cmd == "sampling":
            from switch_model.wecc.sampling import main
        elif cmd == "drop":
            from switch_model.tools.drop import main
        elif cmd == "new":
            from switch_model.tools.new import main
        elif cmd == "graph":
            from switch_model.tools.graph.cli_graph import main
        elif cmd == "compare":
            from switch_model.tools.graph.cli_compare import main
        main()
    else:
        print(
            "Usage: {} {{{}}} ...".format(
                os.path.basename(sys.argv[0]), ", ".join(cmds)
            )
        )
        print("Use one of these commands with --help for more information.")


if __name__ == "__main__":
    main()
