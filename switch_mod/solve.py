# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Command line front-end for running the Switch model solver.

Usage:  python -m switch_mod.solve [ARGS]
"""

import argparse
import os
import sys

import pyomo.opt

import switch_mod.utilities


def main(argv):
    parser = argparse.ArgumentParser(
        prog='python -m switch_mod.solve',
        description='Runs the Switch power grid model solver.')
    parser.add_argument(
        '--inputs-dir', type=str, default='inputs',
        help='Directory containing input files (default is "inputs")')
    parser.add_argument(
        '--outputs-dir', type=str, default='outputs',
        help='Directory to write output files (default is "outputs")')
    parser.add_argument(
        '--solver', type=str, default='glpk',
        help='Linear program solver to use (default is "glpk")')
    parser.add_argument(
        '--verbose', '-v', default=False, action='store_true',
        help='Dump data about internal workings to stdout')
    args = parser.parse_args(argv)

    (switch_model, switch_instance) = load(args.inputs_dir)
    opt = pyomo.opt.SolverFactory(args.solver)
    results = opt.solve(switch_instance, keepfiles=False, tee=False)
    switch_model.save_results(results, switch_instance, args.outputs_dir)

    if args.verbose:
        # Print a dump of the results and model instance to standard output.
        results.write()
        switch_instance.pprint()


def load(inputs_dir):
    try:
        module_fh = open(os.path.join(inputs_dir, 'modules'), 'r')
    except IOError, exc:
        sys.exit('Failed to open input file: {}'.format(exc))
    module_list = [line.rstrip('\n') for line in module_fh]

    switch_model = switch_mod.utilities.define_AbstractModel(
        'switch_mod', *module_list)
    switch_instance = switch_model.load_inputs(inputs_dir=inputs_dir)
    return (switch_model, switch_instance)


if __name__ == '__main__':
    main(sys.argv[1:])
