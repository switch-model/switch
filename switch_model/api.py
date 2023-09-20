"""
Provide an API for getting information about models. Mainly used by Switch
Electron/Theia/VSCode app.

Info can be retrieved by running `switch <cmd> <args> --json` from
Switch.app. This will launch the bundled switch.py script, which will write the
required info to stdout. But if needed we could create an RPC interface for
switch.py to avoid reloading Python each time. Commands and arguments are shown
below.

`validate arguments` (maybe): check whether there are any arguments in
options.txt that aren't defined in any active module

`validate modules` (maybe): confirm all are available or identify unsound ones. also
minimally reorder modules based on their declared dependencies, to ensure they
will run successfully. Add missing modules based on declared mandatory
dependencies. Identify conflicting modules based on declared conflicts.

`validate inputs` (maybe): check for inconsistencies in data files based on
rules derived from code possibly via documentation framework. check for missing
data needed by current modules. report cases where extra data will be ignored.
report missing optional columns.
"""

import importlib, os, pprint, json

import switch_model
from .utilities import unwrap, _ArgumentParser  # includes some extra actions for Switch

argparser = _ArgumentParser()


def info():
    """
    `info --module-arguments <name>`:
    """

    # parse arguments
    argparser.add_argument(
        "--json",
        default=False,
        action="store_true",
        help="Report results as json text instead of prettified Python objects.",
    )
    argparser.add_argument(
        "--module-list",
        default=False,
        action="store_true",
        help=(
            "report all Switch modules (.py files with define_components "
            "functions inside) found in the Switch search path (given by "
            "`--module-search-path`)"
        ),
    )
    argparser.add_argument(
        "--module-arguments",
        default=None,
        dest="module",
        help=(
            "report all arguments defined by the specified module, including "
            "info about data type, single vs multiple, help text, etc."
        ),
    )
    options = argparser.parse_args()

    output = []
    # run steps
    if options.module_list:
        output.append(module_list())

    if options.module is not None:
        output.append(module_arguments(options.module))

    if len(output) == 1:
        output = output[0]

    # report results in json or plain text
    # print("info requested:")
    if options.json:
        print(json.dumps(output, indent=2))
    else:
        pprint.pprint(output)


def module_list():
    # TODO: return these in order by dependency (using dependencies var if provided)

    import sys, pkgutil

    switch_callbacks = [
        "define_arguments",
        "define_components",
        "define_dynamic_components",
        "load_inputs",
        "pre_solve",
        "pre_iterate",
        "post_iterate",
        "post_solve",
    ]
    # for now, only search in the working directory and switch_model directory
    # TODO: search in user-specified path (--module-path) and in site-packages
    # (in case they installed a switch add-on package of some sort)
    # Note: it is a bad idea to test the built-in modules, because that is slow
    # and has weird side effects (e.g., `import this`, some Tk demo code and
    # opening https://xkcd.com/353/ in the system browser)
    # note: the __path__variable of a package is a list, to show all the
    # locations its submodules can be found.
    paths = [([""], ""), (switch_model.__path__, "switch_model.")]
    avail_modules = []
    for path, prefix in paths:
        for info in pkgutil.walk_packages(path=path, prefix=prefix):
            try:
                mod = importlib.import_module(info.name)
                if any(hasattr(mod, x) for x in switch_callbacks):
                    avail_modules.append(info.name)
            except:
                # some kind of error, skip
                pass

    return avail_modules


def arg_dict(arg, *ops):
    action = arg.__class__.__name__.strip("_")
    if action.endswith("Action"):
        action = action[:-6]
    result = {}
    for flag in arg.option_strings:
        d = result[flag] = dict()
        d["action"] = action
        for op in ops + ("nargs", "default", "choices", "help"):
            d[op] = getattr(arg, op)
        # help text may be linewrapped, which Python automatically cleans up
        d["help"] = unwrap(d["help"])
        if flag == "--rps-no-new-renewables":
            breakpoint()
    return result


def module_arguments(module):
    import argparse as ap

    result = dict()

    mod = importlib.import_module(module)  # or sys.modules[module]

    if hasattr(mod, "define_arguments"):
        mod_parser = _ArgumentParser()
        mod.define_arguments(mod_parser)
        for arg in mod_parser._actions:
            if isinstance(arg, ap._HelpAction):
                # skip the default --help option
                continue
            else:
                result.update(arg_dict(arg))

    return result
