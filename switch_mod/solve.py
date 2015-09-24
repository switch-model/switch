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
    args = parser.parse_args(argv)

    opt = pyomo.opt.SolverFactory(args.solver)

    module_list = [
        line.rstrip('\n')
        for line in open(os.path.join(args.inputs_dir, 'modules'), 'r')]

    switch_model = switch_mod.utilities.define_AbstractModel(
        'switch_mod', *module_list)
    switch_instance = switch_model.load_inputs(inputs_dir=args.inputs_dir)

    results = opt.solve(switch_instance, keepfiles=False, tee=False)
    switch_instance.load(results)

    results.write()
    switch_instance.pprint()
    switch_model.save_results(results, switch_instance, args.outputs_dir)


if __name__ == '__main__':
    main(sys.argv[1:])
