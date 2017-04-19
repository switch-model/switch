# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Save a complete text dump of the model and solution, suitable
for development, debugging or using diff tools to compare two runs. 
I do not recommend using this with large datasets or in a production
environment.

"""
import os, sys

def define_arguments(argparser):
    argparser.add_argument("--dump-level", type=int, default=2,
        help="Use 1 for an abbreviated dump via instance.display(), or 2 " +
             "for a complete dump via instance.pprint().")
    argparser.add_argument("--dump-to-screen", action='store_true', default=False, 
        help="Print the model dump to screen as well as an export file.")


def _print_output(instance):
    if instance.options.dump_level == 2:
        instance.pprint()
    elif instance.options.dump_level == 1:
        instance.display()
    else:
        raise RuntimeError("Invalid value for command line param --dump-level") 


def post_solve(instance, outdir):
    """
    Dump the model & solution to model_dump.txt using either
    instance.display() or instance.pprint(), depending on the value of
    dump-level. Default is pprint().
    """
    stdout_copy = sys.stdout  # make a copy of current sys.stdout to return to eventually
    out_path = os.path.join(outdir, "model_dump.txt")
    out_file = open(out_path, "w", buffering=1)
    sys.stdout = out_file
    _print_output(instance)
    sys.stdout = stdout_copy
    if instance.options.dump_to_screen:
        _print_output(instance)
